# Changelog

<!-- markdownlint-disable MD024 -->

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.
Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

---

## [Unreleased]

---

## [1.0.0] – 2026-02-25

### Added

- **CLAUDE.md** – Projektkontext für Claude Code (Tech-Stack, Dateistruktur, Konventionen)

### Changed

- **Projekt umbenannt** zu „KI mit Bedacht" (war: Klaudius / mascot-app)
- Maskottchen-Name von der Hauptseite entfernt – kein angezeigter Name mehr
- Hintergrundbild entfernt, nur noch UKM-Hintergrundfarbe (`#f4f6f8`)
- Sprechblase: Höhe `180px` → `210px` (mehr Platz für längere Tipps)
- `docker-compose.yml`: `config.yaml` als Volume gemountet (Persistenz nach Neustart)
- `.gitignore` erweitert: Python-Build-Artefakte, Logs, Editor-Dateien, Docker-Override

### Fixed

- `request.get_json() or {}` in 5 Admin-Routen (`AttributeError` bei fehlendem Body / falschem Content-Type)
- `maze.js`: Header-Kommentar um Greedy ergänzt
- `script.js`: Irreführenden `onerror`-Kommentar entfernt

---

## [1.0.0-beta.11] – 2026-02-25

### Added

- **Greedy Best-First Search** als 4. Algorithmus im Labyrinth-Duell (lila)
- **Admin: Anzeige & Pool-Konfiguration** – `auto_refresh_seconds`, `auto_rotate_hours`, `pool.min/max_size`, `answers_per_request` direkt im Browser editierbar (`GET/POST /admin/api/config`)
- `_patch_yaml_value()` – hierarchisches YAML-Patching ohne Kommentarverlust

### Changed

- Labyrinth-Breite: COLS 61 → 79
- Schriftgrößen auf `index.html` durchgehend erhöht
- `gunicorn~=23.0` → `~=25.0`, `flask-limiter~=3.11` → `~=4.1`

### Fixed

- KeyError in `load_config()` wenn `prompt.txt` fehlt
- Regex in `_patch_config_yaml` matchte Keys außerhalb des `ai:`-Blocks
- Retry-Logik in `ensure_pool` retried jetzt tatsächlich (statt durchzufallen)
- Falscher Anthropic-Modellname: `claude-haiku-4-5` → `claude-haiku-4-5-20251001`

---

## [1.0.0-beta.10] – 2026-02-23

### Added

- **LXC/Proxmox-Deployment**: `lxc/provision.sh` (idempotent) + `lxc/mascot.service` mit systemd-Hardening
- **GitHub Actions `lxc.yml`**: shellcheck, systemd-verify, Smoke-Test

### Changed

- Docker-Dateien nach `docker/` verschoben

---

## [1.0.0-beta.9] – 2026-02-23

### Added

- **Server-Log im Admin**: letzte 200 Einträge, farbige Level-Labels, Auto-Refresh alle 5s

### Fixed

- Gunicorn `gthread`-Worker ergänzt (sync-Worker blockierte SSE)
- Totes `REFRESH_SECONDS`-Überbleibsel entfernt

---

## [1.0.0-beta.8] – 2026-02-23

### Added

- **loguru** – strukturiertes Logging, ersetzt alle `print()`-Statements
- **pydantic v2** – Schema-Validierung für `config.yaml`
- **flask-talisman** – Security-Header
- **flask-compress** – Gzip/Brotli-Komprimierung

---

## [1.0.0-beta.7] – 2026-02-22

### Added

- **Prompt-Editor im Admin** (`GET/POST /admin/api/prompt`)
- `prompt.txt` als eigenständige plain-text Datei

---

## [1.0.0-beta.6] – 2026-02-22

### Added

- **Fallback-Provider** bei API-Fehler (`ai.fallback_provider`)
- **Server-Sent Events** (`GET /api/stream`) statt Polling
- **Admin-Interface** unter `/admin`: Pool, Provider, API-Keys, Config-Reload

---

## [1.0.0-beta.5] – 2026-02-22

### Added

- Vollbild-Button + Cursor-Auto-Hide für Kiosk-Betrieb

---

## [1.0.0-beta.4] – 2026-02-22

### Added

- OpenAI (ChatGPT / gpt-4o-mini) als KI-Provider

---

## [1.0.0-beta.3] – 2026-02-22

### Added

- `tenacity` – Retry-Logik für API-Calls
- `APScheduler` – robuste Auto-Rotation
- `flask-limiter` – Rate Limiting

---

## [1.0.0-beta.2] – 2026-02-22

### Added

- Docker `HEALTHCHECK`, `roundRect`-Polyfill, CSS-Variablen, Responsive Media-Queries

### Changed

- Atomares Schreiben in `save_answers()`, robusteres `_parse_response()`

---

## [1.0.0-beta.1] – 2026-02-22

### Added

- CI/CD: `docker.yml`, `lint.yml`, `security.yml`, `claude.yml`, `dependabot.yml`
- `README.md`, `CHANGELOG.md`, `.dockerignore`, `.editorconfig`

---

## [1.0.0-alpha] – 2026-02-22

### Added

- Flask-App mit KI-Maskottchen, Sprechblase, Shuffle-Queue, KI-Pool
- Anthropic Claude + OpenRouter als Provider
- Labyrinth-Visualisierung: A\* vs. BFS vs. DFS
