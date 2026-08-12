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

echo "→ копируем unit-файлы и logrotate на ${USER_NAME}@${HOST}"
"${SSH_BASE[@]}" "${USER_NAME}@${HOST}" "mkdir -p '${REMOTE_PATH}/deploy/systemd' '${REMOTE_PATH}/deploy/logrotate' '${REMOTE_PATH}/logs' '${REMOTE_PATH}/scripts'"
rsync -az -e "$RSYNC_SSH" \
  "$ROOT/deploy/systemd/dommaster-crm.service" \
  "$ROOT/deploy/systemd/dommaster-bot.service" \
  "$ROOT/deploy/systemd/dommaster-healthcheck.service" \
  "$ROOT/deploy/systemd/dommaster-healthcheck.timer" \
  "${USER_NAME}@${HOST}:${REMOTE_PATH}/deploy/systemd/"
rsync -az -e "$RSYNC_SSH" \
  "$ROOT/deploy/logrotate/dommaster" \
  "${USER_NAME}@${HOST}:${REMOTE_PATH}/deploy/logrotate/"
rsync -az -e "$RSYNC_SSH" \
  "$ROOT/scripts/health_check.sh" \
  "${USER_NAME}@${HOST}:${REMOTE_PATH}/scripts/"

"${SSH_BASE[@]}" "${USER_NAME}@${HOST}" bash -s -- "$REMOTE_PATH" <<'EOF'
set -euo pipefail
REMOTE_PATH="$1"

install -m 644 "${REMOTE_PATH}/deploy/systemd/dommaster-crm.service" /etc/systemd/system/dommaster-crm.service
install -m 644 "${REMOTE_PATH}/deploy/systemd/dommaster-bot.service" /etc/systemd/system/dommaster-bot.service
install -m 644 "${REMOTE_PATH}/deploy/systemd/dommaster-healthcheck.service" /etc/systemd/system/dommaster-healthcheck.service
install -m 644 "${REMOTE_PATH}/deploy/systemd/dommaster-healthcheck.timer" /etc/systemd/system/dommaster-healthcheck.timer
install -m 644 "${REMOTE_PATH}/deploy/logrotate/dommaster" /etc/logrotate.d/dommaster
chmod +x "${REMOTE_PATH}/scripts/health_check.sh"
mkdir -p "${REMOTE_PATH}/logs" "${REMOTE_PATH}/reports/kp/stroika"
chmod 755 "${REMOTE_PATH}/logs"

# Останавливаем старые nohup-процессы, чтобы не было конфликта портов/polling
systemctl stop dommaster-bot.service 2>/dev/null || true
systemctl stop dommaster-crm.service 2>/dev/null || true
pkill -f 'python3 .*web_app/app.py' 2>/dev/null || true
pkill -f 'python3 app.py' 2>/dev/null || true
pkill -f 'python3 bot.py' 2>/dev/null || true
pkill -f 'python3 .*bot.py' 2>/dev/null || true
fuser -k 5001/tcp 2>/dev/null || true
sleep 2

systemctl daemon-reload
systemctl enable dommaster-crm.service dommaster-bot.service
systemctl enable --now dommaster-healthcheck.timer
systemctl restart dommaster-crm.service
sleep 2
systemctl restart dommaster-bot.service
sleep 2

# проверка logrotate-конфига
if command -v logrotate >/dev/null 2>&1; then
  logrotate -d /etc/logrotate.d/dommaster 2>&1 | tail -20 || true
  # принудительный dry-run уже выше; реальный rotate только по расписанию cron
else
  echo "WARN: logrotate не установлен"
fi

systemctl --no-pager --full status dommaster-crm.service || true
systemctl --no-pager --full status dommaster-bot.service || true
systemctl --no-pager --full status dommaster-healthcheck.timer || true
systemctl is-enabled dommaster-crm.service dommaster-bot.service dommaster-healthcheck.timer

curl -sS -o /dev/null -w "health=%{http_code}\n" --connect-timeout 5 http://127.0.0.1:5001/health || true
bash "${REMOTE_PATH}/scripts/health_check.sh" || true
pgrep -af 'python3.*(app|bot)\.py' || true
EOF

echo "Готово. Управление:"
echo "  ssh -p ${PORT} ${USER_NAME}@${HOST} 'systemctl status dommaster-crm dommaster-bot'"
echo "  ssh -p ${PORT} ${USER_NAME}@${HOST} 'systemctl list-timers dommaster-healthcheck.timer'"
echo "  ssh -p ${PORT} ${USER_NAME}@${HOST} 'logrotate -d /etc/logrotate.d/dommaster'"
echo "  journalctl -u dommaster-crm -u dommaster-bot -u dommaster-healthcheck -f"
