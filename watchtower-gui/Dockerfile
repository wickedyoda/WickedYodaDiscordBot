FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install docker CLI for container management
RUN apt-get update && \
    apt-get install -y --no-install-recommends docker.io cron && \
    rm -rf /var/lib/apt/lists/*

COPY watchtower-gui/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY watchtower-gui/ .
COPY watchtower-gui/scripts/update-containers.sh /app/update-containers.sh
RUN chmod +x /app/update-containers.sh

# Create non-root user for security (fixes Trivy DS002)
RUN addgroup --system --gid 10001 appgroup && \
    adduser --system --uid 10001 --gid appgroup --no-create-home --home /app appuser

# Cron setup
RUN touch /etc/cron.d/watchtower-auto && chmod 0644 /etc/cron.d/watchtower-auto

# Fix permissions for non-root user
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 5000

CMD ["sh", "-c", "cron -f & python app.py"]