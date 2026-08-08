#!/usr/bin/env bash
# update_server.sh — быстрый деплой web_app CRM на VPS (BlueTerbium).
#
# Usage (из корня репозитория):
#   ./scripts/update_server.sh
#   ./scripts/update_server.sh --dry-run
#   ./scripts/update_server.sh --pull-only   # только git pull на сервере, без rsync
#
# SSH берётся из .env:
#   BLUETERBIUM_SSH_HOST / PORT / USER / PASSWORD (пароль опционален, лучше ключ)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DRY_RUN=0
PULL_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --pull-only) PULL_ONLY=1 ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *)
      echo "Неизвестный аргумент: $arg"
      exit 1
      ;;
  esac
done

if [[ -f .env ]]; then
  # Подхватываем только BLUETERBIUM_SSH_* из .env
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

CTRL_DIR="${TMPDIR:-/tmp}/ai_auogen_ssh_$$"
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
    echo "В .env задан BLUETERBIUM_SSH_PASSWORD, но sshpass не установлен."
    echo "Установите: brew install hudochenkov/sshpass/sshpass"
    echo "Или настройте SSH-ключ и уберите пароль из .env."
    exit 1
  fi
  export SSHPASS="$PASSWORD"
  SSH_BASE=(sshpass -e ssh "${SSH_OPTS[@]}")
  RSYNC_SSH="sshpass -e ssh -p ${PORT} -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -o ControlMaster=auto -o ControlPersist=120 -o ControlPath=${CTRL_PATH}"
fi

REMOTE="${USER_NAME}@${HOST}"

echo "=== Деплой CRM на ${REMOTE}:${REMOTE_DIR} ==="
echo "URL: ${APP_URL}"
echo "SSH порт: ${PORT}"

remote() {
  local attempt=1
  local max=4
  while true; do
    if "${SSH_BASE[@]}" "$REMOTE" "$@"; then
      return 0
    fi
    local rc=$?
    if [[ $attempt -ge $max ]]; then
      echo "SSH ошибка после ${max} попыток (код $rc)."
      echo "Проверьте: ssh -p ${PORT} ${REMOTE}"
      echo "Если Connection refused — порт ${PORT} закрыт/sshd лежит, или IP в fail2ban."
      return "$rc"
    fi
    echo "SSH не удался (попытка ${attempt}/${max}), ждём $((attempt * 3))с..."
    sleep $((attempt * 3))
    attempt=$((attempt + 1))
  done
}

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] ssh ok?"
  remote "echo connected && ls -d ~/${REMOTE_DIR} 2>/dev/null || ls -d ~/*Bot* 2>/dev/null || true"
  exit 0
fi

echo "1/4 Проверка SSH (одно соединение)..."
REMOTE_PATH="$(remote "echo ok; if [ -d ~/${REMOTE_DIR} ]; then echo ~/${REMOTE_DIR}; elif [ -d ~/AI_Auogeneration ]; then echo ~/AI_Auogeneration; else echo ~/${REMOTE_DIR}; fi" | tr -d '\r' | tail -n 1)"
echo "Каталог на сервере: ${REMOTE_PATH}"

if [[ "$PULL_ONLY" -eq 1 ]]; then
  echo "2/4 git pull на сервере..."
  remote "cd '${REMOTE_PATH}' && git pull --ff-only"
else
  echo "2/4 Синхронизация файлов (rsync)..."
  if ! command -v rsync >/dev/null 2>&1; then
    echo "rsync не найден — ставьте rsync или запускайте с --pull-only"
    exit 1
  fi
  rsync -az --delete \
    -e "$RSYNC_SSH" \
    --exclude '.env' \
    --exclude '.env.*' \
    --exclude 'deals.db' \
    --exclude 'deals.db.*' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    --exclude 'uploads/' \
    --exclude 'static/uploads/' \
    "${ROOT}/web_app/" \
    "${REMOTE}:${REMOTE_PATH}/web_app/"

  # Эталон и ключевые утилиты (если нужны на сервере рядом с CRM)
  rsync -az \
    -e "$RSYNC_SSH" \
    --exclude '.DS_Store' \
    "${ROOT}/knowledge_base/" \
    "${REMOTE}:${REMOTE_PATH}/knowledge_base/" 2>/dev/null || true
fi

echo "3/4 Бэкап БД + перезапуск..."
remote bash -s << ENDSSH
set -euo pipefail
cd '${REMOTE_PATH}'

mkdir -p web_app/uploads logs

if [[ -f web_app/deals.db ]]; then
  stamp=\$(date +%Y%m%d_%H%M%S)
  cp web_app/deals.db "web_app/deals.db.backup_\${stamp}"
  echo "Бэкап: web_app/deals.db.backup_\${stamp}"
else
  echo "deals.db пока нет — пропускаем бэкап"
fi

echo "Останавливаем старый процесс..."
pkill -f 'python3 .*web_app/app.py' 2>/dev/null || true
pkill -f 'python3 app.py' 2>/dev/null || true
sleep 1

# Зависимости web_app (тихо, если уже стоят)
if command -v pip3 >/dev/null 2>&1; then
  pip3 install -q flask werkzeug python-docx PyPDF2 2>/dev/null || true
fi

echo "Запуск web_app/app.py..."
cd web_app
nohup python3 app.py > ../logs/app.log 2>&1 &
sleep 2

if pgrep -f 'python3 app.py' >/dev/null 2>&1 || pgrep -f 'web_app/app.py' >/dev/null 2>&1; then
  echo "Процесс запущен"
else
  echo "ВНИМАНИЕ: процесс не найден, смотрите logs/app.log"
  tail -n 40 ../logs/app.log || true
  exit 1
fi
ENDSSH

echo "4/4 Проверка /health..."
if curl -fsS --max-time 8 "${APP_URL}/health" >/dev/null 2>&1; then
  echo "health OK → ${APP_URL}/health"
else
  echo "health пока не ответил (firewall/порт/старт). Проверьте: ${APP_URL}"
fi

echo ""
echo "Деплой завершён."
echo "CRM: ${APP_URL}/deals/"
echo "Логи на сервере: ${REMOTE_PATH}/logs/app.log"
