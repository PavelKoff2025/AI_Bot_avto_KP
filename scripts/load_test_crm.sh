#!/usr/bin/env bash
# load_test_crm.sh — лёгкий нагрузочный прогон /health (и опционально /login).
#
# Usage:
#   ./scripts/load_test_crm.sh
#   CRM_URL=http://127.0.0.1:5001 CONCURRENCY=20 REQUESTS=200 ./scripts/load_test_crm.sh
#   ./scripts/load_test_crm.sh --remote   # гоняет с BlueTerbium на localhost:5001
#
# Env:
#   CRM_URL       default http://194.67.103.144:5001
#   CONCURRENCY   параллельных воркеров (default 10)
#   REQUESTS      всего запросов (default 100)
#   PATHS         пробел-разделённый список (default "/health /health?deep=1 /login")

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REMOTE=0
for arg in "$@"; do
  case "$arg" in
    --remote) REMOTE=1 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
  esac
done

CRM_URL="${CRM_URL:-${CRM_PUBLIC_URL:-http://194.67.103.144:5001}}"
CRM_URL="${CRM_URL%/}"
CONCURRENCY="${CONCURRENCY:-10}"
REQUESTS="${REQUESTS:-100}"
PATHS="${PATHS:-/health /health?deep=1 /login}"

run_load() {
  local base="$1"
  python3 - "$base" "$CONCURRENCY" "$REQUESTS" "$PATHS" <<'PY'
import concurrent.futures
import os
import sys
import time
import urllib.error
import urllib.request

base, conc, total, paths_raw = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
paths = [p for p in paths_raw.split() if p]
ok = fail = 0
lat = []

def one(i: int):
    path = paths[i % len(paths)]
    url = base.rstrip("/") + path
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            code = resp.getcode()
            resp.read(256)
        dt = (time.perf_counter() - t0) * 1000
        return code < 400, dt, code
    except Exception as exc:  # noqa: BLE001
        dt = (time.perf_counter() - t0) * 1000
        return False, dt, str(exc.__class__.__name__)

t0 = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=conc) as pool:
    futs = [pool.submit(one, i) for i in range(total)]
    for fut in concurrent.futures.as_completed(futs):
        good, dt, code = fut.result()
        lat.append(dt)
        if good:
            ok += 1
        else:
            fail += 1
elapsed = time.perf_counter() - t0
lat.sort()
def pct(p):
    if not lat:
        return 0
    return lat[min(len(lat) - 1, int(round((p / 100) * (len(lat) - 1))))]

print(f"base={base}")
print(f"concurrency={conc} requests={total} paths={paths}")
print(f"ok={ok} fail={fail} rps={total/elapsed:.1f} elapsed_s={elapsed:.2f}")
print(f"latency_ms p50={pct(50):.0f} p95={pct(95):.0f} p99={pct(99):.0f} max={lat[-1] if lat else 0:.0f}")
sys.exit(0 if fail == 0 else 1)
PY
}

if [[ "$REMOTE" -eq 1 ]]; then
  echo "→ load test on BlueTerbium → http://127.0.0.1:5001"
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
  export SSHPASS="${BLUETERBIUM_SSH_PASSWORD:-}"
  PORT="${BLUETERBIUM_SSH_PORT:-2222}"
  USER_NAME="${BLUETERBIUM_SSH_USER:-root}"
  HOST="${BLUETERBIUM_SSH_HOST:?BLUETERBIUM_SSH_HOST required}"
  SSH=(ssh -T -p "$PORT" -o ConnectTimeout=25 -o StrictHostKeyChecking=accept-new -o RequestTTY=no)
  if [[ -n "${SSHPASS:-}" ]] && command -v sshpass >/dev/null; then
    SSH=(sshpass -e "${SSH[@]}")
  fi
  # передаём скрипт целиком
  "${SSH[@]}" "${USER_NAME}@${HOST}" \
    "CONCURRENCY=$CONCURRENCY REQUESTS=$REQUESTS PATHS='$PATHS' bash -s" <<REMOTE
set -euo pipefail
python3 - <<'PY'
import concurrent.futures, sys, time, urllib.request
base = "http://127.0.0.1:5001"
conc = int("${CONCURRENCY}")
total = int("${REQUESTS}")
paths = "${PATHS}".split()
ok = fail = 0
lat = []

def one(i):
    path = paths[i % len(paths)]
    url = base + path
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            code = resp.getcode()
            resp.read(256)
        return code < 400, (time.perf_counter()-t0)*1000, code
    except Exception as exc:
        return False, (time.perf_counter()-t0)*1000, type(exc).__name__

t0 = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=conc) as pool:
    for good, dt, code in pool.map(one, range(total)):
        lat.append(dt)
        ok += 1 if good else 0
        fail += 0 if good else 1
elapsed = time.perf_counter() - t0
lat.sort()
def pct(p):
    if not lat:
        return 0.0
    idx = min(len(lat) - 1, int(round((p / 100) * (len(lat) - 1))))
    return lat[idx]
print(f"base={base}")
print(f"concurrency={conc} requests={total} paths={paths}")
print(f"ok={ok} fail={fail} rps={total/elapsed:.1f} elapsed_s={elapsed:.2f}")
print(f"latency_ms p50={pct(50):.0f} p95={pct(95):.0f} p99={pct(99):.0f} max={lat[-1] if lat else 0:.0f}")
sys.exit(0 if fail == 0 else 1)
PY
REMOTE
else
  run_load "$CRM_URL"
fi
