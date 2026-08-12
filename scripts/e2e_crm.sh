#!/usr/bin/env bash
# e2e_crm.sh — unit + live smoke CRM.
#
# Usage:
#   ./scripts/e2e_crm.sh
#   ./scripts/e2e_crm.sh --unit-only
#   CRM_URL=http://194.67.103.144:5001 ./scripts/e2e_crm.sh --live-only
#
# Env:
#   CRM_URL   (default http://194.67.103.144:5001)
#   CRM_USER / CRM_PASS  для live login smoke (опционально)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

UNIT=1
LIVE=1
for arg in "$@"; do
  case "$arg" in
    --unit-only) LIVE=0 ;;
    --live-only) UNIT=0 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
  esac
done

CRM_URL="${CRM_URL:-${CRM_PUBLIC_URL:-http://194.67.103.144:5001}}"
CRM_URL="${CRM_URL%/}"

PASS=0
FAIL=0
green() { printf '\033[32m%s\033[0m\n' "$*"; }
red() { printf '\033[31m%s\033[0m\n' "$*"; }
info() { printf '\033[36m%s\033[0m\n' "$*"; }

ok() { green "PASS  $*"; PASS=$((PASS + 1)); }
bad() { red "FAIL  $*"; FAIL=$((FAIL + 1)); }

if [[ "$UNIT" -eq 1 ]]; then
  info "=== unit / e2e smoke (Flask test client) ==="
  if (
    cd web_app
    PYTHONPATH=..:$(pwd) python3 -m unittest discover -s tests -v
  ); then
    ok "unittest suite"
  else
    bad "unittest suite"
  fi
fi

if [[ "$LIVE" -eq 1 ]]; then
  info "=== live: $CRM_URL ==="
  for path in /health '/health?deep=1' /login; do
    code=000
    for try in 1 2 3 4 5; do
      code=$(curl -sS -o "/tmp/e2e_${path//\//_}.json" -w '%{http_code}' \
        --connect-timeout 10 --max-time 25 "$CRM_URL$path" 2>/dev/null || echo 000)
      [[ "$code" != "000" && "$code" != "000000" ]] && break
      sleep $((try * 2))
    done
    if [[ "$path" == /health || "$path" == '/health?deep=1' ]]; then
      if [[ "$code" == "200" ]]; then ok "GET $path → $code"; else bad "GET $path → $code"; fi
    else
      if [[ "$code" == "200" ]]; then ok "GET $path → $code"; else bad "GET $path → $code"; fi
    fi
  done

  code=000
  for try in 1 2 3 4 5; do
    code=$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 10 --max-time 20 \
      "$CRM_URL/help" 2>/dev/null || echo 000)
    [[ "$code" != "000" && "$code" != "000000" ]] && break
    sleep $((try * 2))
  done
  # без сессии ожидаем редирект на login
  if [[ "$code" == "302" || "$code" == "301" || "$code" == "200" ]]; then
    ok "GET /help (auth gate) → $code"
  else
    bad "GET /help → $code"
  fi

  if [[ -n "${CRM_USER:-}" && -n "${CRM_PASS:-}" ]]; then
    jar=$(mktemp)
    code=000
    for try in 1 2 3 4 5; do
      code=$(curl -sS -c "$jar" -b "$jar" -o /dev/null -w '%{http_code}' \
        --connect-timeout 10 --max-time 25 \
        -X POST "$CRM_URL/login" \
        -d "username=${CRM_USER}&password=${CRM_PASS}" 2>/dev/null || echo 000)
      [[ "$code" == "302" || "$code" == "303" ]] && break
      sleep $((try * 2))
    done
    if [[ "$code" == "302" || "$code" == "303" ]]; then
      ok "POST /login → $code"
      code=000
      for try in 1 2 3 4 5; do
        code=$(curl -sS -c "$jar" -b "$jar" -o /tmp/e2e_deals.html -w '%{http_code}' \
          --connect-timeout 10 --max-time 25 "$CRM_URL/deals/" 2>/dev/null || echo 000)
        [[ "$code" == "200" ]] && break
        sleep $((try * 2))
      done
      if [[ "$code" == "200" ]] && grep -qi 'сделок\|deal\|клиент' /tmp/e2e_deals.html; then
        ok "GET /deals/ (session) → $code"
      else
        bad "GET /deals/ → $code"
      fi
      code=$(curl -sS -c "$jar" -b "$jar" -o /dev/null -w '%{http_code}' \
        --connect-timeout 10 --max-time 20 "$CRM_URL/help" 2>/dev/null || echo 000)
      if [[ "$code" == "200" ]]; then
        ok "GET /help (session) → $code"
      else
        bad "GET /help (session) → $code"
      fi
    else
      bad "POST /login → $code"
    fi
    rm -f "$jar"
  else
    info "SKIP live login (задайте CRM_USER и CRM_PASS)"
  fi

  if [[ -f scripts/health_check.sh ]]; then
    info "=== health_check on BlueTerbium (SSH) ==="
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
    if [[ -n "${BLUETERBIUM_SSH_HOST:-}" ]]; then
      export SSHPASS="${BLUETERBIUM_SSH_PASSWORD:-}"
      PORT="${BLUETERBIUM_SSH_PORT:-2222}"
      USER_NAME="${BLUETERBIUM_SSH_USER:-root}"
      SSH=(ssh -T -p "$PORT" -o ConnectTimeout=25 -o StrictHostKeyChecking=accept-new -o RequestTTY=no)
      if [[ -n "${SSHPASS:-}" ]] && command -v sshpass >/dev/null; then
        SSH=(sshpass -e "${SSH[@]}")
      fi
      remote_ok=0
      for try in 1 2 3 4 5 6; do
        if "${SSH[@]}" "${USER_NAME}@${BLUETERBIUM_SSH_HOST}" \
          'bash /root/AI_Bot_avto_KP/scripts/health_check.sh'; then
          remote_ok=1
          break
        fi
        sleep $((try * 2))
      done
      if [[ "$remote_ok" -eq 1 ]]; then
        ok "health_check.sh (remote)"
      else
        bad "health_check.sh (remote)"
      fi
    else
      info "SKIP remote health_check (нет BLUETERBIUM_SSH_*)"
    fi
  fi
fi

echo
info "=== summary ==="
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]]
