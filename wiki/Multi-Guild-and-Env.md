# Multi-Guild and Env Setup

Last Updated: 2026-07-28

## D&D 20th Persistent Schema

- The bot auto-runs D&D SQLite schema setup at startup from the web/admin startup flow.
- No new required env vars are required for D&D commands.
- State is stored in SQLite and managed via `/dnd` slash commands.

## Required vs Optional Vars

- Required:
  - `DISCORD_TOKEN`
- Optional:
  - `MANAGED_GUILD_IDS`
  - `GUILD_ID`
  - `Bot_Log_Channel`
  - Web/admin integration vars (`WEB_*`)
  - Storage vars (`DATA_DIR`, `ACTION_DB_PATH`, `LOG_DIR`)
  - Feed integration timeouts (`YOUTUBE_REQUEST_TIMEOUT_SECONDS`, `WORDPRESS_REQUEST_TIMEOUT_SECONDS`, `LINKEDIN_REQUEST_TIMEOUT_SECONDS`)
  - Spicy Prompts repo vars (`SPICY_PROMPTS_*`)
  - Uptime monitors (no required env vars; configured in web GUI)

## Storage Paths

- In the shipped Docker Compose example, `DATA_DIR` in `env.env` is the host-side bind path for persistent data.
- In the shipped Docker Compose example, `LOG_DIR` in `env.env` is the host-side bind path for persistent logs.
- `docker-compose.yml` overrides the bot's in-container `DATA_DIR` to `/app/data` and `LOG_DIR` to `/logs`.
- `ACTION_DB_PATH` defaults to the in-container `DATA_DIR/mod_actions.db` when unset.
- `LOG_DIR` defaults under the in-container `DATA_DIR` when unset or invalid, but the shipped Compose example pins it to `/app/log`.
- The shipped `docker-compose.yml` example bind-mounts `${DATA_DIR:-/root/docker/wickedyodabot}` to `/app/data`.
- The shipped `docker-compose.yml` example bind-mounts `${LOG_DIR:-/root/docker/wickedyodabot/log}` to `/logs`.
- Start Compose with `docker compose --env-file env.env up -d` so the bind path comes from `env.env`.

## env.env Overlay

The runtime loads defaults from `env.env`, then applies overrides from `/app/env.env` (written by the web GUI). This allows per-deployment overrides without editing the base file.

## How Guild Selection Works

- `MANAGED_GUILD_IDS` set:
  - Bot only manages/syncs commands to those guild IDs.
  - Recommended for production control.
- `MANAGED_GUILD_IDS` not set:
  - Bot manages all guilds it is currently in.
- `GUILD_ID` set:
  - Used as legacy/default fallback for some seed settings.
- `GUILD_ID` not set:
  - Bot still starts in multi-guild mode.

## Logging Channel Behavior

- Primary mode is per-guild log channel from `/admin/guild-settings`.
- Fallback mode uses global `Bot_Log_Channel` if set.
- If neither is configured, Discord log-channel posting is skipped, but file/SQLite logging still runs.

## Guild-Scoped Feed Automation

Feed subscriptions are configured per guild from the web GUI. The selected guild in the top nav controls which server you are editing for:

- Reddit feeds
- WordPress feeds
- LinkedIn feeds
- YouTube feeds

Feed source URLs, selected notify channels, and last-seen state do not cross between guilds.

## Spicy Prompts Repo Settings

The repo-backed Spicy Prompts cache is global to the bot runtime and refreshed from the web GUI.

- `SPICY_PROMPTS_ENABLED`
- `SPICY_PROMPTS_REPO_URL`
- `SPICY_PROMPTS_REPO_BRANCH`
- `SPICY_PROMPTS_MANIFEST_PATH`
- `SPICY_PROMPTS_REQUEST_TIMEOUT_SECONDS`

The refresh action pulls the current manifest and pack files from the configured GitHub repo without restarting the bot.

## Recommended Multi-Guild Example

```env
DISCORD_TOKEN=your-token
MANAGED_GUILD_IDS=111111111111111111,222222222222222222
WEB_ENABLED=true
WEB_BIND_HOST=0.0.0.0
WEB_PORT=8080
WEB_TLS_ENABLED=true
WEB_TLS_PORT=8081
DATA_DIR=/root/docker/wickedyodabot
LOG_DIR=/root/docker/wickedyodabot/logs
```

## Single-Guild Legacy Example

```env
DISCORD_TOKEN=your-token
GUILD_ID=111111111111111111
Bot_Log_Channel=333333333333333333
WEB_ENABLED=true
WEB_PORT=8080
WEB_TLS_ENABLED=true
WEB_TLS_PORT=8081
DATA_DIR=/root/docker/wickedyodabot
LOG_DIR=/root/docker/wickedyodabot/logs
```


## Log Retention

- `LOG_RETENTION_DAYS` controls how long log files are kept (default 90).
- Logs are written inside the container to `/logs` and should be bind-mounted to the host (e.g. `./logs:/logs`).

## Guild Admin Access

Guild Admins are web users scoped to a subset of guilds. Access groups are configured under `/admin/guild-access`:

- Create a group
- Assign guilds to the group
- Assign user emails to the group

Guild Admin users only see and manage the guilds assigned to their groups.
