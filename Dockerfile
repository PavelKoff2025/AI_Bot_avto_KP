# AI_Auogeneration — runtime image (Flask API + опционально Telegram-бот)
# WeasyPrint нуждается в системных cairo/pango/gdk-pixbuf.

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5000 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

# Системные зависимости для WeasyPrint + curl для healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fonts-dejavu-core \
        libcairo2 \
        libffi8 \
        libgdk-pixbuf-2.0-0 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-docker.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt -r requirements-docker.txt

COPY fonts ./fonts
COPY templates ./templates
COPY utils ./utils
COPY sample_dialog.txt ./
COPY flask_app.py main.py bot.py ./
COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh

RUN chmod +x /docker-entrypoint.sh \
    && mkdir -p reports/kp reports/engineering reports/images logs \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser ${APP_HOME}

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${FLASK_PORT:-5000}/health" || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["api"]
