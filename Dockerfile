# syntax=docker/dockerfile:1

FROM python:3.13-slim AS wheels

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DASHBOARD_DEBUG=0 \
    DASHBOARD_DATABASE_ENGINE=sqlite \
    DASHBOARD_WORKSPACE_ROOT=/workspace \
    DOCUMENT_VIEWER_DEFAULT_DIRECTORY=/workspace \
    SQLITE_DATABASE_PATH=/data/dashboard.sqlite3 \
    PORT=8000

RUN addgroup --system dashboard \
    && adduser --system --ingroup dashboard --home /app dashboard

WORKDIR /app

COPY --from=wheels /wheels /wheels
RUN pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

COPY --chown=dashboard:dashboard . .
RUN chmod +x /app/docker-entrypoint.sh \
    && mkdir -p /data /workspace /app/staticfiles \
    && chown -R dashboard:dashboard /data /workspace /app/staticfiles \
    && DASHBOARD_SECRET_KEY=collectstatic-build-only python manage.py collectstatic --noinput

USER dashboard

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health/', timeout=3)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["serve"]
