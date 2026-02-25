#!/usr/bin/env bash
# lxc/provision.sh -- KI mit Bedacht in einem LXC-Container einrichten
#
# Verwendung (als root im Container):
#
#   Option A -- Dateien schon vorhanden (z.B. via rsync/scp vom Host):
#     rsync -av "KI mit Bedacht/" root@<CT-IP>:/tmp/ki-mit-bedacht-src/
#     bash /tmp/ki-mit-bedacht-src/lxc/provision.sh
#
#   Option B -- Git-Clone (Container braucht Internet):
#     export REPO_URL="https://github.com/OWNER/ki-mit-bedacht.git"
#     bash /tmp/ki-mit-bedacht-src/lxc/provision.sh
#
# Nach der Installation:
#   nano /opt/ki-mit-bedacht/.env   <- API-Keys eintragen
#   systemctl restart ki-mit-bedacht

set -euo pipefail

# Konfiguration
APP_USER="ki-mit-bedacht"
APP_DIR="/opt/ki-mit-bedacht"
SERVICE_NAME="ki-mit-bedacht"
PYTHON="python3.11"
SRC_DIR="${SRC_DIR:-/tmp/ki-mit-bedacht-src}"
REPO_URL="${REPO_URL:-}"

log() { echo "[provision] $*"; }
die() { echo "[provision] FEHLER: $*" >&2; exit 1; }

# Betriebssystem pruefen
[ "$EUID" -eq 0 ] || die "Bitte als root ausfuehren."

if [ -f /etc/os-release ]; then
    . /etc/os-release
    log "System: ${PRETTY_NAME:-unbekannt}"
fi

# System-Pakete installieren
log "Installiere System-Pakete..."
apt-get update -qq
apt-get install -y -qq \
    python3.11 python3.11-venv python3.11-dev \
    git curl ca-certificates rsync

# Quell-Dateien beschaffen
if [ -d "$SRC_DIR" ] && [ -f "$SRC_DIR/app.py" ]; then
    log "Nutze vorhandene Quelldateien aus $SRC_DIR"
elif [ -n "$REPO_URL" ]; then
    log "Klone Repository: $REPO_URL"
    git clone --depth=1 "$REPO_URL" "$SRC_DIR"
else
    die "Keine Quelldateien gefunden. SRC_DIR oder REPO_URL setzen."
fi

# App-User anlegen
if ! id "$APP_USER" >/dev/null 2>&1; then
    log "Erstelle System-User: $APP_USER"
    useradd --system --shell /usr/sbin/nologin \
        --home-dir "$APP_DIR" --no-create-home "$APP_USER"
fi

# App-Dateien installieren
log "Kopiere App-Dateien nach $APP_DIR"
mkdir -p "$APP_DIR"
rsync -a --delete \
    --exclude='.env' \
    --exclude='answers.json' \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='.git/' \
    "$SRC_DIR/" "$APP_DIR/"

# Python-venv + Pakete
log "Erstelle venv und installiere Pakete..."
if [ ! -d "$APP_DIR/venv" ]; then
    "$PYTHON" -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet --no-cache-dir -r "$APP_DIR/requirements.txt"

# .env anlegen (nur wenn noch nicht vorhanden)
if [ ! -f "$APP_DIR/.env" ]; then
    log "Erstelle .env aus .env.example -- bitte API-Keys eintragen!"
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
fi

# Verzeichnis-Rechte setzen
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 750 "$APP_DIR"

# systemd-Service installieren
log "Installiere systemd-Service: $SERVICE_NAME"
cp "$APP_DIR/lxc/mascot.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# Ergebnis
IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
echo ""
echo "KI mit Bedacht laeuft!"
echo "  Hauptseite:    http://${IP}:5000"
echo "  Admin-Panel:   http://${IP}:5000/admin"
echo ""
echo "  API-Keys:      nano $APP_DIR/.env && systemctl restart $SERVICE_NAME"
echo "  Logs:          journalctl -u $SERVICE_NAME -f"
echo "  Status:        systemctl status $SERVICE_NAME"
echo ""
