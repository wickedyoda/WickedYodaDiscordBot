FROM python@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install docker CLI for container management
RUN apt-get update && \
    apt-get install -y --no-install-recommends docker.io cron && \
    apt-get install -y --no-install-recommends --only-upgrade \
        apt libapt-pkg7.0 libpcre2-8-0 libssl3t64 openssl openssl-provider-legacy zlib1g && \
    rm -rf /var/lib/apt/lists/*

COPY watchtower-gui/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY watchtower-gui/ .
COPY watchtower-gui/scripts/update-containers.sh /app/update-containers.sh
RUN chmod +x /app/update-containers.sh

# Create non-root user for security (fixes Trivy DS002)
RUN groupadd --system --gid 10001 appgroup && \
    useradd --system --uid 10001 --gid appgroup --no-create-home --home-dir /app --shell /usr/sbin/nologin appuser

# Cron setup
RUN touch /etc/cron.d/watchtower-auto && chmod 0644 /etc/cron.d/watchtower-auto

# Fix permissions for non-root user
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 5000

CMD ["sh", "-c", "cron -f & python app.py"]