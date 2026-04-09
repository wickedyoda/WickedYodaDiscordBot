#!/bin/sh
set -e

mkdir -p /app/data /logs

if [ "$(id -u)" -eq 0 ]; then
  chown -R botuser:botuser /app/data /logs || true
  exec gosu botuser python /app/bot.py
fi

exec python /app/bot.py
