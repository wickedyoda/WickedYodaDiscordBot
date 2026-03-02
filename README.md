# WickedYoda's Little Helper

Basic moderation Discord bot with a mobile-friendly web admin GUI, designed to run in Docker using `env.env`.

## Wiki

Project wiki files live in [`wiki/`](wiki/).

- [`wiki/Home.md`](wiki/Home.md) - wiki index and maintenance workflow
- [`wiki/Command-Reference.md`](wiki/Command-Reference.md) - full slash command documentation

When adding or changing a bot command, update `wiki/Command-Reference.md` in the same pull request.

## Environment Variables

Set these in `env.env`:

- `DISCORD_TOKEN` - your bot token
- `GUILD_ID` - your Discord server (guild) ID
- `Bot_Log_Channel` - text channel ID where bot action logs are posted
- `WEB_ENABLED` - enable web GUI (`true`/`false`)
- `WEB_BIND_HOST` - web server bind host (use `0.0.0.0` in Docker)
- `WEB_PORT` - web GUI port inside container
- `ENABLE_MEMBERS_INTENT` - set `true` only if you enabled Server Members Intent in Discord Developer Portal
- `SHORTENER_ENABLED` - enable Shortipy integration commands (`/shorten`, `/expand`)
- `SHORTENER_BASE_URL` - Shortipy base URL (example: `https://l.twy4.us`)
- `SHORTENER_TIMEOUT_SECONDS` - timeout for Shortipy requests
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
- `DATA_DIR` - persistent internal data directory for moderation action history (recommended: `/app/data`)

## Included Slash Commands

- `/ping`
- `/sayhi`
- `/shorten`
- `/expand`
- `/uptime`
- `/kick`
- `/ban`
- `/timeout`
- `/untimeout`
- `/purge`

Detailed command behavior, parameters, and permission requirements are documented in [`wiki/Command-Reference.md`](wiki/Command-Reference.md).

All command actions (success/failure) are logged to `Bot_Log_Channel`.
All actions are also written to SQLite and visible in the web GUI.

SQLite storage is internal to the container at `/app/data/mod_actions.db`.

## Web Admin GUI

- URL: `http://localhost:8080`
- Login: `WEB_ADMIN_DEFAULT_USERNAME` / `WEB_ADMIN_DEFAULT_PASSWORD`
- Pages:
  - Dashboard (`/admin`)
  - Action history (`/admin/actions`)
  - Runtime settings view (`/admin/settings`)

The GUI is built with responsive Bootstrap layout for mobile and desktop.

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

## Docker Image Publish (GitHub Packages / GHCR)

Workflow: `.github/workflows/docker-publish.yml`

- Publishes on push to `main`, semantic version tags (`v*.*.*`), or manual run.
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
