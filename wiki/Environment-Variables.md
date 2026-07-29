# Environment Variables

Last Updated: 2026-07-28

This page documents the main environment variables used by the bot and web GUI.

## Core

* `DISCORD_TOKEN` - Discord bot token.
* `MANAGED_GUILD_IDS` - comma-separated guild IDs the bot should manage.
* `GUILD_ID` - optional legacy single-guild default.
* `Bot_Log_Channel` - optional default log channel ID; can be overridden per guild in the web GUI.

## Web GUI

* `WEB_ENABLED` - enable or disable the web admin GUI.
* `WEB_BIND_HOST` - bind host; use `0.0.0.0` in Docker.
* `WEB_PORT` - HTTP web GUI port.
* `WEB_TLS_ENABLED` - enable HTTPS for the web GUI.
* `WEB_TLS_PORT` - HTTPS port, commonly `WEB_PORT + 1`.
* `WEB_TLS_CERT_FILE` - optional TLS certificate path.
* `WEB_TLS_KEY_FILE` - optional TLS private key path.
* `WEB_ADMIN_DEFAULT_USERNAME` - web GUI login username.
* `WEB_ADMIN_DEFAULT_PASSWORD` - web GUI login password.
* `WEB_ADMIN_DEFAULT_PASSWORD_HASH` - optional password hash instead of plaintext password.
* `WEB_SESSION_SECRET` - Flask session signing secret.
* `WEB_PUBLIC_BASE_URL` - public base URL used in password reset emails.
* `WEB_PASSWORD_RESET_ENABLED` - enable email-based password reset.
* `WEB_SMTP_HOST` - SMTP server hostname for password reset emails.
* `WEB_SMTP_PORT` - SMTP port.
* `WEB_SMTP_USERNAME` - optional SMTP username.
* `WEB_SMTP_PASSWORD` - optional SMTP password.
* `WEB_SMTP_FROM_EMAIL` - from address used in reset emails.
* `WEB_SMTP_FROM_NAME` - from display name used in reset emails.
* `WEB_SMTP_SECURITY` - `none`, `starttls`, or `ssl`.
* `WEB_SESSION_COOKIE_SECURE` - set `true` when using HTTPS.
* `WEB_SESSION_COOKIE_SAMESITE` - cookie SameSite policy.
* `WEB_SESSION_TIMEOUT_MINUTES` - web session timeout in minutes.
* `WEB_ENFORCE_CSRF` - enforce CSRF checks.
* `WEB_ENFORCE_SAME_ORIGIN_POSTS` - block cross-origin POST requests.
* `WEB_RESTART_ENABLED` - allow admin-triggered restart from the web GUI.
* `WEB_AVATAR_MAX_UPLOAD_BYTES` - max upload size for bot profile avatar uploads.

## Command behavior

* `COMMAND_RESPONSES_EPHEMERAL` - set `false` for public replies, `true` for user-only replies.
* `ENABLE_MEMBERS_INTENT` - set `true` only if Server Members Intent is enabled in Discord Developer Portal.

## Fun and integrations

* `PUPPY_IMAGE_API_URL`
* `PUPPY_IMAGE_TIMEOUT_SECONDS`
* `FUN_API_TIMEOUT_SECONDS`
* `CAT_IMAGE_API_URL`
* `MEME_API_URL`
* `DAD_JOKE_API_URL`
* `SHORTENER_ENABLED`
* `SHORTENER_BASE_URL`
* `SHORTENER_TIMEOUT_SECONDS`
* `TRANSLATE_API_URL`
* `WIKI_SEARCH_ENABLED`
* `WIKI_SEARCH_URL`
* `OLLAMA_ENABLED`
* `OLLAMA_BASE_URL`
* `OLLAMA_MODEL`
* `OLLAMA_TIMEOUT_SECONDS`

## Feeds and automation

* `YOUTUBE_NOTIFY_ENABLED`
* `YOUTUBE_POLL_INTERVAL_SECONDS`
* `YOUTUBE_REQUEST_TIMEOUT_SECONDS`
* `WORDPRESS_REQUEST_TIMEOUT_SECONDS`
* `LINKEDIN_REQUEST_TIMEOUT_SECONDS`

## Spicy Prompts

* `SPICY_PROMPTS_ENABLED`
* `SPICY_PROMPTS_REPO_URL`
* `SPICY_PROMPTS_REPO_BRANCH`
* `SPICY_PROMPTS_MANIFEST_PATH`
* `SPICY_PROMPTS_REQUEST_TIMEOUT_SECONDS`

## Uptime Status

* `UPTIME_STATUS_ENABLED`
* `UPTIME_STATUS_PAGE_URL`
* `UPTIME_STATUS_TIMEOUT_SECONDS`

## Storage

* `DATA_DIR` - host bind path for persistent bot data.
* `LOG_DIR` - host bind path for persistent logs.
* `WEB_ENV_FILE` - optional path to env file used by the web settings editor.

## Internal web links

* `WEB_GITHUB_WIKI_URL` - optional external wiki URL shown in the web GUI.
