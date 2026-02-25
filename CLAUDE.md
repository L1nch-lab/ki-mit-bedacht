# KI mit Bedacht — Projektkontext für Claude

## Projektübersicht

Flask-Web-App für den UKM-Infoscreen: KI-generierte Tipps per SSE in animierter
Sprechblase, daneben ein Labyrinth-Algorithmen-Duell (A\* vs. BFS vs. DFS vs. Greedy).
Kiosk-Modus mit Vollbild-Button und Cursor-Auto-Hide nach 3s Inaktivität.

## Tech-Stack

- Python 3.11, Flask 3.1
- Gunicorn: `--worker-class=gthread --workers=1 --threads=4`
- Pydantic v2 (Config-Validierung, nur Warnungen — roher Dict bleibt aktiv)
- Loguru (strukturiertes Logging + 200-Einträge-Ringbuffer für Admin-Panel)
- APScheduler (automatische Pool-Rotation)
- flask-limiter, flask-talisman, flask-compress

## Schlüsseldateien

```
app.py           # Flask-App, Routes, SSE (/api/stream), Admin-API
generator.py     # KI-Pool, 9 Provider, Deduplizierung (Jaccard >= 0.6)
config.yaml      # Konfiguration — wird vom Admin-Panel live überschrieben
prompt.txt       # System-Prompt (plain text, im Admin editierbar)
answers.json     # Antwort-Pool (persistiert, atomic write)
docker/          # Dockerfile, docker-compose.yml
lxc/             # provision.sh (idempotent), mascot.service
static/          # style.css, script.js, maze.js, admin.js, admin.css
templates/       # index.html, admin.html, admin_login.html
```

## Lokale Entwicklung

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # ADMIN_PASSWORD, API-Keys eintragen
python app.py
```

## Docker

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml up --build
# config.yaml und answers.json sind als Volumes gemountet
```

## Wichtige Konventionen

- **Kein Auto-Commit** — nur auf explizite Anfrage
- **`request.get_json() or {}`** — immer mit `or {}` (None-Guard bei fehlendem Body)
- **config.yaml Race Condition** — `_patch_config_yaml()` hat keinen Thread-Lock;
  bei gleichzeitigen Admin-Requests möglich (bekannt, nicht kritisch für Einzelnutzer)
- **SSE-Interval eingefroren** — `auto_refresh_seconds` wird zum Connect-Zeitpunkt
  gelesen; Config-Änderung wirkt erst beim nächsten Seitenaufruf
- **Pydantic nur zur Validierung** — ersetzt den rohen `config`-Dict nicht

## Deployment

- LXC: `lxc/provision.sh` (`.env` und `answers.json` bleiben bei Re-Run erhalten)
- Admin: `/admin` (Passwort via `ADMIN_PASSWORD` in `.env`)
- Rate-Limiting aktiv (flask-limiter), Session-Secret via `SESSION_SECRET` in `.env`
