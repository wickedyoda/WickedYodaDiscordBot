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

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import os,sys,urllib.request; enabled=os.getenv('WEB_ENABLED','true').lower() in {'1','true','yes','on'}; url=f'http://127.0.0.1:{os.getenv(\"WEB_PORT\",\"8080\")}/healthz'; status=urllib.request.urlopen(url, timeout=3).status if enabled else 200; sys.exit(0 if status==200 else 1)"

CMD ["python", "bot.py"]
