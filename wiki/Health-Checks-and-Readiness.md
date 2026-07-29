# Health Checks and Readiness

Last Updated: 2026-07-28

This page explains how to verify bot readiness, web GUI health, and container startup status.

## Bot ready behavior

* `/health` returns `200` only after the Discord bot is ready.
* `/healthz` is also provided for generic liveness probes.
* `/status` shows operational state and can be used for quick diagnostics.
* `/status/everything` returns the public-facing status page data.

## Local checks

```bash
curl -i http://localhost:8080/health
curl -i https://localhost:8081/health
```

Expected successful response indicators:

* HTTP `200`
* JSON or plain text indicating ready state
* No connection refused or TLS handshake errors

## Inside the container

```bash
docker exec <container-name> python -c "import os; print('ok')"
```

This verifies the Python runtime and installed dependencies load.

## Readiness troubleshooting

If `/health` does not return `200`:

1. Check container logs for startup import errors.
2. Confirm `DISCORD_TOKEN` is valid.
3. Confirm `MANAGED_GUILD_IDS` is set if the bot must join specific guilds.
4. If `WEB_ENABLED=false`, web health paths are unavailable by design.
5. If you recently checked out a feature branch, confirm feature modules import cleanly from their expected paths.

## D&D branch readiness note

When running the `dnd` branch:

* `bot.py` imports `from dnd.bot_integration import ensure_dnd_schema, register_dnd_commands`
* Ensure the checked-out repo contains the `dnd/` package directory
* Ensure the container image or bind mount includes `dnd/`
* `/dnd` commands initialize schema from `/app/data/dnd.db` at runtime
2026-07-29 refresh
