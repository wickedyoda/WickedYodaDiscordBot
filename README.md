# Wicked Yoda's Little Helper

Basic moderation Discord bot with a mobile-friendly web admin GUI, designed to run in Docker using `env.env`.

Invite the bot: [Discord OAuth2 Invite](https://discord.com/oauth2/authorize?client_id=1478110480806576259)

## Wiki

Project wiki files live in [`wiki/`](wiki/).

- [`wiki/Home.md`](wiki/Home.md) - wiki index and maintenance workflow
- [`wiki/Command-Reference.md`](wiki/Command-Reference.md) - full slash command documentation
- [`wiki/Feed-Integrations.md`](wiki/Feed-Integrations.md) - web-managed Reddit, WordPress, LinkedIn, and YouTube feeds
- [`wiki/Multi-Guild-and-Env.md`](wiki/Multi-Guild-and-Env.md) - multi-guild behavior and environment variable patterns
- [`wiki/Web-Admin-Interface.md`](wiki/Web-Admin-Interface.md) - web GUI authentication, pages, and security controls
- [`wiki/Security-Hardening.md`](wiki/Security-Hardening.md) - runtime and verification hardening details
- [`wiki/Docker-and-Portainer-Deploy.md`](wiki/Docker-and-Portainer-Deploy.md) - container deployment, Portainer, and health checks
- [`wiki/Environment-Variables.md`](wiki/Environment-Variables.md) - bot, web, and integration environment variables
- [`wiki/Health-Checks-and-Readiness.md`](wiki/Health-Checks-and-Readiness.md) - readiness checks and startup verification
- [`wiki/DnD-HowTo.md`](wiki/DnD-HowTo.md) - D&D 20th command workflows and story data model

When adding or changing a bot command, update `wiki/Command-Reference.md` in the same commit/PR.

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
- `FUN_API_TIMEOUT_SECONDS` - timeout for fun command APIs (`/cat`, `/meme`, `/dadjoke`)
- `CAT_IMAGE_API_URL` - API endpoint used by `/cat`
- `MEME_API_URL` - API endpoint used by `/meme`
- `DAD_JOKE_API_URL` - API endpoint used by `/dadjoke`
- `SHORTENER_ENABLED` - enable Shortipy integration commands (`/shorten`, `/expand`)
- `SHORTENER_BASE_URL` - Shortipy base URL (example: `https://l.twy4.us`)
- `SHORTENER_TIMEOUT_SECONDS` - timeout for Shortipy requests
- `YOUTUBE_NOTIFY_ENABLED` - enable background YouTube upload notifications
- `YOUTUBE_POLL_INTERVAL_SECONDS` - polling interval for YouTube feed checks
- `YOUTUBE_REQUEST_TIMEOUT_SECONDS` - timeout for YouTube URL/feed requests
- `WORDPRESS_REQUEST_TIMEOUT_SECONDS` - timeout for WordPress feed discovery and polling
- `LINKEDIN_REQUEST_TIMEOUT_SECONDS` - timeout for LinkedIn profile activity requests
- `SPICY_PROMPTS_ENABLED` - enable the repo-backed Spicy Prompts feature
- `SPICY_PROMPTS_REPO_URL` - GitHub repo URL used as the source of Spicy Prompts content
- `SPICY_PROMPTS_REPO_BRANCH` - branch to read from the Spicy Prompts repo
- `SPICY_PROMPTS_MANIFEST_PATH` - manifest file path inside the Spicy Prompts repo
- `SPICY_PROMPTS_REQUEST_TIMEOUT_SECONDS` - timeout for Spicy Prompts repo fetches
- `UPTIME_STATUS_ENABLED` - enable uptime status integration command (`/uptime`)
- `UPTIME_STATUS_PAGE_URL` - public Uptime Kuma status page URL (example: `https://randy.wickedyoda.com/status/everything`)
- `UPTIME_STATUS_TIMEOUT_SECONDS` - timeout for uptime API requests
- `WEB_ADMIN_DEFAULT_USERNAME` - web admin login username
- `WEB_ADMIN_DEFAULT_PASSWORD` - web admin login password
- `WEB_ADMIN_DEFAULT_PASSWORD_HASH` - optional password hash instead of plaintext password
- `WEB_ADMIN_SESSION_SECRET` - session signing secret for Flask
- `WEB_PASSWORD_RESET_ENABLED` - enable email-based password reset from the login page
- `WEB_PUBLIC_BASE_URL` - public base URL used in password reset emails (example: `https://bot.example.com`)
- `WEB_SMTP_HOST` - SMTP server hostname for password reset emails
- `WEB_SMTP_PORT` - SMTP server port (`587` for STARTTLS, `465` for SSL, `25` for plain SMTP)
- `WEB_SMTP_USERNAME` - optional SMTP username
- `WEB_SMTP_PASSWORD` - optional SMTP password
- `WEB_SMTP_FROM_EMAIL` - from-address used for password reset emails
- `WEB_SMTP_FROM_NAME` - display name used for password reset emails
- `WEB_SMTP_SECURITY` - SMTP security mode (`none`, `starttls`, `ssl`)
- `WEB_SESSION_COOKIE_SECURE` - set `true` when using HTTPS
- `WEB_SESSION_COOKIE_SAMESITE` - cookie same-site policy (`Lax`, `Strict`, `None`)
- `WEB_SESSION_TIMEOUT_MINUTES` - web session timeout (minutes)
- `WEB_AVATAR_MAX_UPLOAD_BYTES` - max avatar upload size for `/admin/bot-profile` (default `2097152`)
- `WEB_ENFORCE_CSRF` - enforce CSRF token checks on POST routes (`true`/`false`)
- `WEB_ENFORCE_SAME_ORIGIN_POSTS` - block cross-origin POST requests (`true`/`false`)
- `WEB_RESTART_ENABLED` - allow admin-triggered container restart from web GUI (`true`/`false`)
- `DATA_DIR` - when using the shipped Docker Compose example, host-side bind path for persistent bot data (example: `/root/docker/wickedyodabot`)
- `LOG_DIR` - when using the shipped Docker Compose example, host-side bind path for persistent bot logs (example: `/root/docker/wickedyodabot/logs`)
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
- `/cat`
- `/meme`
- `/dadjoke`
- `/eightball`
- `/coinflip`
- `/roll`
- `/choose`
- `/roastme`
- `/compliment`
- `/wisdom`
- `/gif`
- `/poll`
- `/questionoftheday`
- `/spicy`
- `/countdown`
- `/dnd roll`
- `/dnd general`
- `/dnd initiative`
- `/dnd character`
- `/birthday set`
- `/birthday view`
- `/birthday upcoming`
- `/birthday remove`
- `/leaderboard`
- `/trivia`
- `/wouldyourather`
- `/rps`
- `/guess`
- `/help`
- `/tags`
- `/tag`
- `/shorten`
- `/expand`
- `/uptime`
- `/logs`
- `/stats`
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

Member message activity is also recorded internally and exposed through:

- `/stats` for a private per-user activity summary in Discord
- `/admin/member-activity` for guild activity rankings and export in the web GUI

SQLite storage is internal to the container at `/app/data/mod_actions.db`.

## Web Admin GUI

- HTTP URL: `http://localhost:8080`
- HTTPS URL: `https://localhost:8081`
- Health check (ready): `http://localhost:8080/health` (returns `200` only when Discord bot is ready)
- Login: `WEB_ADMIN_DEFAULT_USERNAME` / `WEB_ADMIN_DEFAULT_PASSWORD`
- If `WEB_TLS_ENABLED=true` and cert/key files are not set, Flask runs with an adhoc self-signed certificate (requires `cryptography`, included in this image).
- Use the guild dropdown in the top nav to switch the server you are managing.
- Theme switcher (Light/Black) is available in the top nav and persists per browser.
- Login includes optional "Keep me signed in" mode (5-day max), inactivity timeout, and IP-based login attempt throttling.
- Pages:
  - Home (`/admin/home`)
  - Servers (`/admin/guilds`)
  - Dashboard (`/admin`)
  - Status (`/admin/status`)
  - Action history (`/admin/actions`)
  - Member activity (`/admin/member-activity`)
    - per-guild message activity leaderboards for `24h`, `7d`, `30d`, and `90d`
    - ZIP export for guild activity data, optionally filtered by role
  - Reddit feeds (`/admin/reddit`)
  - WordPress feeds (`/admin/wordpress`)
  - LinkedIn feeds (`/admin/linkedin`)
  - YouTube subscriptions (`/admin/youtube`)
  - Spicy Prompts (`/admin/spicy-prompts`)
    - refreshes prompt packs from the configured GitHub repo without restarting the bot
    - stores a guild-specific allowed Discord channel for `/spicy`
    - rejects non-age-restricted channels for Spicy Prompts use
    - shows cached pack count, prompt count, last sync status, and prompt preview
  - Observability (`/admin/observability`, login required)
  - Bot profile (`/admin/bot-profile`, admin only)
    - Includes bot username/nickname updates and avatar upload
  - Guild settings (`/admin/guild-settings`, admin only)
  - Logs viewer (`/admin/logs`)
  - Documentation viewer (`/admin/documentation`)
  - Wiki redirect (`/admin/wiki`)
  - Account self-service (`/admin/account`)
    - change email
    - change first name
    - change last name
    - change password
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

## Feed Automation

The web GUI also manages background notifications for:

- Reddit
- WordPress
- LinkedIn
- YouTube

Each feed integration supports:

- source/profile/site input
- selected Discord target channel
- schedule selection (`5m`, `10m`, `15m`, `30m`, `1h`, `3h`, `6h`)
- stored last-seen state in SQLite

LinkedIn support is experimental and depends on public activity being accessible without authentication.

## Spicy Prompts Repo Refresh

- Open `/admin/spicy-prompts` in the web GUI.
- Set the repo values in `env.env` or through the runtime settings page:
  - `SPICY_PROMPTS_REPO_URL`
  - `SPICY_PROMPTS_REPO_BRANCH`
  - `SPICY_PROMPTS_MANIFEST_PATH`
- Use the `Refresh From Repo` button to pull the latest prompt manifest and pack files without restarting the bot.
- The fetched prompt cache is stored in SQLite and visible in the page preview table.

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
docker compose --env-file env.env up -d
```

The shipped Compose example bind-mounts `${DATA_DIR:-/root/docker/wickedyodabot}` on the host to `/app/data` inside the container.
It also bind-mounts `${LOG_DIR:-/root/docker/wickedyodabot/log}` on the host to `/logs` inside the container.
`docker-compose.yml` overrides the bot's in-container `DATA_DIR` to `/app/data` and `LOG_DIR` to `/logs`.

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
