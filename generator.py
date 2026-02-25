import json
import os
import re
from datetime import datetime
from pathlib import Path

import anthropic
from loguru import logger
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

ANSWERS_FILE = Path(__file__).parent / "answers.json"


def load_answers() -> list[str]:
    if not ANSWERS_FILE.exists():
        return []
    try:
        with open(ANSWERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("answers", [])
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("answers.json nicht lesbar: {}", e)
        return []


def save_answers(answers: list[str]) -> None:
    payload = {
        "answers": answers,
        "last_updated": datetime.now().isoformat(),
        "count": len(answers),
    }
    tmp = ANSWERS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(ANSWERS_FILE)  # atomisches Rename auf POSIX


def get_status() -> dict:
    if not ANSWERS_FILE.exists():
        return {"count": 0, "last_updated": None}
    try:
        with open(ANSWERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "count": data.get("count", 0),
                "last_updated": data.get("last_updated"),
            }
    except (json.JSONDecodeError, OSError):
        return {"count": 0, "last_updated": None}


def _resolve_key(value: str) -> str:
    """Gibt den API-Key aus der Umgebungsvariablen zurück."""
    key = os.environ.get(value)
    if not key:
        raise ValueError(f"API-Key nicht gefunden. Umgebungsvariable '{value}' ist nicht gesetzt.")
    return key


def _build_prompt(config: dict, count: int) -> tuple[str, str]:
    system_prompt = config["speech"]["prompt"]
    user_prompt = (
        f'Generiere genau {count} kurze Tipps zu diesem Thema.\n'
        f"Antworte NUR mit einem JSON-Array von Strings, ohne Erklärungen.\n"
        f"Verwende KEIN Markdown, KEINE Sterne, KEINE Unterstriche. Emojis sind erlaubt und erwünscht.\n"
        f"Beginne jeden Tipp NICHT mit einer Nummer oder dem Wort 'Tipp'.\n"
        f'Beispiel: ["Nutze täglich 10 Minuten für KI-Experimente.", "Teile deine Erkenntnisse im Team."]'
    )
    return system_prompt, user_prompt


def _strip_markdown(text: str) -> str:
    """Entfernt gängige Markdown-Formatierungen aus einem String."""
    # **fett**, *kursiv*, ***beides***
    text = re.sub(r"\*{1,3}([^*]*)\*{1,3}", r"\1", text)
    # __fett__, _kursiv_
    text = re.sub(r"_{1,3}([^_]*)_{1,3}", r"\1", text)
    # # Überschriften
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # - Listenpunkte am Anfang
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    # Numerierungen: "Tipp 1:", "1.", "1)" etc.
    text = re.sub(r"^\s*Tipp?\s*\d+\s*[:\-.]?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*\d+[.)]\s*", "", text)
    return text.strip()


def _word_overlap(a: str, b: str) -> float:
    """Jaccard-Ähnlichkeit auf Wortebene (0.0 … 1.0)."""
    words_a = set(re.findall(r"\w+", a.lower()))
    words_b = set(re.findall(r"\w+", b.lower()))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _deduplicate(new_answers: list[str], existing: list[str], threshold: float = 0.6) -> list[str]:
    """Filtert neue Antworten heraus, die zu ähnlich zu vorhandenen sind."""
    pool = list(existing)
    unique = []
    for candidate in new_answers:
        if all(_word_overlap(candidate, p) < threshold for p in pool):
            unique.append(candidate)
            pool.append(candidate)
    return unique


def _parse_response(raw: str) -> list[str]:
    """Extrahiert ein JSON-Array aus der API-Antwort (robust gegen umgebenden Text)."""
    raw = raw.strip()

    # Direkter Parse: API hat sauberes JSON geliefert
    try:
        answers = json.loads(raw)
        if isinstance(answers, list):
            return [_strip_markdown(str(a)) for a in answers if str(a).strip()]
    except json.JSONDecodeError:
        pass

    # Fallback: JSON-Array per Klammer-Zählung extrahieren
    start = raw.find("[")
    if start == -1:
        raise ValueError(f"Kein JSON-Array in der Antwort: {raw!r}")

    depth = 0
    end = start
    for i, ch in enumerate(raw[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break

    try:
        answers = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"Ungültiges JSON-Array in der Antwort: {e}") from e

    if not isinstance(answers, list):
        raise ValueError("Geparste Antwort ist keine Liste.")
    return [_strip_markdown(str(a)) for a in answers if str(a).strip()]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def _generate_via_anthropic(provider_cfg: dict, config: dict, count: int) -> list[str]:
    api_key = _resolve_key(provider_cfg.get("api_key_env", ""))
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt, user_prompt = _build_prompt(config, count)
    message = client.messages.create(
        model=provider_cfg["model"],
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return _parse_response(message.content[0].text.strip())


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def _generate_via_openrouter(provider_cfg: dict, config: dict, count: int) -> list[str]:
    api_key = _resolve_key(provider_cfg.get("api_key_env", ""))
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": provider_cfg.get("site_url", "http://localhost:5000"),
            "X-Title": provider_cfg.get("site_name", "Mascot App"),
        },
    )
    system_prompt, user_prompt = _build_prompt(config, count)
    response = client.chat.completions.create(
        model=provider_cfg["model"],
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return _parse_response(response.choices[0].message.content.strip())


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def _generate_via_openai(provider_cfg: dict, config: dict, count: int) -> list[str]:
    api_key = _resolve_key(provider_cfg.get("api_key_env", ""))
    client = OpenAI(api_key=api_key)
    system_prompt, user_prompt = _build_prompt(config, count)
    response = client.chat.completions.create(
        model=provider_cfg["model"],
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return _parse_response(response.choices[0].message.content.strip())


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def _generate_via_openai_compat(provider_cfg: dict, config: dict, count: int) -> list[str]:
    """Generischer OpenAI-kompatibler Provider (Mistral, DeepSeek, xAI, Ollama, …)."""
    api_key_env = provider_cfg.get("api_key_env", "")
    # Lokale Provider (Ollama, LM Studio) benötigen keinen echten API-Key
    resolved_key = os.environ.get(api_key_env, "no-key") if api_key_env else "no-key"
    client = OpenAI(
        api_key=resolved_key,
        base_url=provider_cfg["base_url"],
    )
    system_prompt, user_prompt = _build_prompt(config, count)
    response = client.chat.completions.create(
        model=provider_cfg["model"],
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return _parse_response(response.choices[0].message.content.strip())


def _dispatch(provider_cfg: dict, config: dict, count: int) -> list[str]:
    """Ruft die passende _generate_via_*-Funktion anhand des Provider-Typs auf."""
    ptype = provider_cfg.get("type", "anthropic")
    if ptype == "openrouter":
        return _generate_via_openrouter(provider_cfg, config, count)
    if ptype == "openai":
        return _generate_via_openai(provider_cfg, config, count)
    if ptype == "openai_compat":
        return _generate_via_openai_compat(provider_cfg, config, count)
    return _generate_via_anthropic(provider_cfg, config, count)


def generate_answers(config: dict, count: int) -> list[str]:
    """Generiert `count` Antworten über den konfigurierten Provider.
    Bei Fehler wird automatisch auf `ai.fallback_provider` gewechselt (falls gesetzt).
    """
    provider_name = config["ai"]["provider"]
    fallback_name = config["ai"].get("fallback_provider")
    providers = config.get("providers", {})
    if provider_name not in providers:
        raise ValueError(
            f"Provider '{provider_name}' nicht in config.yaml unter 'providers:' definiert."
        )
    try:
        return _dispatch(providers[provider_name], config, count)
    except Exception as primary_err:
        if fallback_name and fallback_name in providers and fallback_name != provider_name:
            logger.warning(
                "Provider '{}' fehlgeschlagen ({}). Wechsle auf Fallback '{}'.",
                provider_name, primary_err, fallback_name,
            )
            return _dispatch(providers[fallback_name], config, count)
        raise


def ensure_pool(config: dict) -> dict:
    """Füllt den Pool bis max_size auf. Gibt Status zurück."""
    pool_cfg = config["speech"]["pool"]
    max_size = pool_cfg["max_size"]
    per_request = pool_cfg["answers_per_request"]

    combined = load_answers()

    if len(combined) >= max_size:
        return {"generated": 0, "total": len(combined), "action": "skipped"}

    total_generated = 0
    max_retries = 5
    retries = 0

    while len(combined) < max_size:
        needed = min(per_request, max_size - len(combined))
        raw_answers = generate_answers(config, needed)
        new_answers = _deduplicate(raw_answers, combined)
        if not new_answers:
            retries += 1
            if retries >= max_retries:
                logger.warning("ensure_pool: Abbruch nach {} Deduplizierungs-Fehlschlägen.", max_retries)
                fallback = raw_answers[:max(1, needed)]
                combined.extend(fallback)
                total_generated += len(fallback)
                break
            # Nochmal versuchen, ohne Duplikate einzufügen
            continue
        retries = 0
        combined.extend(new_answers)
        total_generated += len(new_answers)

    save_answers(combined)
    return {"generated": total_generated, "total": len(combined), "action": "generated"}
