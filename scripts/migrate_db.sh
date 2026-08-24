#!/bin/sh
set -e

migrate_db() {
  legacy="$1"
  target="$2"
  label="$3"

  if [ ! -f "$legacy" ]; then
    return
  fi
  if [ "$(readlink -f "$legacy")" = "$(readlink -f "$target")" ]; then
    return
  fi
  if [ -f "$target" ]; then
    return
  fi

  mkdir -p "$(dirname "$target")"
  mv "$legacy" "$target" 2>/dev/null || true

  for suffix in "-wal" "-shm" ""; do
    src="${legacy}${suffix}"
    dst="${target}${suffix}"
    if [ -f "$src" ] && [ ! -f "$dst" ]; then
      mv "$src" "$dst" 2>/dev/null || true
    fi
  done

  echo "[migrate] $label: moved $legacy -> $target"
}

mkdir -p /app/data/storage

migrate_db /app/data/mod_actions.db /app/data/storage/mod_actions.db "action db"
migrate_db /app/data/dnd.db /app/data/storage/dnd.db "dnd db"
