# WickedYoda's Little Helper

Basic moderation Discord bot with a mobile-friendly web admin GUI, designed to run in Docker using `env.env`.

## Wiki

Project wiki files live in [`wiki/`](wiki/).

- [`wiki/Home.md`](wiki/Home.md) - wiki index and maintenance workflow
- [`wiki/Command-Reference.md`](wiki/Command-Reference.md) - full slash command documentation
- [`wiki/Multi-Guild-and-Env.md`](wiki/Multi-Guild-and-Env.md) - multi-guild behavior and environment variable patterns
- [`wiki/Web-Admin-Interface.md`](wiki/Web-Admin-Interface.md) - web GUI authentication, pages, and security controls

When adding or changing a bot command, update `wiki/Command-Reference.md` in the same pull request.

## Environment Variables

Set these in `env.env`:

- `DISCORD_TOKEN` - your bot token
- `GUILD_ID` - optional default guild ID (needed for legacy single-guild defaults; can be omitted in multi-guild mode)
- `MANAGED_GUILD_IDS` - optional comma-separated guild IDs to manage/sync (defaults to all guilds the bot is in)
- `Bot_Log_Channel` - optional default text channel ID for bot action logs (can be overridden per guild in web GUI)
- `WEB_ENABLED` - enable web GUI (`true`/`false`)
- `WEB_BIND_HOST` - web server bind host (use `0.0.0.0` in Docker)
- `WEB_PORT` - web GUI port inside container
- `WEB_TLS_ENABLED` - enable HTTPS for the web GUI (`true`/`false`)
- `WEB_TLS_PORT` - HTTPS web GUI port (recommended: `WEB_PORT + 1`)
- `WEB_TLS_CERT_FILE` - optional TLS certificate path (requires `WEB_TLS_KEY_FILE`)
- `WEB_TLS_KEY_FILE` - optional TLS private key path (requires `WEB_TLS_CERT_FILE`)
- `ENABLE_MEMBERS_INTENT` - set `true` only if you enabled Server Members Intent in Discord Developer Portal
- `COMMAND_RESPONSES_EPHEMERAL` - set `false` for public command replies, `true` for user-only (ephemeral) replies
- `PUPPY_IMAGE_API_URL` - API endpoint used by `/happy` for random puppy images
- `PUPPY_IMAGE_TIMEOUT_SECONDS` - timeout for puppy image API requests
- `SHORTENER_ENABLED` - enable Shortipy integration commands (`/shorten`, `/expand`)
- `SHORTENER_BASE_URL` - Shortipy base URL (example: `https://l.twy4.us`)
- `SHORTENER_TIMEOUT_SECONDS` - timeout for Shortipy requests
- `YOUTUBE_NOTIFY_ENABLED` - enable background YouTube upload notifications
- `YOUTUBE_POLL_INTERVAL_SECONDS` - polling interval for YouTube feed checks
- `YOUTUBE_REQUEST_TIMEOUT_SECONDS` - timeout for YouTube URL/feed requests
- `UPTIME_STATUS_ENABLED` - enable uptime status integration command (`/uptime`)
- `UPTIME_STATUS_PAGE_URL` - public Uptime Kuma status page URL (example: `https://randy.wickedyoda.com/status/everything`)
- `UPTIME_STATUS_TIMEOUT_SECONDS` - timeout for uptime API requests
- `WEB_ADMIN_DEFAULT_USERNAME` - web admin login username
- `WEB_ADMIN_DEFAULT_PASSWORD` - web admin login password
- `WEB_ADMIN_DEFAULT_PASSWORD_HASH` - optional password hash instead of plaintext password
- `WEB_ADMIN_SESSION_SECRET` - session signing secret for Flask
- `WEB_SESSION_COOKIE_SECURE` - set `true` when using HTTPS
- `WEB_SESSION_COOKIE_SAMESITE` - cookie same-site policy (`Lax`, `Strict`, `None`)
- `WEB_SESSION_TIMEOUT_MINUTES` - web session timeout (minutes)
- `WEB_AVATAR_MAX_UPLOAD_BYTES` - max avatar upload size for `/admin/bot-profile` (default `2097152`)
- `WEB_ENFORCE_CSRF` - enforce CSRF token checks on POST routes (`true`/`false`)
- `WEB_ENFORCE_SAME_ORIGIN_POSTS` - block cross-origin POST requests (`true`/`false`)
- `WEB_RESTART_ENABLED` - allow admin-triggered container restart from web GUI (`true`/`false`)
- `DATA_DIR` - persistent internal data directory for moderation action history (recommended: `/app/data`)
- `LOG_DIR` - optional override for log file directory shown in web GUI Logs page
- `WEB_ENV_FILE` - optional path to env file used by web GUI settings editor (default: `./env.env`)
- `WEB_GITHUB_WIKI_URL` - optional external wiki URL button in the web GUI Wiki page

### Multi-Guild Startup Notes

- Minimum required variable is `DISCORD_TOKEN`.
- `MANAGED_GUILD_IDS` is recommended for controlled multi-guild operation.
- `GUILD_ID` is optional; keep it only for legacy/single-guild defaults.
- `Bot_Log_Channel` is optional when you configure per-guild log channels in `/admin/guild-settings`.

Example multi-guild config:

```env
DISCORD_TOKEN=your-token
MANAGED_GUILD_IDS=111111111111111111,222222222222222222
WEB_ENABLED=true
WEB_BIND_HOST=0.0.0.0
WEB_PORT=8080
WEB_TLS_ENABLED=true
WEB_TLS_PORT=8081
```

## Included Slash Commands

- `/ping`
- `/sayhi`
- `/happy`
- `/help`
- `/tags`
- `/tag`
- `/shorten`
- `/expand`
- `/uptime`
- `/logs`
- `/kick`
- `/ban`
- `/timeout`
- `/untimeout`
- `/purge`
- `/unban`
- `/addrole`
- `/removerole`

Detailed command behavior, parameters, and permission requirements are documented in [`wiki/Command-Reference.md`](wiki/Command-Reference.md).

All command actions (success/failure) are logged to per-guild configured log channel, or `Bot_Log_Channel` when set.
All actions are also written to SQLite and visible in the web GUI.

SQLite storage is internal to the container at `/app/data/mod_actions.db`.

## Web Admin GUI

- HTTP URL: `http://localhost:8080`
- HTTPS URL: `https://localhost:8081`
- Login: `WEB_ADMIN_DEFAULT_USERNAME` / `WEB_ADMIN_DEFAULT_PASSWORD`
- If `WEB_TLS_ENABLED=true` and cert/key files are not set, Flask runs with an adhoc self-signed certificate (requires `cryptography`, included in this image).
- Use the guild dropdown in the top nav to switch the server you are managing.
- Theme switcher (Light/Black) is available in the top nav and persists per browser.
- Login includes optional "Keep me signed in" mode (5-day max), inactivity timeout, and IP-based login attempt throttling.
- Pages:
  - Dashboard (`/admin`)
  - Action history (`/admin/actions`)
  - YouTube subscriptions (`/admin/youtube`)
  - Observability (`/admin/observability`, login required)
  - Bot profile (`/admin/bot-profile`, admin only)
    - Includes bot username/nickname updates and avatar upload
  - Guild settings (`/admin/guild-settings`, admin only)
  - Logs viewer (`/admin/logs`)
  - Wiki viewer (`/admin/wiki`)
  - Account password management (`/admin/account`)
  - User management (`/admin/users`, admin only)
  - Command permissions (`/admin/command-permissions`, admin only)
  - Tag responses (`/admin/tag-responses`, admin only)
  - Runtime settings editor (`/admin/settings`, admin only)
  - Public status page (`/status/everything`)

The GUI is built with responsive Bootstrap layout for mobile and desktop.
Settings are editable from the GUI and saved back to `env.env` (or `WEB_ENV_FILE`), with dropdown selectors for boolean and common numeric options where possible.

## YouTube Auto Notifications

- Open `/admin/youtube` in the web GUI.
- Add a YouTube channel URL and select the Discord channel to notify.
- The bot stores subscriptions in SQLite and polls YouTube feeds.
- On new uploads, it posts a notification embed in the selected Discord channel(s).

## Verification And Security Checks

Local verification command:

```bash
./scripts/verify.sh
```

This runs:
- Python compile check
- Ruff lint + format check
- Pytest
- Bandit (in CI Python 3.12; skipped locally on Python 3.14+ due upstream tool incompatibility)
- pip-audit dependency vulnerability check
- Docker image build verification

GitHub workflows included:
- `.github/workflows/ci.yml` - lint/test/audit/docker build
- `.github/workflows/security.yml` - Gitleaks + Trivy FS/Image scans
- `.github/workflows/codeql.yml` - CodeQL static analysis
- `.github/workflows/dependency-review.yml` - dependency risk gate for pull requests
- `.github/workflows/python-vulnerability-scan.yml` - scheduled + on-change `pip-audit`
- `.github/workflows/sbom.yml` - CycloneDX SBOM generation artifact
- `.github/workflows/scorecards.yml` - weekly OSSF Scorecards analysis
- `.github/dependabot.yml` - weekly dependency updates

## Run With Docker Compose

```bash
docker compose up -d
```

Compose mounts a persistent writable volume at `/app/data` for SQLite and log files.

## Docker Image Publish (GitHub Packages / GHCR)

Workflow: `.github/workflows/docker-publish.yml`

- Publishes on push to `main`, semantic version tags (`v*.*.*`), or manual run.
- Publishes automatically after successful `CI` completion on `main`, on semantic version tags (`v*.*.*`), or manual run.
- Push target:
  - `ghcr.io/<owner>/<repo>:latest`
  - `ghcr.io/<owner>/<repo>:<branch|tag|sha>`
- Multi-arch build: `linux/amd64`, `linux/arm64`

To trigger publish, push to `main` or create a tag:

```bash
git tag v0.1.0
git push origin main --tags
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
