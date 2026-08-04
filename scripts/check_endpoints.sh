#!/usr/bin/env bash
# Проверка HTTP API эндпоинтов (Flask / Go).
#
# Usage:
#   ./scripts/check_endpoints.sh
#   BASE_URL=http://127.0.0.1:5001 ./scripts/check_endpoints.sh
#   FLASK_API_TOKEN=secret ./scripts/check_endpoints.sh
#   ./scripts/check_endpoints.sh --quick   # health + validation + auth
#   ./scripts/check_endpoints.sh --full    # + OpenAI (report/КП с ИР)
#
# Env:
#   BASE_URL          по умолчанию http://127.0.0.1:5001 (Docker compose)
#   FLASK_API_TOKEN   / API_TOKEN — заголовок X-API-Token
#   SAMPLE_FILE       путь к .txt (по умолчанию sample_dialog.txt)
#   TIMEOUT_SEC       таймаут curl для тяжёлых запросов (по умолчанию 600)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

load_env_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" == export\ * ]] && line="${line#export }"
    [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue
    local key="${line%%=*}"
    local val="${line#*=}"
    # не перезаписываем уже заданные в окружении
    if [[ -z "${!key+x}" ]]; then
      export "$key=$val"
    fi
  done < "$file"
}

load_env_file "$ROOT/.env"

BASE_URL="${BASE_URL:-http://127.0.0.1:5001}"
BASE_URL="${BASE_URL%/}"
TOKEN="${FLASK_API_TOKEN:-${API_TOKEN:-}}"
SAMPLE_FILE="${SAMPLE_FILE:-$ROOT/sample_dialog.txt}"
TIMEOUT_SEC="${TIMEOUT_SEC:-600}"
MODE="default"

for arg in "$@"; do
  case "$arg" in
    --quick) MODE="quick" ;;
    --full) MODE="full" ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
  esac
done

AUTH_ARGS=()
if [[ -n "$TOKEN" ]]; then
  AUTH_ARGS=(-H "X-API-Token: ${TOKEN}")
fi

PASS=0
FAIL=0
SKIP=0

green() { printf '\033[32m%s\033[0m\n' "$*"; }
red() { printf '\033[31m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
info() { printf '\033[36m%s\033[0m\n' "$*"; }

assert_http() {
  local name="$1"
  local expected="$2"
  local got="${3:-000}"
  if [[ "$got" == "$expected" ]]; then
    green "PASS  [${got}] ${name}"
    PASS=$((PASS + 1))
  else
    red "FAIL  [${got} != ${expected}] ${name}"
    FAIL=$((FAIL + 1))
  fi
}

skip() {
  yellow "SKIP  $*"
  SKIP=$((SKIP + 1))
}

http_code() {
  # Всегда печатает код (или 000), даже если curl не смог соединиться
  local out
  out="$(curl -sS -o "$1" -w '%{http_code}' --connect-timeout 3 "${@:2}" 2>/dev/null || true)"
  if [[ -z "$out" ]]; then
    echo "000"
  else
    echo "$out"
  fi
}

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

info "=== API check ==="
info "BASE_URL=$BASE_URL  MODE=$MODE  token=$([ -n "$TOKEN" ] && echo set || echo empty)"
if [[ -n "${FLASK_API_TOKEN:-}" && -f "$ROOT/.env" ]] && grep -q '^FLASK_API_TOKEN=' "$ROOT/.env"; then
  env_tok="$(grep '^FLASK_API_TOKEN=' "$ROOT/.env" | head -1 | cut -d= -f2-)"
  if [[ -n "$env_tok" && "$TOKEN" != "$env_tok" ]]; then
    yellow "WARN  FLASK_API_TOKEN в shell != значению в .env"
    yellow "      Контейнер читает .env. Сделайте: unset FLASK_API_TOKEN"
    yellow "      или export FLASK_API_TOKEN=<тот же, что в .env>"
  fi
fi
echo

# --- 1. GET /health ---
code="$(http_code "$tmpdir/health.json" "$BASE_URL/health")"
if [[ "$code" == "000" ]]; then
  red "FAIL  cannot connect to $BASE_URL"
  red "      Сначала запустите: docker compose up -d --build go-api"
  FAIL=$((FAIL + 1))
  echo
  info "=== summary ==="
  echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
  exit 1
fi
assert_http "GET /health" "200" "$code"
if [[ "$code" == "200" ]] && grep -q '"status"' "$tmpdir/health.json" 2>/dev/null; then
  green "PASS  body /health contains status"
  PASS=$((PASS + 1))
elif [[ "$code" == "200" ]]; then
  red "FAIL  body /health unexpected: $(cat "$tmpdir/health.json")"
  FAIL=$((FAIL + 1))
fi

# --- 2. POST /api/report empty → 400 ---
code="$(http_code "$tmpdir/report_empty.json" \
  -X POST "$BASE_URL/api/report" \
  "${AUTH_ARGS[@]+"${AUTH_ARGS[@]}"}" \
  -H 'Content-Type: application/json' \
  -d '{"text":"","type":"client"}')"
assert_http "POST /api/report empty text -> 400" "400" "$code"

# --- 3. POST /api/report bad type → 400 ---
code="$(http_code "$tmpdir/report_badtype.json" \
  -X POST "$BASE_URL/api/report" \
  "${AUTH_ARGS[@]+"${AUTH_ARGS[@]}"}" \
  -H 'Content-Type: application/json' \
  -d '{"text":"короткий тест диалога про дом","type":"nope"}')"
assert_http "POST /api/report bad type -> 400" "400" "$code"

# --- 4. Auth without token ---
if [[ -n "$TOKEN" ]]; then
  code="$(http_code "$tmpdir/unauth.json" \
    -X POST "$BASE_URL/api/kp" \
    -H 'Content-Type: application/json' \
    -d '{"with_fz":false,"with_engineering":false}')"
  assert_http "POST /api/kp without token -> 401" "401" "$code"
else
  skip "auth check (FLASK_API_TOKEN не задан)"
fi
if [[ "$MODE" == "quick" ]]; then
  echo
  info "=== summary (quick) ==="
  echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
  [[ "$FAIL" -eq 0 ]]
  exit $?
fi

# --- 5. Light KP (no AI) ---
info "--- POST /api/kp (без ИР) ---"
code="$(curl -sS -o "$tmpdir/kp.json" -w '%{http_code}' \
  --max-time "$TIMEOUT_SEC" \
  -X POST "$BASE_URL/api/kp" \
  "${AUTH_ARGS[@]+"${AUTH_ARGS[@]}"}" \
  -H 'Content-Type: application/json' \
  -d '{"with_fz":false,"with_engineering":false,"client_name":"Тест API"}' || echo 000)"
assert_http "POST /api/kp basic" "200" "$code"
if [[ "$code" == "200" ]] && grep -q '"files"' "$tmpdir/kp.json"; then
  green "PASS  /api/kp response has files"
  PASS=$((PASS + 1))
  info "      files: $(tr '\n' ' ' <"$tmpdir/kp.json")"
elif [[ "$code" == "200" ]]; then
  red "FAIL  /api/kp body: $(cat "$tmpdir/kp.json")"
  FAIL=$((FAIL + 1))
else
  red "      body: $(cat "$tmpdir/kp.json" 2>/dev/null || true)"
fi

if [[ "$MODE" != "full" ]]; then
  echo
  yellow "Полный прогон с OpenAI: $0 --full"
  info "=== summary ==="
  echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
  [[ "$FAIL" -eq 0 ]]
  exit $?
fi

if [[ ! -f "$SAMPLE_FILE" ]]; then
  red "FAIL  SAMPLE_FILE not found: $SAMPLE_FILE"
  exit 1
fi

python3 - "$SAMPLE_FILE" "$tmpdir/report_payload.json" <<'PY'
import json, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")[:12000]
Path(sys.argv[2]).write_text(
    json.dumps({"text": text, "type": "client"}, ensure_ascii=False),
    encoding="utf-8",
)
PY

info "--- POST /api/report JSON type=client ---"
code="$(curl -sS -o "$tmpdir/report_client.pdf" -w '%{http_code}' \
  --max-time "$TIMEOUT_SEC" \
  -X POST "$BASE_URL/api/report" \
  "${AUTH_ARGS[@]+"${AUTH_ARGS[@]}"}" \
  -H 'Content-Type: application/json' \
  --data-binary @"$tmpdir/report_payload.json" || echo 000)"
assert_http "POST /api/report type=client → PDF" "200" "$code"
if [[ "$code" == "200" ]]; then
  if head -c 5 "$tmpdir/report_client.pdf" | grep -q '%PDF'; then
    green "PASS  response is PDF ($(wc -c <"$tmpdir/report_client.pdf" | tr -d ' ') bytes)"
    PASS=$((PASS + 1))
  else
    red "FAIL  expected PDF, got: $(head -c 160 "$tmpdir/report_client.pdf")"
    FAIL=$((FAIL + 1))
  fi
fi

info "--- POST /api/report multipart type=engineering ---"
code="$(curl -sS -o "$tmpdir/report_ir.pdf" -w '%{http_code}' \
  --max-time "$TIMEOUT_SEC" \
  -X POST "$BASE_URL/api/report" \
  "${AUTH_ARGS[@]+"${AUTH_ARGS[@]}"}" \
  -F "file=@${SAMPLE_FILE};type=text/plain" \
  -F "type=engineering" || echo 000)"
assert_http "POST /api/report multipart engineering → PDF" "200" "$code"

python3 - "$SAMPLE_FILE" "$tmpdir/kp_payload.json" <<'PY'
import json, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")[:12000]
Path(sys.argv[2]).write_text(
    json.dumps({
        "with_fz": False,
        "with_engineering": True,
        "client_name": "Тест API",
        "text": text,
    }, ensure_ascii=False),
    encoding="utf-8",
)
PY

info "--- POST /api/kp with_engineering=true ---"
code="$(curl -sS -o "$tmpdir/kp_full.json" -w '%{http_code}' \
  --max-time "$TIMEOUT_SEC" \
  -X POST "$BASE_URL/api/kp" \
  "${AUTH_ARGS[@]+"${AUTH_ARGS[@]}"}" \
  -H 'Content-Type: application/json' \
  --data-binary @"$tmpdir/kp_payload.json" || echo 000)"
assert_http "POST /api/kp with engineering" "200" "$code"

echo
info "=== summary (full) ==="
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
[[ "$FAIL" -eq 0 ]]
