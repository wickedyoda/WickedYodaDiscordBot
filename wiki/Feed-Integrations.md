# Feed Integrations

Last Updated: 2026-07-28

The bot supports background content notifications configured entirely through the web GUI. These feeds are guild-scoped: each server chooses its own sources, target channels, and polling schedules.

## Supported Feed Types

### Reddit

- Page: `/admin/reddit`
- Input:
  - subreddit name such as `r/python`
  - or subreddit URL such as `https://www.reddit.com/r/python`
- Output:
  - new subreddit posts are sent to the selected Discord channel
- Notes:
  - uses Reddit `new.json`
  - stores last seen post in SQLite to avoid reposting old content

### WordPress

- Page: `/admin/wordpress`
- Input:
  - WordPress site URL such as `https://wickedyoda.com`
- Output:
  - new site posts are sent to the selected Discord channel
- Notes:
  - discovers RSS/Atom feeds from common WordPress feed paths and `<link>` tags
  - seeds the latest post when saved so first poll does not backfill older posts

### YouTube

- Page: `/admin/youtube`
- Input:
  - YouTube channel URL
- Output:
  - new uploads, shorts, and optionally community posts are sent to the selected Discord channel
- Notes:
  - uploads and community posts can be enabled independently
  - latest known video/community post is stored in SQLite

### LinkedIn

- Page: `/admin/linkedin`
- Input:
  - public LinkedIn profile or page URL
- Output:
  - new public activity posts are sent to the selected Discord channel
- Notes:
  - experimental
  - only works when LinkedIn exposes recent activity without authentication
- LinkedIn may block scraping or show a sign-in wall, which prevents notifications

## Uptime Monitoring (Related)

Uptime monitors are configured separately under `/admin/uptime-monitors`, but they share the same guild-scoped behavior:

- Each guild can create HTTP, TCP, or Status Page monitors.
- Alerts post into the per-guild uptime alert channel set in `/admin/guild-settings`.

## Shared Feed Scheduling

All supported feed types use the same schedule options in the web GUI:

- `5 minutes`
- `10 minutes`
- `15 minutes`
- `30 minutes`
- `1 hour`
- `3 hours`
- `6 hours`

The bot runs a unified background notification loop and only polls feeds that are due.

## Feed Delivery Behavior

- Notifications are posted to the selected Discord text channel
- Each successful post is logged to:
  - the configured guild log channel when available
  - SQLite action history
- Feed state is stored in SQLite so the bot can resume after restart without reposting old content

## Environment Variables Related To Feeds

- `YOUTUBE_NOTIFY_ENABLED`
- `YOUTUBE_POLL_INTERVAL_SECONDS`
- `YOUTUBE_REQUEST_TIMEOUT_SECONDS`
- `WORDPRESS_REQUEST_TIMEOUT_SECONDS`
- `LINKEDIN_REQUEST_TIMEOUT_SECONDS`

These timeout variables affect feed resolution and polling, but feed sources and notify channels are configured from the web GUI rather than `env.env`.
