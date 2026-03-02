# WickedYoda's Little Helper Wiki

This folder contains internal project wiki docs for bot operations and command behavior.

## Pages

- [Command Reference](./Command-Reference.md) - active slash commands, parameters, and permission behavior.
- [Multi-Guild and Env Setup](./Multi-Guild-and-Env.md) - required/optional env vars and multi-guild startup patterns.
- [Web Admin Interface](./Web-Admin-Interface.md) - web GUI auth, pages, security controls, and operational notes.

## Web Admin Routes

- Public health and status:
  - `/healthz`
  - `/status`
  - `/status/everything`
- Login/session:
  - `/login`
  - `/logout`
- Core admin:
  - `/admin`
  - `/admin/actions`
  - `/admin/youtube`
  - `/admin/logs`
  - `/admin/wiki`
  - `/admin/account`
- Admin-only:
  - `/admin/users`
  - `/admin/command-permissions`
  - `/admin/tag-responses`
  - `/admin/guild-settings`
  - `/admin/settings`
  - `/admin/observability`
  - `/admin/bot-profile`
  - `/admin/restart` (only when `WEB_RESTART_ENABLED=true`)

## Maintenance Rule

Whenever a command is added, removed, or changed in `bot.py`:

1. Update [Command Reference](./Command-Reference.md) in the same commit/PR.
2. Verify command options, permission checks, and responses match code.
3. Keep the "Last Updated" date current.

## Source Of Truth

- Runtime behavior: `bot.py`
- Human documentation: this wiki folder
