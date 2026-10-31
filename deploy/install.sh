#!/usr/bin/env bash
# Установка playground-gateway на стенд. Пользовательский юнит, без sudo.
# Использование: ./install.sh
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/playground-gateway}"
cd "$APP_DIR"

python3 -m venv venv
venv/bin/pip install -q -r requirements.txt

mkdir -p data "$HOME/.config/systemd/user"
cp deploy/playground-gateway.service "$HOME/.config/systemd/user/"

if [ ! -f "$HOME/playground-gateway.env" ]; then
  KEY="$(head -c 24 /dev/urandom | base64)"
  cat > "$HOME/playground-gateway.env" <<EOF
GATEWAY_API_KEY=$KEY
CODEX_BIN=${CODEX_BIN:-codex}
CODEX_ARGS=--skip-git-repo-check
RUNS_PER_DAY=10
CONCURRENCY=2
EOF
  echo "Создан $HOME/playground-gateway.env — ключ сгенерирован автоматически"
fi

systemctl --user daemon-reload
systemctl --user enable --now playground-gateway.service
systemctl --user status playground-gateway.service --no-pager || true
echo "Готово: http://127.0.0.1:8787/healthz"
