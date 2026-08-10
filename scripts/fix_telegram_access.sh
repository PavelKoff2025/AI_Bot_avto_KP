#!/usr/bin/env bash
# fix_telegram_access.sh — доступ к api.telegram.org с VPS BlueTerbium.
#
# Проблема (reg.ru / РФ-хостинг):
#   - DNS часто отдаёт AAAA, а IPv6 на VPS unreachable
#   - официальный A-record 149.154.166.110 с VPS таймаутится
#   - рабочий DC: 149.154.167.220
#
# Решение: пин в /etc/hosts + prefer IPv4 + (опционально) рестарт бота.
#
# Usage (из корня репозитория):
#   ./scripts/fix_telegram_access.sh
#   ./scripts/fix_telegram_access.sh --no-restart
#
# SSH: BLUETERBIUM_SSH_* из .env (как в update_server.sh)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RESTART_BOT=1
for arg in "$@"; do
  case "$arg" in
    --no-restart) RESTART_BOT=0 ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
    *)
      echo "Неизвестный аргумент: $arg"
      exit 1
      ;;
  esac
done

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
TG_IP="${TELEGRAM_API_IP:-149.154.167.220}"

SSH_BASE=(ssh -T -p "$PORT" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=25)
if [[ -n "$PASSWORD" ]]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "Нужен sshpass или SSH-ключ. brew install hudochenkov/sshpass/sshpass"
    exit 1
  fi
  export SSHPASS="$PASSWORD"
  SSH_BASE=(sshpass -e "${SSH_BASE[@]}")
fi

echo "→ ${USER_NAME}@${HOST}:${PORT}"
echo "→ pin api.telegram.org → ${TG_IP}"

"${SSH_BASE[@]}" "${USER_NAME}@${HOST}" bash -s -- "$TG_IP" "$REMOTE_PATH" "$RESTART_BOT" <<'EOF'
set -euo pipefail
TG_IP="$1"
REMOTE_PATH="$2"
RESTART_BOT="$3"

# Не затираем /etc/hosts целиком — только строка api.telegram.org
if [[ ! -s /etc/hosts ]]; then
  cat > /etc/hosts <<'HOSTS'
127.0.0.1       localhost
127.0.1.1       cv7802191.novalocal cv7802191
::1             localhost ip6-localhost ip6-loopback
ff02::1         ip6-allnodes
ff02::2         ip6-allrouters
HOSTS
fi

tmp="$(mktemp)"
grep -vE '[[:space:]]api\.telegram\.org([[:space:]]|$)' /etc/hosts > "$tmp" || true
printf '%s api.telegram.org\n' "$TG_IP" >> "$tmp"
cp -a /etc/hosts "/etc/hosts.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
cat "$tmp" > /etc/hosts
rm -f "$tmp"

if [[ -f /etc/gai.conf ]] && ! grep -qE '^precedence ::ffff:0:0/96[[:space:]]+100' /etc/gai.conf; then
  echo 'precedence ::ffff:0:0/96  100' >> /etc/gai.conf
fi

echo "resolve: $(getent hosts api.telegram.org | tr '\n' ' ')"
curl -sS -o /dev/null -w "curl api.telegram.org → HTTP %{http_code} ip=%{remote_ip} time=%{time_total}s\n" \
  --connect-timeout 10 --max-time 20 https://api.telegram.org/

if [[ "$RESTART_BOT" == "1" && -f "${REMOTE_PATH}/bot.py" ]]; then
  cd "$REMOTE_PATH"
  mkdir -p logs
  pkill -f 'python3 bot.py' 2>/dev/null || true
  pkill -f 'python3 .*bot.py' 2>/dev/null || true
  sleep 1
  nohup python3 bot.py >> logs/bot.log 2>&1 &
  sleep 2
  if pgrep -f 'python3 bot.py' >/dev/null 2>&1; then
    echo "bot: OK ($(pgrep -f 'python3 bot.py' | head -1))"
  else
    echo "bot: FAIL — tail logs/bot.log:"
    tail -n 30 logs/bot.log || true
    exit 1
  fi
fi
EOF

echo "Готово."
