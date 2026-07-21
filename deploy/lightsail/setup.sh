#!/usr/bin/env bash
# Run this on the Lightsail instance itself (via the browser SSH console),
# not on your own machine. See DEPLOY-LIGHTSAIL.md for the full walkthrough.
set -euo pipefail

echo "== Installing system packages =="
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip git curl

REPO_DIR="$HOME/autostrat-loom-backend"

if [ ! -d "$REPO_DIR" ]; then
  read -rp "GitHub repo URL (e.g. https://github.com/you/autostrat-loom-backend.git): " REPO_URL
  git clone "$REPO_URL" "$REPO_DIR"
else
  echo "$REPO_DIR already exists, skipping clone."
fi

cd "$REPO_DIR"

echo "== Creating virtual environment and installing dependencies =="
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "Created .env from .env.example."
  echo "Edit it now — at minimum set ANTHROPIC_API_KEY, LOOM_ADMIN_KEYS, and CORS_ORIGINS:"
  echo "  nano .env"
  echo ""
  echo "For LOOM_ADMIN_KEYS, generate a random value with:"
  echo "  python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
fi

echo ""
echo "== Base setup done =="
echo "Next steps (see DEPLOY-LIGHTSAIL.md):"
echo "  1. Edit .env if you haven't already: nano $REPO_DIR/.env"
echo "  2. Install the systemd service (deploy/lightsail/loom-api.service)"
echo "  3. Install Caddy and its config (deploy/lightsail/Caddyfile)"
