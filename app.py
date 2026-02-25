import json
import logging
import os
import random
import re
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, render_template, request, session
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from loguru import logger
from pydantic import BaseModel, ValidationError

from generator import _deduplicate, ensure_pool, generate_answers, get_status, load_answers, save_answers


# ---------------------------------------------------------------------------
# Loguru – Flask/Werkzeug-Logs abfangen
# ---------------------------------------------------------------------------

class _InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)


# ---------------------------------------------------------------------------
# Log-Ringbuffer – letzte 200 Einträge für Admin-Panel
# ---------------------------------------------------------------------------

_log_buffer: deque = deque(maxlen=200)


def _log_sink(message) -> None:  # type: ignore[no-untyped-def]
    record = message.record
    _log_buffer.append({
        "time": record["time"].strftime("%H:%M:%S"),
        "level": record["level"].name,
        "message": record["message"],
    })


logger.add(_log_sink, level="INFO")


# ---------------------------------------------------------------------------
# Pydantic – config.yaml Validierung
# ---------------------------------------------------------------------------

class _PoolCfg(BaseModel):
    min_size: int = 25
    max_size: int = 100
    answers_per_request: int = 10


class _SpeechCfg(BaseModel):
    prompt_file: Optional[str] = None
    prompt: Optional[str] = None
    auto_refresh_seconds: int = 25
    generate_on_startup: bool = True
    auto_rotate_hours: int = 0
    pool: _PoolCfg = _PoolCfg()


class _AiCfg(BaseModel):
    provider: str
    fallback_provider: Optional[str] = None


class _MascotCfg(BaseModel):
    name: str = "KI mit Bedacht"
    image: str = "images/robot3.png"


class _AppCfg(BaseModel):
    mascot: _MascotCfg = _MascotCfg()
    speech: _SpeechCfg
    ai: _AiCfg
    providers: dict = {}

# .env automatisch laden (für lokale Entwicklung ohne manuelles `source .env`)
load_dotenv()

CONFIG_FILE = Path(__file__).parent / "config.yaml"

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-change-me")

Compress(app)
Talisman(
    app,
    force_https=False,
    strict_transport_security=False,
    content_security_policy=False,
)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    # memory:// reicht bei 1 Gunicorn-Worker; bei mehreren auf Redis umstellen
    storage_uri="memory://",
    default_limits=[],
)


def load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    try:
        _AppCfg(**cfg)
    except ValidationError as e:
        logger.warning("config.yaml Validierungsfehler:\n{}", e)
    prompt_file = cfg["speech"].get("prompt_file")
    if prompt_file:
        p = CONFIG_FILE.parent / prompt_file
        if p.exists():
            cfg["speech"]["prompt"] = p.read_text(encoding="utf-8")
        else:
            cfg["speech"].setdefault("prompt", "")
            logger.warning("prompt_file '{}' nicht gefunden – leerer Prompt wird verwendet.", prompt_file)
    return cfg


config = load_config()

_queue: list[str] = []
_queue_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Admin-Auth
# ---------------------------------------------------------------------------

def _require_admin(f):
    """Decorator: prüft Admin-Session; leitet sonst zu Login oder 401 um."""
    from functools import wraps

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            if request.is_json or request.path.startswith("/admin/api/"):
                return jsonify({"status": "unauthorized"}), 401
            return redirect("/admin/login")
        return f(*args, **kwargs)

    return wrapper


def _audit(action: str, detail: str = "") -> None:
    """Loggt Admin-Aktionen für Audit-Zwecke."""
    logger.info("[AUDIT] {} | {}", action, detail)


# ---------------------------------------------------------------------------
# SSE-Hilfsfunktion
# ---------------------------------------------------------------------------

def _pop_answer() -> dict:
    """Thread-sicher: nächste Antwort aus der shuffled Queue."""
    global _queue
    with _queue_lock:
        if not _queue:
            answers = load_answers()
            if not answers:
                return {"answer": "Lade Tipp…", "pool_size": 0}
            _queue = answers.copy()
            random.shuffle(_queue)
        answer = _queue.pop()
        remaining = len(_queue)
    return {"answer": answer, "pool_size": remaining}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template(
        "index.html",
        mascot_name=config["mascot"]["name"],
        mascot_image=config["mascot"]["image"],
    )


@app.route("/api/answer")
def api_answer():
    data = _pop_answer()
    if data["pool_size"] == 0 and data["answer"] == "Lade Tipp…":
        data["answer"] = "Ich denke gerade nach... Bitte kurz warten!"
    return jsonify(data)


@app.route("/api/stream")
def api_stream():
    """Server-Sent Events: schickt alle auto_refresh_seconds einen neuen Tipp."""
    interval = int(config["speech"]["auto_refresh_seconds"])

    def generate():
        yield f"data: {json.dumps(_pop_answer())}\n\n"
        while True:
            time.sleep(interval)
            yield f"data: {json.dumps(_pop_answer())}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/generate", methods=["POST"])
@limiter.limit("5 per minute")
def api_generate():
    try:
        pool_cfg = config["speech"]["pool"]
        per_request = pool_cfg["answers_per_request"]
        max_size = pool_cfg["max_size"]

        reset = request.args.get("reset", "false").lower() == "true"
        current = [] if reset else load_answers()
        min_size = pool_cfg["min_size"]

        # Beim Reset: auffüllen bis min_size (ggf. mehrere API-Calls)
        target = min_size if reset else max_size
        total_generated = 0

        while len(current) < target:
            count = min(per_request, target - len(current))
            if count <= 0:
                break
            new_answers = generate_answers(config, count)
            current = current + new_answers
            total_generated += len(new_answers)

        if len(current) > max_size:
            current = current[-max_size:]

        if total_generated == 0:
            return jsonify({"status": "pool_full", "total": len(current), "generated": 0})

        save_answers(current)
        return jsonify({"status": "ok", "generated": total_generated, "total": len(current)})
    except Exception:
        logger.exception("Fehler bei /api/generate")
        return jsonify({"status": "error", "message": "Interner Fehler"}), 500


@app.route("/api/rotate", methods=["POST"])
@limiter.limit("10 per minute")
def api_rotate():
    try:
        per_request = config["speech"]["pool"]["answers_per_request"]
        current = load_answers()
        # Erste N löschen
        current = current[per_request:]
        # N neue generieren, deduplizieren und anhängen
        raw = generate_answers(config, per_request)
        new_answers = _deduplicate(raw, current) or raw[:max(1, per_request)]
        current = current + new_answers
        save_answers(current)
        return jsonify({"status": "ok", "removed": per_request, "added": len(new_answers), "total": len(current)})
    except Exception:
        logger.exception("Fehler bei /api/rotate")
        return jsonify({"status": "error", "message": "Interner Fehler"}), 500


@app.route("/api/status")
def api_status():
    status = get_status()
    status["pool_config"] = config["speech"]["pool"]
    return jsonify(status)


# ---------------------------------------------------------------------------
# Admin – Authentifizierung
# ---------------------------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        admin_pw = os.environ.get("ADMIN_PASSWORD", "")
        if admin_pw and password == admin_pw:
            session["admin"] = True
            return redirect("/admin")
        error = "Falsches Passwort."
        return render_template("admin_login.html", error=error), 401
    return render_template("admin_login.html", error=None)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin/login")


# ---------------------------------------------------------------------------
# Admin – Dashboard
# ---------------------------------------------------------------------------

@app.route("/admin")
@_require_admin
def admin_dashboard():
    status = get_status()
    providers = config.get("providers", {})
    active_provider = config["ai"]["provider"]
    fallback_provider = config["ai"].get("fallback_provider", "")
    key_status = {
        cfg["api_key_env"]: len(os.environ.get(cfg["api_key_env"], "")) >= 20
        for cfg in providers.values()
        if cfg.get("api_key_env")
    }
    return render_template(
        "admin.html",
        status=status,
        providers=providers,
        active_provider=active_provider,
        fallback_provider=fallback_provider,
        key_status=key_status,
    )


# ---------------------------------------------------------------------------
# Admin – Pool-API
# ---------------------------------------------------------------------------

@app.route("/admin/api/pool")
@_require_admin
def admin_api_pool():
    answers = load_answers()
    status = get_status()
    return jsonify({"answers": answers, "count": len(answers), "last_updated": status.get("last_updated")})


@app.route("/admin/api/pool/<int:n>", methods=["DELETE"])
@_require_admin
def admin_api_pool_delete(n: int):
    answers = load_answers()
    if n < 0 or n >= len(answers):
        return jsonify({"status": "error", "message": "Index außerhalb des Bereichs"}), 400
    answers.pop(n)
    save_answers(answers)
    return jsonify({"status": "ok", "total": len(answers)})


@app.route("/admin/api/generate", methods=["POST"])
@_require_admin
@limiter.limit("5 per minute")
def admin_api_generate():
    try:
        per_request = config["speech"]["pool"]["answers_per_request"]
        max_size = config["speech"]["pool"]["max_size"]
        current = load_answers()
        new_answers = generate_answers(config, per_request)
        current = current + new_answers
        if len(current) > max_size:
            current = current[-max_size:]
        save_answers(current)
        _audit("manual_generate", f"generated={len(new_answers)} total={len(current)}")
        return jsonify({"status": "ok", "generated": len(new_answers), "total": len(current)})
    except Exception:
        logger.exception("Fehler bei /admin/api/generate")
        return jsonify({"status": "error", "message": "Interner Fehler"}), 500


@app.route("/admin/api/rotate", methods=["POST"])
@_require_admin
@limiter.limit("10 per minute")
def admin_api_rotate():
    try:
        per_request = config["speech"]["pool"]["answers_per_request"]
        current = load_answers()
        current = current[per_request:]
        raw = generate_answers(config, per_request)
        new_answers = _deduplicate(raw, current) or raw[:max(1, per_request)]
        current = current + new_answers
        save_answers(current)
        _audit("manual_rotate", f"removed={per_request} added={len(new_answers)}")
        return jsonify({"status": "ok", "removed": per_request, "added": len(new_answers), "total": len(current)})
    except Exception:
        logger.exception("Fehler bei /admin/api/rotate")
        return jsonify({"status": "error", "message": "Interner Fehler"}), 500


# ---------------------------------------------------------------------------
# Admin – Provider & Keys
# ---------------------------------------------------------------------------

_ruamel = None


def _get_ruamel():
    """Lazy-Init für ruamel.yaml (erhält Kommentare & Formatierung)."""
    global _ruamel
    if _ruamel is None:
        from ruamel.yaml import YAML
        _ruamel = YAML()
        _ruamel.preserve_quotes = True
    return _ruamel


def _patch_config_yaml(key: str, value) -> None:
    """Setzt `key` im ai:-Block der config.yaml (kommentar-erhaltend)."""
    ry = _get_ruamel()
    data = ry.load(CONFIG_FILE)
    data["ai"][key] = str(value) if value is not None else None
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        ry.dump(data, f)


def _patch_yaml_value(section_path: str, key: str, value) -> None:
    """Setzt `key: value` in einem hierarchischen YAML-Pfad (erhält Kommentare).

    section_path: z.B. 'speech' oder 'speech.pool'
    """
    ry = _get_ruamel()
    data = ry.load(CONFIG_FILE)
    node = data
    for part in section_path.split("."):
        node = node[part]
    node[key] = value
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        ry.dump(data, f)


@app.route("/admin/api/provider", methods=["POST"])
@_require_admin
def admin_api_provider():
    global config
    data = request.get_json() or {}
    name = data.get("provider", "")
    if name not in config.get("providers", {}):
        return jsonify({"status": "error", "message": f"Unbekannter Provider: {name}"}), 400
    config["ai"]["provider"] = name
    _patch_config_yaml("provider", name)
    _audit("provider_change", name)
    return jsonify({"status": "ok", "provider": name})


@app.route("/admin/api/fallback", methods=["POST"])
@_require_admin
def admin_api_fallback():
    global config
    data = request.get_json() or {}
    name = data.get("provider", "")
    providers = config.get("providers", {})
    if name and name not in providers:
        return jsonify({"status": "error", "message": f"Unbekannter Provider: {name}"}), 400
    config["ai"]["fallback_provider"] = name if name else None
    _patch_config_yaml("fallback_provider", name if name else None)
    _audit("fallback_change", name or "(deaktiviert)")
    return jsonify({"status": "ok", "fallback_provider": name})


@app.route("/admin/api/keys", methods=["POST"])
@_require_admin
def admin_api_keys():
    data = request.get_json() or {}
    env_var = data.get("env_var", "")
    value = data.get("value", "")
    if not env_var:
        return jsonify({"status": "error", "message": "env_var fehlt"}), 400
    if not re.fullmatch(r"[A-Z][A-Z_0-9]*", env_var):
        return jsonify({"status": "error", "message": "Ungültiger Variablenname"}), 400
    # 1. Sofort im laufenden Prozess setzen
    os.environ[env_var] = value
    # 2. In .env-Datei persistieren (Wert in Anführungszeichen, Sonderzeichen escapen)
    safe_value = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "").replace("\r", "")
    env_line = f'{env_var}="{safe_value}"'
    env_path = Path(__file__).parent / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{env_var}="):
            lines[i] = env_line
            updated = True
            break
    if not updated:
        lines.append(env_line)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _audit("key_update", env_var)
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Admin – Prompt-Editor
# ---------------------------------------------------------------------------

@app.route("/admin/api/prompt", methods=["GET"])
@_require_admin
def admin_api_prompt_get():
    prompt_file = config["speech"].get("prompt_file", "prompt.txt")
    app_dir = Path(__file__).parent.resolve()
    p = (app_dir / prompt_file).resolve()
    if not p.is_relative_to(app_dir):
        return jsonify({"status": "error", "message": "Ungültiger Dateipfad"}), 400
    text = p.read_text(encoding="utf-8") if p.exists() else config["speech"].get("prompt", "")
    return jsonify({"prompt": text})


@app.route("/admin/api/prompt", methods=["POST"])
@_require_admin
def admin_api_prompt_set():
    global config
    data = request.get_json() or {}
    text = data.get("prompt", "")
    prompt_file = config["speech"].get("prompt_file", "prompt.txt")
    app_dir = Path(__file__).parent.resolve()
    p = (app_dir / prompt_file).resolve()
    if not p.is_relative_to(app_dir):
        return jsonify({"status": "error", "message": "Ungültiger Dateipfad"}), 400
    p.write_text(text, encoding="utf-8")
    config["speech"]["prompt"] = text
    _audit("prompt_update")
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Admin – Config-Reload
# ---------------------------------------------------------------------------

@app.route("/admin/api/reload", methods=["POST"])
@_require_admin
def admin_api_reload():
    global config
    try:
        new_cfg = load_config()
        old_hours = config["speech"].get("auto_rotate_hours", 0)
        new_hours = new_cfg["speech"].get("auto_rotate_hours", 0)
        config = new_cfg
        if old_hours != new_hours:
            _scheduler.remove_all_jobs()
            if new_hours:
                _scheduler.add_job(_do_rotate, "interval", hours=new_hours)
                if not _scheduler.running:
                    _scheduler.start()
                logger.info("Auto-Rotation neu konfiguriert: alle {}h.", new_hours)
            else:
                logger.info("Auto-Rotation deaktiviert.")
        _audit("config_reload", f"provider={config['ai']['provider']}")
        return jsonify({"status": "ok", "provider": config["ai"]["provider"]})
    except Exception:
        logger.exception("Fehler bei /admin/api/reload")
        return jsonify({"status": "error", "message": "Interner Fehler"}), 400


# ---------------------------------------------------------------------------
# Admin – Log-Viewer
# ---------------------------------------------------------------------------

@app.route("/admin/api/logs")
@_require_admin
def admin_api_logs():
    return jsonify({"logs": list(_log_buffer)})


# ---------------------------------------------------------------------------
# Admin – Anzeige- & Pool-Konfiguration
# ---------------------------------------------------------------------------

@app.route("/admin/api/config")
@_require_admin
def admin_api_config_get():
    sp = config["speech"]
    return jsonify({
        "auto_refresh_seconds": sp.get("auto_refresh_seconds", 25),
        "auto_rotate_hours":    sp.get("auto_rotate_hours", 0),
        "pool": {
            "min_size":            sp["pool"]["min_size"],
            "max_size":            sp["pool"]["max_size"],
            "answers_per_request": sp["pool"]["answers_per_request"],
        },
    })


@app.route("/admin/api/config", methods=["POST"])
@_require_admin
def admin_api_config_set():
    global config
    data = request.get_json() or {}
    errors = []

    try:
        ars  = int(data.get("auto_refresh_seconds",     config["speech"]["auto_refresh_seconds"]))
        arh  = int(data.get("auto_rotate_hours",        config["speech"]["auto_rotate_hours"]))
        pmin = int(data.get("pool_min_size",             config["speech"]["pool"]["min_size"]))
        pmax = int(data.get("pool_max_size",             config["speech"]["pool"]["max_size"]))
        apr  = int(data.get("pool_answers_per_request",  config["speech"]["pool"]["answers_per_request"]))
    except (TypeError, ValueError) as e:
        return jsonify({"status": "error", "message": f"Ungültiger Wert: {e}"}), 400

    if ars < 5:
        errors.append("Refresh muss ≥ 5 s sein.")
    if arh < 0:
        errors.append("Rotation muss ≥ 0 h sein.")
    if pmin < 1:
        errors.append("Pool Min muss ≥ 1 sein.")
    if pmax <= pmin:
        errors.append("Pool Max muss > Min sein.")
    if apr < 1 or apr > pmax:
        errors.append("Pro Request muss ≥ 1 und ≤ Max sein.")
    if errors:
        return jsonify({"status": "error", "message": " ".join(errors)}), 400

    old_arh = config["speech"].get("auto_rotate_hours", 0)

    config["speech"]["auto_refresh_seconds"]         = ars
    config["speech"]["auto_rotate_hours"]            = arh
    config["speech"]["pool"]["min_size"]             = pmin
    config["speech"]["pool"]["max_size"]             = pmax
    config["speech"]["pool"]["answers_per_request"]  = apr

    _patch_yaml_value("speech",      "auto_refresh_seconds", ars)
    _patch_yaml_value("speech",      "auto_rotate_hours",    arh)
    _patch_yaml_value("speech.pool", "min_size",             pmin)
    _patch_yaml_value("speech.pool", "max_size",             pmax)
    _patch_yaml_value("speech.pool", "answers_per_request",  apr)

    if old_arh != arh:
        _scheduler.remove_all_jobs()
        if arh:
            _scheduler.add_job(_do_rotate, "interval", hours=arh)
            if not _scheduler.running:
                _scheduler.start()
            logger.info("Auto-Rotation neu konfiguriert: alle {}h.", arh)
        else:
            logger.info("Auto-Rotation deaktiviert.")

    _audit("config_update", f"ars={ars} arh={arh} pmin={pmin} pmax={pmax} apr={apr}")
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Auto-Rotation: Pool in konfigurierbarem Intervall rotieren (APScheduler)
# ---------------------------------------------------------------------------

def _do_rotate():
    """Rotiert den Pool: entfernt älteste Antworten und generiert neue."""
    try:
        per_request = config["speech"]["pool"]["answers_per_request"]
        current = load_answers()
        current = current[per_request:]
        raw = generate_answers(config, per_request)
        new_answers = _deduplicate(raw, current) or raw[:max(1, per_request)]
        current = current + new_answers
        save_answers(current)
        logger.info("Auto-Rotation: {} alte entfernt, {} neue hinzugefügt. Pool: {}.", per_request, len(new_answers), len(current))
    except Exception as e:
        logger.error("Auto-Rotation fehlgeschlagen: {}", e)


_scheduler = BackgroundScheduler()


# ---------------------------------------------------------------------------
# Startup: Pool auffüllen wenn nötig, Scheduler starten
# ---------------------------------------------------------------------------

if config["speech"].get("generate_on_startup", False):
    logger.info("Prüfe Antwort-Pool beim Start...")
    try:
        result = ensure_pool(config)
        logger.info("Pool-Status: {}", result)
    except Exception as e:
        logger.warning("Pool konnte nicht aufgefüllt werden: {}", e)
        logger.warning("Server startet trotzdem. Prüfe API-Key.")

hours = config["speech"].get("auto_rotate_hours", 0)
if hours:
    _scheduler.add_job(_do_rotate, "interval", hours=hours)
    _scheduler.start()
    logger.info("Auto-Rotation alle {}h aktiviert.", hours)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", host="0.0.0.0", port=5000)
