#!/bin/sh
# Entrypoint контейнера.
# CMD: api | bot | cli  (+ произвольные аргументы)

set -eu

mode="${1:-api}"
if [ "$#" -gt 0 ]; then
  shift
fi

cd "${APP_HOME:-/app}"

case "$mode" in
  api|serve|flask)
    host="${FLASK_HOST:-0.0.0.0}"
    port="${FLASK_PORT:-5000}"
    workers="${WEB_CONCURRENCY:-2}"
    timeout="${GUNICORN_TIMEOUT:-600}"
    echo "Starting Flask API on ${host}:${port} (workers=${workers}, timeout=${timeout}s)"
    exec gunicorn \
      --bind "${host}:${port}" \
      --workers "${workers}" \
      --timeout "${timeout}" \
      --access-logfile - \
      --error-logfile - \
      "flask_app:create_app()"
    ;;
  bot|telegram)
    echo "Starting Telegram bot (polling)"
    exec python bot.py
    ;;
  cli|main)
    exec python main.py "$@"
    ;;
  *)
    # Произвольная команда: docker run ... image python -c '...'
    exec "$mode" "$@"
    ;;
esac
