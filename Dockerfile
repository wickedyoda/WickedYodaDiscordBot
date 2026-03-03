FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py web_admin.py ./
RUN mkdir -p /app/data
RUN useradd --create-home --shell /usr/sbin/nologin botuser && chown -R botuser:botuser /app

USER botuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import os,sys,ssl,urllib.request; enabled=os.getenv('WEB_ENABLED','true').lower() in {'1','true','yes','on'}; tls=os.getenv('WEB_TLS_ENABLED','false').lower() in {'1','true','yes','on'}; scheme='https' if tls else 'http'; url=f'{scheme}://127.0.0.1:{os.getenv(\"WEB_PORT\",\"8081\")}/healthz'; ctx=ssl._create_unverified_context() if tls else None; status=urllib.request.urlopen(url, timeout=3, context=ctx).status if enabled else 200; sys.exit(0 if status==200 else 1)"

CMD ["python", "bot.py"]
