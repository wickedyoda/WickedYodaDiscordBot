# Wicked Yoda's Little Helper Wiki

Last Updated: 2026-07-28

This folder contains internal project wiki docs for bot operations, command behavior, feed automation, and web admin usage.

Current feature areas include slash commands, TTRPG dice rolls, D&D 20th story helpers, moderation commands, guild-scoped feeds, uptime monitoring, repo-backed Spicy Prompts content refresh, member activity reporting/leaderboards, multi-guild web admin portal with role-based access, wiki/doc viewers, short-URL helpers, quick-play games, logging/log export, and guild customization.

## Pages

- [Command Reference](./Command-Reference.md) - active slash commands, parameters, and permission behavior.
- [Feed Integrations](./Feed-Integrations.md) - Reddit, WordPress, YouTube, and LinkedIn automation configured from the web GUI.
- [Multi-Guild and Env Setup](./Multi-Guild-and-Env.md) - required/optional env vars and multi-guild startup patterns.
- [Web Admin Interface](./Web-Admin-Interface.md) - web GUI auth, pages, security controls, and operational notes.
- [Security Hardening](./Security-Hardening.md) - implemented runtime, auth, storage, and verification controls.

## Web Admin Routes

Public health and status:
  - `/healthz`
  - `/health`
  - `/status`
  - `/status/everything`

Login/session/reset:
  - `/login`
  - `/forgot-password`
  - `/reset-password/<token>`
  - `/logout`

Login required:
  - `/`
  - `/admin`
  - `/admin/home`
  - `/admin/overview`
  - `/admin/guilds`
  - `/admin/status`
  - `/admin/actions`
  - `/admin/random-user`
  - `/admin/member-activity`
  - `/admin/youtube`
  - `/admin/reddit`
  - `/admin/wordpress`
  - `/admin/linkedin`
  - `/admin/spicy-prompts`
  - `/admin/logs`
  - `/admin/logs/download`
  - `/admin/logs/export`
  - `/admin/wiki`
  - `/admin/documentation`
  - `/admin/documentation/<page_slug>`
  - `/admin/observability`
  - `/admin/bot-profile`
  - `/admin/account`
  - `/admin/honeypot`
  - `/admin/role-access`
  - `/admin/reaction-roles`
  - `/admin/discourse`
  - `/admin/uptime-monitors`
  - `/admin/users`
  - `/admin/guild-access`
  - `/admin/command-permissions`
  - `/admin/tag-responses`
  - `/admin/guild-settings`
  - `/admin/moderation`
  - `/admin/settings`

Write actions:
  - `/admin/guilds/kick`
  - `/admin/guilds/ban`
  - `/admin/guilds/timeout`
  - `/admin/guilds/untimeout`
  - `/admin/guilds/leave`
  - `/admin/users/add`
  - `/admin/users/update`
  - `/admin/users/delete`
  - `/admin/settings/save`
  - `/admin/restart` (only when `WEB_RESTART_ENABLED=true`)
  - `/admin/uptime-monitors/add`
  - `/admin/uptime-monitors/<int:monitor_id>/toggle`
  - `/admin/uptime-monitors/<int:monitor_id>/delete`
  - `/admin/guild-access/create`
  - `/admin/guild-access/update`
  - `/admin/guild-access/delete`
  - `/admin/honeypot/save`
  - `/admin/role-access/save`
  - `/admin/reaction-roles/save`
  - `/admin/discourse/save`
  - `/admin/spicy-prompts/refresh`
  - `/admin/spicy-prompts/settings`
  - `/admin/select-guild`

## Maintenance Rule

Whenever a command is added, removed, or changed in `bot.py`:
1. Update [Command Reference](./Command-Reference.md) in the same commit/PR.
2. Verify command options, permission checks, and responses match code.
3. Keep the "Last Updated" date current.

Whenever a web-managed automation or admin capability is added or changed:
1. Update [Feed Integrations](./Feed-Integrations.md) if the change affects background notifications.
2. Update [Web Admin Interface](./Web-Admin-Interface.md) if the change affects the GUI, auth, or account management.
3. Update [Multi-Guild and Env Setup](./Multi-Guild-and-Env.md) if new env vars or guild-scoped behaviors are introduced.
4. Update the shipped examples (`env.env`, `docker-compose.yml`) when container paths or runtime storage defaults change.

Whenever activity reporting or analytics views change:
1. Update [Command Reference](./Command-Reference.md) if `/stats` behavior changes.
2. Update [Web Admin Interface](./Web-Admin-Interface.md) if `/admin/member-activity` layout, export, or permissions change.

## Source Of Truth

- Runtime behavior: `bot.py`
- Human documentation: this wiki folder

Recent updates include `/color` role-picker command, latest roll presets plus `/roll` meaning text, Discord interaction-access checks for slash commands, D&D 20th subcommands (`/dnd character`, `/dnd session`, `/dnd proxy`, `/dnd xp`, `/dnd reward`), compact public repo README, expanded web admin route coverage plus CI/python-verification merge gate and pip-audit vulnerability baseline.
