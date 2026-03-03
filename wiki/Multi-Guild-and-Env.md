# Multi-Guild and Env Setup

Last Updated: 2026-03-02

## Required vs Optional Vars

- Required:
  - `DISCORD_TOKEN`
- Optional:
  - `MANAGED_GUILD_IDS`
  - `GUILD_ID`
  - `Bot_Log_Channel`
  - Web/admin integration vars (`WEB_*`)

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

## Recommended Multi-Guild Example

```env
DISCORD_TOKEN=your-token
MANAGED_GUILD_IDS=111111111111111111,222222222222222222
WEB_ENABLED=true
WEB_BIND_HOST=0.0.0.0
WEB_PORT=8080
WEB_TLS_ENABLED=true
WEB_TLS_PORT=8081
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
```
