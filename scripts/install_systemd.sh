#!/usr/bin/env bash
# install_systemd.sh — поставить systemd-сервисы CRM + Telegram-бота на BlueTerbium.
#
# Usage (из корня репозитория):
#   ./scripts/install_systemd.sh
#
# После установки:
#   systemctl status dommaster-crm dommaster-bot
#   journalctl -u dommaster-crm -f

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  TMP_ENV="$(mktemp)"
  grep -E '^[[:space:]]*BLUETERBIUM_SSH_[A-Z0-9_]+=' .env \
    | sed 's/^[[:space:]]*//' \
    | sed 's/[[:space:]]*#.*$//' > "$TMP_ENV" || true
  set -a
  # shellcheck disable=SC1090
  source "$TMP_ENV"
  set +a
  rm -f "$TMP_ENV"
fi

HOST="${BLUETERBIUM_SSH_HOST:-194.67.103.144}"
PORT="${BLUETERBIUM_SSH_PORT:-2222}"
USER_NAME="${BLUETERBIUM_SSH_USER:-root}"
PASSWORD="${BLUETERBIUM_SSH_PASSWORD:-}"
REMOTE_PATH="${REMOTE_DIR:-/root/AI_Bot_avto_KP}"

SSH_BASE=(ssh -T -p "$PORT" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=25)
RSYNC_SSH="ssh -p ${PORT} -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20"
if [[ -n "$PASSWORD" ]]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "Нужен sshpass или SSH-ключ"
    exit 1
  fi
  export SSHPASS="$PASSWORD"
  SSH_BASE=(sshpass -e "${SSH_BASE[@]}")
  RSYNC_SSH="sshpass -e ${RSYNC_SSH}"
fi

echo "→ копируем unit-файлы на ${USER_NAME}@${HOST}"
"${SSH_BASE[@]}" "${USER_NAME}@${HOST}" "mkdir -p '${REMOTE_PATH}/deploy/systemd' '${REMOTE_PATH}/logs'"
rsync -az -e "$RSYNC_SSH" \
  "$ROOT/deploy/systemd/dommaster-crm.service" \
  "$ROOT/deploy/systemd/dommaster-bot.service" \
  "${USER_NAME}@${HOST}:${REMOTE_PATH}/deploy/systemd/"

"${SSH_BASE[@]}" "${USER_NAME}@${HOST}" bash -s -- "$REMOTE_PATH" <<'EOF'
set -euo pipefail
REMOTE_PATH="$1"

install -m 644 "${REMOTE_PATH}/deploy/systemd/dommaster-crm.service" /etc/systemd/system/dommaster-crm.service
install -m 644 "${REMOTE_PATH}/deploy/systemd/dommaster-bot.service" /etc/systemd/system/dommaster-bot.service

# Останавливаем старые nohup-процессы, чтобы не было конфликта портов/polling
pkill -f 'python3 .*web_app/app.py' 2>/dev/null || true
pkill -f 'python3 app.py' 2>/dev/null || true
pkill -f 'python3 bot.py' 2>/dev/null || true
pkill -f 'python3 .*bot.py' 2>/dev/null || true
fuser -k 5001/tcp 2>/dev/null || true
sleep 2

systemctl daemon-reload
systemctl enable dommaster-crm.service dommaster-bot.service
systemctl restart dommaster-crm.service
sleep 2
systemctl restart dommaster-bot.service
sleep 2

systemctl --no-pager --full status dommaster-crm.service || true
systemctl --no-pager --full status dommaster-bot.service || true

curl -sS -o /dev/null -w "health=%{http_code}\n" --connect-timeout 5 http://127.0.0.1:5001/health || true
pgrep -af 'python3.*(app|bot)\.py' || true
EOF

echo "Готово. Управление:"
echo "  ssh -p ${PORT} ${USER_NAME}@${HOST} 'systemctl status dommaster-crm dommaster-bot'"
echo "  journalctl -u dommaster-crm -u dommaster-bot -f"
