#!/usr/bin/env bash
# reset_and_load_demo.sh — бэкап БД, очистка сделок, загрузка 4 демо-протоколов.
#
# Usage:
#   ./scripts/reset_and_load_demo.sh           # на VPS по SSH (+ rsync свежих файлов)
#   ./scripts/reset_and_load_demo.sh --local   # только локальная deals.db
#   ./scripts/reset_and_load_demo.sh --no-sync # на сервере без rsync (файлы уже там)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOCAL=0
NO_SYNC=0
for arg in "$@"; do
  case "$arg" in
    --local) LOCAL=1 ;;
    --no-sync) NO_SYNC=1 ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *)
      echo "Неизвестный аргумент: $arg"
      exit 1
      ;;
  esac
done

run_local_reset() {
  local db_path="${1:-${ROOT}/web_app/deals.db}"
  echo "🔄 ПОЛНЫЙ СБРОС И ЗАГРУЗКА ДЕМО-ДАННЫХ"
  echo "========================================="
  echo "БД: ${db_path}"

  if [[ -f "$db_path" ]]; then
    local stamp
    stamp="$(date +%Y%m%d_%H%M%S)"
    cp "$db_path" "${db_path}.backup_${stamp}"
    echo "📦 Бэкап: ${db_path}.backup_${stamp}"
  fi

  python3 "${ROOT}/web_app/clear_test_data.py" --yes --db "$db_path"
  python3 "${ROOT}/web_app/load_demo_protocols.py" --yes --clear --db "$db_path"

  echo "========================================="
  echo "✅ Готово. Откройте /deals/"
}

if [[ "$LOCAL" -eq 1 ]]; then
  run_local_reset "${DEALS_DB:-$ROOT/web_app/deals.db}"
  exit 0
fi

# --- remote ---
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
REMOTE_DIR="${REMOTE_DIR:-AI_Bot_avto_KP}"
APP_URL="http://${HOST}:5001"

CTRL_DIR="${TMPDIR:-/tmp}/ai_demo_ssh_$$"
mkdir -p "$CTRL_DIR"
CTRL_PATH="${CTRL_DIR}/ctl"
cleanup_ssh() {
  ssh -O exit -o ControlPath="$CTRL_PATH" "${USER_NAME}@${HOST}" 2>/dev/null || true
  rm -rf "$CTRL_DIR"
}
trap cleanup_ssh EXIT

SSH_OPTS=(
  -p "$PORT"
  -o StrictHostKeyChecking=accept-new
  -o ConnectTimeout=20
  -o ServerAliveInterval=30
  -o ControlMaster=auto
  -o ControlPersist=120
  -o ControlPath="$CTRL_PATH"
)
SSH_BASE=(ssh "${SSH_OPTS[@]}")
RSYNC_SSH="ssh -p ${PORT} -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -o ControlMaster=auto -o ControlPersist=120 -o ControlPath=${CTRL_PATH}"

if [[ -n "$PASSWORD" ]]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "Нужен sshpass или SSH-ключ. brew install hudochenkov/sshpass/sshpass"
    exit 1
  fi
  export SSHPASS="$PASSWORD"
  SSH_BASE=(sshpass -e ssh "${SSH_OPTS[@]}")
  RSYNC_SSH="sshpass -e ssh -p ${PORT} -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -o ControlMaster=auto -o ControlPersist=120 -o ControlPath=${CTRL_PATH}"
fi

REMOTE="${USER_NAME}@${HOST}"

remote() {
  local attempt=1
  while true; do
    if "${SSH_BASE[@]}" "$REMOTE" "$@"; then
      return 0
    fi
    if [[ $attempt -ge 4 ]]; then
      echo "SSH не удался. Проверьте: ssh -p ${PORT} ${REMOTE}"
      return 1
    fi
    echo "SSH retry ${attempt}/4..."
    sleep $((attempt * 3))
    attempt=$((attempt + 1))
  done
}

echo "🔄 ПОЛНЫЙ СБРОС И ЗАГРУЗКА ДЕМО на ${REMOTE}"
echo "========================================="

REMOTE_PATH="$(remote "if [ -d ~/${REMOTE_DIR} ]; then echo ~/${REMOTE_DIR}; elif [ -d ~/AI_Auogeneration ]; then echo ~/AI_Auogeneration; else echo ~/${REMOTE_DIR}; fi" | tr -d '\r' | tail -n 1)"
echo "Каталог: ${REMOTE_PATH}"

if [[ "$NO_SYNC" -eq 0 ]]; then
  echo "📁 Синхронизация скриптов и демо-протоколов..."
  rsync -az -e "$RSYNC_SSH" \
    "${ROOT}/web_app/clear_test_data.py" \
    "${ROOT}/web_app/load_demo_protocols.py" \
    "${ROOT}/web_app/transcript_parser_local.py" \
    "${ROOT}/web_app/etalon_score.py" \
    "${ROOT}/web_app/db_utils.py" \
    "${REMOTE}:${REMOTE_PATH}/web_app/"

  rsync -az -e "$RSYNC_SSH" \
    "${ROOT}/knowledge_base/" \
    "${REMOTE}:${REMOTE_PATH}/knowledge_base/"
fi

echo "🧹 Бэкап + очистка + загрузка + рестарт..."
remote bash -s << ENDSSH
set -euo pipefail
cd '${REMOTE_PATH}'
mkdir -p web_app/uploads logs

if [[ -f web_app/deals.db ]]; then
  stamp=\$(date +%Y%m%d_%H%M%S)
  cp web_app/deals.db "web_app/deals.db.backup_\${stamp}"
  echo "📦 Бэкап: web_app/deals.db.backup_\${stamp}"
fi

pkill -f 'python3 .*web_app/app.py' 2>/dev/null || true
pkill -f 'python3 app.py' 2>/dev/null || true
sleep 1

python3 web_app/clear_test_data.py --yes --db web_app/deals.db
python3 web_app/load_demo_protocols.py --yes --clear --db web_app/deals.db

cd web_app
nohup python3 app.py > ../logs/app.log 2>&1 &
sleep 2
if pgrep -f 'python3 app.py' >/dev/null 2>&1; then
  echo "▶️ Приложение запущено"
else
  echo "⚠️ Процесс не найден — смотрите logs/app.log"
  tail -n 30 ../logs/app.log || true
fi
ENDSSH

echo "========================================="
echo "✅ Готово!"
echo "🌐 ${APP_URL}/deals/"
echo "========================================="

if curl -fsS --max-time 8 "${APP_URL}/health" >/dev/null 2>&1; then
  echo "health OK"
else
  echo "health пока не ответил снаружи — проверьте браузером"
fi
