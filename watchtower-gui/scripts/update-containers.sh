#!/bin/bash
# Auto-update script called by cron
# Pulls latest images for all running containers and restarts them

set -e

echo "[$(date)] Starting scheduled container updates..."

# Get list of running containers with their images
containers=$(docker ps --format '{{.ID}} {{.Image}}')

while read -r id image; do
    if [ -z "$id" ]; then
        continue
    fi

    echo "[$(date)] Processing container $id (image: $image)"

    # Get full image name with registry
    image_full=$image

    # Pull latest image
    echo "[$(date)] Pulling $image_full..."
    docker pull "$image_full"

    # Restart the container
    echo "[$(date)] Restarting container $id..."
    docker restart "$id"

done <<< "$containers"

echo "[$(date)] Scheduled update complete."
