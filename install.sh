#!/bin/bash
set -euo pipefail

# mine29-scraper-worker unattended installer for Alibaba ECS (Ubuntu/Debian)
# Usage: curl -sSL <raw-url>/install.sh | bash
#    or: bash install.sh

APP_DIR="/opt/mine29-scraper-worker"
REPO_URL="https://github.com/arifinreinaldo/mine29-scraper-worker.git"

log() { echo "[mine29] $*"; }
err() { echo "[mine29] ERROR: $*" >&2; exit 1; }

# --- Root check ---
if [ "$(id -u)" -ne 0 ]; then
    err "Run as root: sudo bash install.sh"
fi

# --- Install Docker if missing ---
if ! command -v docker &>/dev/null; then
    log "Installing Docker..."
    apt-get update -qq
    apt-get install -y -qq docker.io docker-compose-plugin >/dev/null
    systemctl enable --now docker
    log "Docker installed"
else
    log "Docker already installed"
fi

# --- Clone or pull repo ---
if [ -d "$APP_DIR/.git" ]; then
    log "Updating existing repo..."
    git -C "$APP_DIR" pull --ff-only
else
    log "Cloning repo..."
    apt-get install -y -qq git >/dev/null
    git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"

# --- Generate config.yaml if missing ---
if [ ! -f config.yaml ]; then
    log "Generating config.yaml from template..."
    cp config.example.yaml config.yaml
fi

# --- Generate .env if missing ---
if [ ! -f .env ]; then
    log "Generating .env from template..."
    cp .env.example .env
fi

# --- Build and start ---
log "Building and starting container..."
docker compose up -d --build

log "Waiting for initial run..."
sleep 5
docker compose logs --tail 20

log ""
log "=============================="
log "  Installation complete!"
log "=============================="
log ""
log "Config:  $APP_DIR/config.yaml"
log "Env:     $APP_DIR/.env"
log "Logs:    docker compose -f $APP_DIR/docker-compose.yml logs -f"
log ""
log "Next steps:"
log "  1. Edit $APP_DIR/config.yaml to set your ntfy topics"
log "  2. Edit $APP_DIR/.env to set NTFY_TOKEN (if using private topics)"
log "  3. Restart: cd $APP_DIR && docker compose up -d"
log "  4. Subscribe to your ntfy topics on your phone"
