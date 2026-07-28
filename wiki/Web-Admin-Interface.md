# Web Admin Interface

Last Updated: 2026-07-28

The web admin is served by `web_admin.py`/`webui/app.py` and is mobile-friendly.

## Authentication and Session

- Login with `WEB_ADMIN_DEFAULT_USERNAME` / `WEB_ADMIN_DEFAULT_PASSWORD`.
- Optional "Keep me signed in" uses 5-day remember mode.
- Inactivity timeout uses `WEB_SESSION_TIMEOUT_MINUTES`.
- Login attempts are rate-limited per IP.
- Password rotation is enforced every 90 days.
- Existing users can update their own email, name, and password in `My Account`.
- Admins can manage other web users and guild access groups.
- Guild Admins can manage only the guilds assigned to their access groups.
- Read-only users can view the full portal but cannot submit changes.

## Security Controls

- CSRF enforcement: `WEB_ENFORCE_CSRF` (default `true`)
- Same-origin POST enforcement: `WEB_ENFORCE_SAME_ORIGIN_POSTS` (default `true`)
- Security headers are applied on responses (CSP, frame deny, no-store, etc.).
- Web audit logs are written to `web_gui_audit.log`.
- Avatar upload requests are bounded by request-size and per-file-size limits.
- SQLite storage uses WAL mode and foreign key enforcement.

## Navigation and Themes

- Theme switch in top nav (Light/Black/Ocean/Ember/Forest).
- "Go to page..." quick selector in nav.
- Guild selector at top controls the active guild context for guild-scoped pages.
- Guild access is filtered by the logged-in user's role (Admin vs Guild Admin vs Read-only).

## Key Pages

- Home: `/admin/home`
- Servers: `/admin/guilds`
- Dashboard: `/admin`
- Overview: `/admin/overview`
- Status: `/admin/status`
- Uptime monitors: `/admin/uptime-monitors`
- Actions: `/admin/actions`
- Random user: `/admin/random-user`
- Member activity: `/admin/member-activity`
- Reddit feeds: `/admin/reddit`
- WordPress feeds: `/admin/wordpress`
- LinkedIn feeds: `/admin/linkedin`
- YouTube subscriptions: `/admin/youtube`
- Spicy Prompts: `/admin/spicy-prompts`
- Logs: `/admin/logs`
- Logs download: `/admin/logs/download`
- Documentation viewer: `/admin/documentation`
- Wiki redirect: `/admin/wiki`
- Account management: `/admin/account`
- Users: `/admin/users` (login required, admin writes only)
- Guild Access: `/admin/guild-access` (login required, admin only)
- Command permissions: `/admin/command-permissions` (login required, admin writes only)
- Tag responses: `/admin/tag-responses` (login required, admin writes only)
- Guild settings: `/admin/guild-settings` (login required, admin writes only)
- Runtime settings editor: `/admin/settings` (login required, admin writes only)
- Observability: `/admin/observability` (login required)
- Bot profile: `/admin/bot-profile` (login required, admin writes only)
  - Update bot username
  - Update or clear guild nickname
  - Upload bot avatar (`WEB_AVATAR_MAX_UPLOAD_BYTES`)

## Member Activity

The web GUI includes a guild-scoped member activity view at `/admin/member-activity`.

- Shows message activity rankings for `24h`, `7d`, `30d`, and `90d` windows
- Supports optional filtering by Discord role
- Exposes ZIP export for the selected guild and role filter
- Uses internally tracked message activity stored in SQLite

## Public Status

- `/status` redirects to `/status/everything`
- `/status/everything` shows public status/health summary without login.

## Account Self-Service

Users can manage their own profile from `/admin/account`:

- change email
- change first name
- change last name
- change password

Profile changes require the current password. If the email is changed, the active session is updated to the new email.

## Roles and Guild Access

- `Admin`: full read/write access across all guilds and global pages.
- `Guild Admin`: read/write access for assigned guilds only.
- `Read-only`: view access only.

Guild Admin access is configured under `/admin/guild-access` by creating groups, assigning guilds to each group, and then assigning user emails to those groups.

## Feed Automation Pages

The web GUI includes guild-scoped automation pages for:

- Reddit
- WordPress
- LinkedIn
- YouTube

Each feed page allows:

- source/profile/site input
- target Discord channel selection
- polling schedule selection
- listing existing feed subscriptions
- deletion of existing feed subscriptions

See [Feed Integrations](./Feed-Integrations.md) for feed-specific behavior and limitations.

## Spicy Prompts

The web GUI includes a repo-backed `Spicy Prompts` page at `/admin/spicy-prompts`.

- Admin-only refresh button pulls prompt data from the configured GitHub repo without restarting the bot
- Displays configured repo URL, branch, manifest path, and resolved manifest URL
- Shows last refresh time, last successful sync, last error, cached pack count, and cached prompt count
- Includes cached pack listing and prompt preview from SQLite

Related env vars:

- `SPICY_PROMPTS_ENABLED`
- `SPICY_PROMPTS_REPO_URL`
- `SPICY_PROMPTS_REPO_BRANCH`
- `SPICY_PROMPTS_MANIFEST_PATH`
- `SPICY_PROMPTS_REQUEST_TIMEOUT_SECONDS`

## Restart Control

- `/admin/restart` is only useful when `WEB_RESTART_ENABLED=true`.
- Intended for containerized environments where process exit triggers container restart.

## Uptime Monitors

Uptime monitoring is configured per guild in `/admin/uptime-monitors`.

- Monitor types: HTTP, TCP, Status Page
- Target examples:
  - HTTP: `https://example.com`
  - TCP: `host:port`
  - Status Page: `https://status.example.com`
- Poll interval and timeout are configured per monitor.
- Alerts post to the per-guild uptime alert channel set in `/admin/guild-settings`.

## Logs

- Logs are surfaced under `/admin/logs`.
- Auto-refresh dropdown supports 1-120s intervals.
- Export all log files (with manifest) from `/admin/logs/download` or `/admin/logs/export`.

## Dashboard

- `/admin/overview` provides the full dashboard with status cards, command visibility, and recent actions.
- `/admin` provides a categorized directory of every admin page, grouped by Core, Community, Feeds, Uptime, Admin, and Account.


## Navigation

- Header navigation is simplified to Servers + Dashboard, with remaining pages and Logout in a dropdown menu.
