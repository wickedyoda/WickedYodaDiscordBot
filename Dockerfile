FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && apt-get install -y --no-install-recommends --only-upgrade libssl3t64 openssl openssl-provider-legacy || true \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

COPY bot.py ./
COPY app /app/app
COPY core /app/core
COPY webui /app/webui
COPY dnd /app/dnd
COPY scripts/entrypoint.sh /app/entrypoint.sh
COPY scripts/migrate_db.sh /app/scripts/migrate_db.sh
RUN mkdir -p /app/data /logs /app/scripts \
    && useradd --create-home --shell /usr/sbin/nologin botuser \
    && chown -R botuser:botuser /app /logs \
    && chmod +x /app/entrypoint.sh /app/scripts/migrate_db.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import os,sys,urllib.request; enabled=os.getenv('WEB_ENABLED','true').lower() in {'1','true','yes','on'}; port=os.getenv('WEB_PORT','8080'); base=f'http://127.0.0.1:{port}';\n\n\nstatus=200\nif enabled:\n    try:\n        status=urllib.request.urlopen(f'{base}/health', timeout=3).status\n        if status!=200:\n            status=urllib.request.urlopen(f'{base}/healthz', timeout=3).status\n    except Exception:\n        status=1\nsys.exit(0 if status==200 else 1)"

USER botuser

ENTRYPOINT ["/app/entrypoint.sh"]
