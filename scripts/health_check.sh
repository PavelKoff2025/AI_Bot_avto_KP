#!/usr/bin/env bash
# health_check.sh — мониторинг CRM / бота / NL-прокси / Telegram.
#
# Usage (на VPS или локально):
#   ./scripts/health_check.sh
#   ./scripts/health_check.sh --alert          # при FAIL — Telegram менеджерам
#   ./scripts/health_check.sh --json           # машинный вывод
#   CRM_URL=http://127.0.0.1:5001 ./scripts/health_check.sh
#
# Env (из .env или окружения):
#   CRM_URL / CRM_PUBLIC_URL   URL CRM (по умолчанию http://127.0.0.1:5001)
#   OPENAI_PROXY               HTTP-прокси для OpenAI
#   TELEGRAM_BOT_TOKEN         проверка getMe
#   TELEGRAM_ALLOWED_IDS       куда слать алерты (первый id, или HEALTH_ALERT_CHAT_ID)
#   HEALTH_ALERT_CHAT_ID       явный chat_id для алертов
#   HEALTH_ALERT_COOLDOWN_MIN  антиспам алертов, минут (по умолчанию 30)
#   HEALTH_STATE_DIR           каталог state-файлов (по умолчанию logs/)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ALERT=0
JSON=0
for arg in "$@"; do
  case "$arg" in
    --alert) ALERT=1 ;;
    --json) JSON=1 ;;
    -h|--help)
      sed -n '2,22p' "$0"
      exit 0
      ;;
  esac
done

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
    if [[ -z "${!key+x}" ]]; then
      export "$key=$val"
    fi
  done < "$file"
}

load_env_file "$ROOT/.env"
load_env_file "$ROOT/web_app/.env"

CRM_URL="${CRM_URL:-${CRM_PUBLIC_URL:-http://127.0.0.1:5001}}"
CRM_URL="${CRM_URL%/}"
STATE_DIR="${HEALTH_STATE_DIR:-$ROOT/logs}"
mkdir -p "$STATE_DIR"
STATE_FILE="$STATE_DIR/healthcheck.state"
LOG_FILE="$STATE_DIR/healthcheck.log"
RESULTS_FILE="$STATE_DIR/.health_results.tsv"
: > "$RESULTS_FILE"
COOLDOWN_MIN="${HEALTH_ALERT_COOLDOWN_MIN:-30}"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

PASS=0
FAIL=0
WARN=0

green() { [[ "$JSON" -eq 1 ]] || printf '\033[32m%s\033[0m\n' "$*"; }
red()   { [[ "$JSON" -eq 1 ]] || printf '\033[31m%s\033[0m\n' "$*"; }
yellow(){ [[ "$JSON" -eq 1 ]] || printf '\033[33m%s\033[0m\n' "$*"; }
info()  { [[ "$JSON" -eq 1 ]] || printf '\033[36m%s\033[0m\n' "$*"; }

record() {
  local status="$1"
  local name="$2"
  local detail="${3:-}"
  printf '%s\t%s\t%s\n' "$status" "$name" "$detail" >> "$RESULTS_FILE"
  case "$status" in
    PASS) PASS=$((PASS + 1)); green "PASS  ${name}${detail:+ — $detail}" ;;
    FAIL) FAIL=$((FAIL + 1)); red   "FAIL  ${name}${detail:+ — $detail}" ;;
    WARN) WARN=$((WARN + 1)); yellow "WARN  ${name}${detail:+ — $detail}" ;;
  esac
}

http_code() {
  local out
  out="$(curl -sS -o "$1" -w '%{http_code}' --connect-timeout 5 --max-time 20 "${@:2}" 2>/dev/null || true)"
  [[ -n "$out" ]] && echo "$out" || echo "000"
}

# --- 1. systemd units (если доступны) ---
if command -v systemctl >/dev/null 2>&1; then
  for unit in dommaster-crm dommaster-bot; do
    if systemctl cat "${unit}.service" >/dev/null 2>&1 \
      || [[ -f "/etc/systemd/system/${unit}.service" ]]; then
      state="$(systemctl show -p ActiveState --value "$unit" 2>/dev/null || echo unknown)"
      # краткий retry на переходных состояниях после restart
      if [[ "$state" == "activating" || "$state" == "reloading" ]]; then
        sleep 2
        state="$(systemctl show -p ActiveState --value "$unit" 2>/dev/null || echo unknown)"
      fi
      if [[ "$state" == "active" ]]; then
        record PASS "systemd:${unit}" "active"
      elif [[ "$state" == "activating" ]]; then
        record WARN "systemd:${unit}" "activating"
      else
        record FAIL "systemd:${unit}" "$state"
      fi
    else
      record WARN "systemd:${unit}" "unit not installed"
    fi
  done
else
  record WARN "systemd" "systemctl unavailable"
fi

# --- 2. CRM /health и /health?deep=1 ---
code="$(http_code "$STATE_DIR/.health.json" "$CRM_URL/health")"
if [[ "$code" == "200" ]]; then
  record PASS "crm:/health" "$CRM_URL → $code"
else
  record FAIL "crm:/health" "$CRM_URL → $code"
fi

code="$(http_code "$STATE_DIR/.health_deep.json" "$CRM_URL/health?deep=1")"
if [[ "$code" == "200" ]]; then
  db="$(python3 -c "import json; d=json.load(open(r'$STATE_DIR/.health_deep.json')); print((d.get('checks') or {}).get('db','?'))" 2>/dev/null || echo '?')"
  record PASS "crm:/health?deep=1" "db=$db"
elif [[ "$code" == "503" ]]; then
  record FAIL "crm:/health?deep=1" "degraded $(head -c 200 "$STATE_DIR/.health_deep.json" 2>/dev/null || true)"
else
  record FAIL "crm:/health?deep=1" "code=$code"
fi

# --- 3. OpenAI через прокси (401 на фейковом ключе = сеть жива) ---
PROXY="${OPENAI_PROXY:-${HTTPS_PROXY:-${HTTP_PROXY:-}}}"
if [[ -n "$PROXY" ]]; then
  code="$(curl -sS -o "$STATE_DIR/.openai.json" -w '%{http_code}' \
    --connect-timeout 12 --max-time 35 \
    -x "$PROXY" \
    -H 'Authorization: Bearer sk-healthcheck' \
    https://api.openai.com/v1/models 2>/dev/null || echo 000)"
  if [[ "$code" == "401" || "$code" == "200" ]]; then
    record PASS "openai:via-proxy" "http=$code"
  else
    record FAIL "openai:via-proxy" "http=$code host=${PROXY##*@}"
  fi
else
  record WARN "openai:via-proxy" "OPENAI_PROXY not set"
fi

# --- 4. Telegram Bot API getMe ---
TOKEN="${TELEGRAM_BOT_TOKEN:-}"
if [[ -n "$TOKEN" && "$TOKEN" != "your_telegram_bot_token_here" ]]; then
  code="$(http_code "$STATE_DIR/.tg_me.json" "https://api.telegram.org/bot${TOKEN}/getMe")"
  if [[ "$code" == "200" ]] && grep -q '"ok":true' "$STATE_DIR/.tg_me.json" 2>/dev/null; then
    uname="$(python3 -c "import json; d=json.load(open(r'$STATE_DIR/.tg_me.json')); print(d.get('result',{}).get('username','?'))" 2>/dev/null || echo '?')"
    record PASS "telegram:getMe" "@${uname}"
  else
    record FAIL "telegram:getMe" "http=$code"
  fi
else
  record WARN "telegram:getMe" "TELEGRAM_BOT_TOKEN not set"
fi

# --- summary ---
SUMMARY="health ${TS} PASS=${PASS} FAIL=${FAIL} WARN=${WARN}"
{
  echo "$SUMMARY"
  sed 's/^/  /' "$RESULTS_FILE"
} >> "$LOG_FILE"

if [[ "$JSON" -eq 1 ]]; then
  PASS="$PASS" FAIL="$FAIL" WARN="$WARN" TS="$TS" CRM_URL="$CRM_URL" RESULTS_FILE="$RESULTS_FILE" python3 - <<'PY'
import json, os
rows = []
with open(os.environ["RESULTS_FILE"], encoding="utf-8") as f:
    for line in f:
        parts = line.rstrip("\n").split("\t", 2)
        while len(parts) < 3:
            parts.append("")
        rows.append({"status": parts[0], "name": parts[1], "detail": parts[2]})
print(json.dumps({
    "ts": os.environ["TS"],
    "crm_url": os.environ["CRM_URL"],
    "pass": int(os.environ["PASS"]),
    "fail": int(os.environ["FAIL"]),
    "warn": int(os.environ["WARN"]),
    "ok": int(os.environ["FAIL"]) == 0,
    "checks": rows,
}, ensure_ascii=False, indent=2))
PY
else
  echo
  info "=== summary ==="
  echo "$SUMMARY"
fi

# --- alert ---
maybe_alert() {
  [[ "$ALERT" -eq 1 ]] || return 0
  [[ "$FAIL" -gt 0 ]] || return 0

  local chat="${HEALTH_ALERT_CHAT_ID:-}"
  if [[ -z "$chat" ]]; then
    chat="$(printf '%s' "${TELEGRAM_ALLOWED_IDS:-}" | tr ',;' '\n' | sed 's/[[:space:]]//g' | grep -E '^[0-9]+$' | head -1 || true)"
  fi
  if [[ -z "$chat" || -z "$TOKEN" || "$TOKEN" == "your_telegram_bot_token_here" ]]; then
    yellow "ALERT skip: нет HEALTH_ALERT_CHAT_ID / TELEGRAM_ALLOWED_IDS / TOKEN"
    return 0
  fi

  local now last
  now="$(date +%s)"
  if [[ -f "$STATE_FILE" ]]; then
    last="$(awk -F= '/^last_alert_epoch=/{print $2}' "$STATE_FILE" | tail -1)"
    if [[ -n "${last:-}" ]] && [[ $((now - last)) -lt $((COOLDOWN_MIN * 60)) ]]; then
      yellow "ALERT cooldown ${COOLDOWN_MIN}m — skip"
      return 0
    fi
  fi

  TOKEN="$TOKEN" CHAT="$chat" TS="$TS" CRM_URL="$CRM_URL" FAIL="$FAIL" RESULTS_FILE="$RESULTS_FILE" \
  STATE_DIR="$STATE_DIR" STATE_FILE="$STATE_FILE" NOW="$now" python3 - <<'PY'
import json, os, urllib.parse, urllib.request
rows = []
with open(os.environ["RESULTS_FILE"], encoding="utf-8") as f:
    for line in f:
        parts = line.rstrip("\n").split("\t", 2)
        while len(parts) < 3:
            parts.append("")
        if parts[0] == "FAIL":
            rows.append(f"• {parts[1]}: {parts[2]}")
text = (
    f"🚨 DomMaster health FAIL={os.environ['FAIL']}\n"
    f"{os.environ['TS']}\n"
    f"CRM: {os.environ['CRM_URL']}\n"
    + "\n".join(rows)
)[:3500]
body = urllib.parse.urlencode({
    "chat_id": os.environ["CHAT"],
    "text": text,
    "disable_web_page_preview": "1",
}).encode()
url = f"https://api.telegram.org/bot{os.environ['TOKEN']}/sendMessage"
out = os.path.join(os.environ["STATE_DIR"], ".tg_alert.json")
try:
    with urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"), timeout=25) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
except Exception as exc:  # noqa: BLE001
    open(out, "w", encoding="utf-8").write(str(exc))
    raise SystemExit(f"ALERT send failed: {exc}")
open(out, "w", encoding="utf-8").write(raw)
ok = '"ok":true' in raw.replace(" ", "").lower() or (json.loads(raw).get("ok") is True)
if not ok:
    raise SystemExit(f"ALERT rejected: {raw[:200]}")
with open(os.environ["STATE_FILE"], "w", encoding="utf-8") as sf:
    sf.write(f"last_alert_epoch={os.environ['NOW']}\nlast_alert_ts={os.environ['TS']}\n")
print(f"ALERT sent → chat {os.environ['CHAT']}")
PY
}

maybe_alert
[[ "$FAIL" -eq 0 ]]
