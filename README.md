# WickedYoda's Little Helper

Basic moderation Discord bot with a mobile-friendly web admin GUI, designed to run in Docker using `env.env`.

## Environment Variables

Set these in `env.env`:

- `DISCORD_TOKEN` - your bot token
- `GUILD_ID` - your Discord server (guild) ID
- `Bot_Log_Channel` - text channel ID where bot action logs are posted
- `WEB_ENABLED` - enable web GUI (`true`/`false`)
- `WEB_BIND_HOST` - web server bind host (use `0.0.0.0` in Docker)
- `WEB_PORT` - web GUI port inside container
- `WEB_ADMIN_DEFAULT_USERNAME` - web admin login username
- `WEB_ADMIN_DEFAULT_PASSWORD` - web admin login password
- `WEB_ADMIN_SESSION_SECRET` - session signing secret for Flask
- `DATA_DIR` - persistent data directory for moderation action history

## Included Slash Commands

- `/ping`
- `/kick`
- `/ban`
- `/timeout`
- `/untimeout`
- `/purge`

All command actions (success/failure) are logged to `Bot_Log_Channel`.
All actions are also written to SQLite and visible in the web GUI.

## Web Admin GUI

- URL: `http://localhost:8080`
- Login: `WEB_ADMIN_DEFAULT_USERNAME` / `WEB_ADMIN_DEFAULT_PASSWORD`
- Pages:
  - Dashboard (`/admin`)
  - Action history (`/admin/actions`)
  - Runtime settings view (`/admin/settings`)

The GUI is built with responsive Bootstrap layout for mobile and desktop.

## Run With Docker Compose

```bash
docker compose up --build -d
```

## Required Bot Permissions

In your Discord Developer Portal bot setup and server role, ensure the bot can:

- View Channels
- Send Messages
- Embed Links
- Kick Members
- Ban Members
- Moderate Members
- Manage Messages
- Read Message History
