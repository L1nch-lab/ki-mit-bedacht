# KI mit Bedacht

Interaktives Web-Maskottchen für den UKM-Infoscreen. Zeigt KI-Tipps in einer animierten Sprechblase, daneben ein Labyrinth-Algorithmen-Duell (A\* vs. BFS vs. DFS vs. Greedy).

## Features

- Sprechblase mit Typewriter-Effekt, Tipp-Wechsel via Server-Sent Events
- 9 KI-Provider (Anthropic, OpenAI, OpenRouter, Mistral, DeepSeek, xAI, Gemini, Ollama, LM Studio), automatischer Fallback
- Shuffle-Queue + automatische Pool-Rotation
- Passwortgeschütztes Admin-Interface: Pool, Provider, API-Keys, Prompt, Config & Server-Log
- Labyrinth: A\* vs. BFS vs. DFS vs. Greedy mit Echtzeit-Statistiken

## Quickstart (Docker)

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml up --build
```

Browser: [http://localhost:5000](http://localhost:5000) · Admin: [http://localhost:5000/admin](http://localhost:5000/admin)

## Quickstart (LXC / Proxmox)

```bash
rsync -av "KI mit Bedacht/" root@<CT-IP>:/tmp/mascot-src/
bash /tmp/mascot-src/lxc/provision.sh   # im Container als root
nano /opt/mascot-app/.env && systemctl restart mascot
```

> Das Skript ist idempotent – `.env` und `answers.json` bleiben erhalten.

## Lokale Entwicklung

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

## Konfiguration (`config.yaml`)

| Schlüssel | Standard |
| --------- | -------- |
| `mascot.name` / `mascot.image` | `KI mit Bedacht` / `images/robot3.png` |
| `speech.auto_refresh_seconds` | `25` |
| `speech.auto_rotate_hours` | `1` |
| `speech.pool.min_size` / `max_size` | `25` / `100` |
| `speech.pool.answers_per_request` | `10` |
| `ai.provider` | `openrouter` |
| `ai.fallback_provider` | `claude_haiku` |

Verfügbare Provider: `openrouter`, `claude_haiku`, `gpt_mini`, `mistral`, `deepseek`, `xai`, `gemini`, `ollama`, `lm_studio`

Prompt bearbeiten: `prompt.txt` direkt editieren oder im Admin-Interface unter „KI-Prompt".

## Umgebungsvariablen

`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `MISTRAL_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY`, `ADMIN_PASSWORD`, `SESSION_SECRET`, `FLASK_DEBUG`

> API-Keys können auch direkt im Admin-Interface gesetzt werden (schreibt in `.env`).

## Projektstruktur

```text
KI mit Bedacht/
├── app.py              # Flask-App, Routes, SSE, Admin
├── generator.py        # KI-Integration, Pool-Verwaltung
├── config.yaml / prompt.txt
├── CLAUDE.md           # Projektkontext für Claude Code
├── docker/             # Dockerfile, docker-compose.yml
├── lxc/                # provision.sh, mascot.service
├── static/             # style.css, script.js, maze.js, admin.*
└── templates/          # index.html, admin.html, admin_login.html
```

## Lizenz

MIT – siehe [LICENSE](LICENSE).
