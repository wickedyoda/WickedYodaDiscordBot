# Command Reference

Last Updated: 2026-03-02

Guild-scoped slash commands currently registered in `bot.py`.

Response visibility for most slash commands is controlled by `COMMAND_RESPONSES_EPHEMERAL`:
- `false` (default): bot responses are public in-channel
- `true`: bot responses are only visible to the command user

## `/ping`

- Description: Check if the bot is online.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Replies with `WickedYoda's Little Helper is online.` (ephemeral).
  - Logs success to `Bot_Log_Channel` and SQLite action history.

## `/sayhi`

- Description: Introduce the bot in the current channel.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Posts a public introduction message in the channel.
  - Logs success to `Bot_Log_Channel` and SQLite action history.

## `/happy`

- Description: Post a random puppy picture in the channel.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Fetches a random dog image URL from `PUPPY_IMAGE_API_URL`.
  - Sends an embed with the image.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to `Bot_Log_Channel` and SQLite action history.

## `/shorten`

- Description: Create a short URL with the configured Shortipy instance.
- Parameters:
  - `url` (`str`) - long URL to shorten
- Required user permissions: none
- Bot action:
  - Validates URL format (`http`/`https`).
  - Sends URL to `SHORTENER_BASE_URL` via Shortipy form POST.
  - Replies with generated short URL.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to `Bot_Log_Channel` and SQLite action history.

## `/expand`

- Description: Resolve a short code or short URL to the destination URL.
- Parameters:
  - `value` (`str`) - numeric short code (for example `1234`) or full short URL
- Required user permissions: none
- Bot action:
  - Validates short code/URL against `SHORTENER_BASE_URL`.
  - Requests short URL and reads redirect target.
  - Replies with expanded destination URL.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to `Bot_Log_Channel` and SQLite action history.

## `/uptime`

- Description: Show current monitor health from the configured Uptime Kuma status page.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Calls Uptime Kuma API endpoints derived from `UPTIME_STATUS_PAGE_URL`.
  - Summarizes monitor counts (`Up`, `Down`, `Pending`, `Maintenance`, `Unknown`).
  - Includes a short list of currently down monitors.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to `Bot_Log_Channel` and SQLite action history.

## `/logs`

- Description: View recent lines from `container_errors.log`.
- Parameters:
  - `lines` (`int`, range `10-400`) - number of recent lines to return
- Required user permissions: `Manage Messages`
- Bot action:
  - Reads latest lines from runtime error log file.
  - Sends inline code block when short enough, otherwise sends as a file attachment.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to `Bot_Log_Channel` and SQLite action history.

## `/help`

- Description: Show a quick overview of bot capabilities and command groups.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Sends a quick reference summary.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs action to `Bot_Log_Channel` and SQLite.

## `/tags`

- Description: List configured tag shortcuts.
- Parameters: none
- Required user permissions: none (unless overridden by command permissions policy)
- Bot action:
  - Lists currently configured tag keys.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs action to `Bot_Log_Channel` and SQLite.

## `/tag`

- Description: Post the configured response for a specific tag.
- Parameters:
  - `name` (`str`) - tag key (with or without `!`)
- Required user permissions: none (unless overridden by command permissions policy)
- Bot action:
  - Sends configured tag response if found.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to `Bot_Log_Channel` and SQLite.

Message tags are also supported for `!tag` style messages when message content intent is available.

## `/kick`

- Description: Kick a member from the server.
- Parameters:
  - `member` (`discord.Member`) - member to kick
  - `reason` (`str`, optional) - default: `No reason provided`
- Required user permissions: `Kick Members`
- Bot action:
  - Attempts to kick target member.
  - Replies ephemerally with success or failure.
  - Logs success/failure to `Bot_Log_Channel` and SQLite action history.

## `/ban`

- Description: Ban a member from the server.
- Parameters:
  - `member` (`discord.Member`) - member to ban
  - `reason` (`str`, optional) - default: `No reason provided`
  - `delete_days` (`int`, range `0-7`) - days of message history to delete
- Required user permissions: `Ban Members`
- Bot action:
  - Validates command is run in guild context.
  - Bans member and converts `delete_days` to seconds for Discord API.
  - Replies ephemerally with success or failure.
  - Logs success/failure to `Bot_Log_Channel` and SQLite action history.

## `/timeout`

- Description: Timeout a member for a number of minutes.
- Parameters:
  - `member` (`discord.Member`) - member to timeout
  - `minutes` (`int`, range `1-40320`) - timeout duration
  - `reason` (`str`, optional) - default: `No reason provided`
- Required user permissions: `Moderate Members`
- Bot action:
  - Sets timeout expiration (`now + minutes`).
  - Replies ephemerally with success or failure.
  - Logs success/failure to `Bot_Log_Channel` and SQLite action history.

## `/untimeout`

- Description: Remove timeout from a member.
- Parameters:
  - `member` (`discord.Member`) - member to untimeout
  - `reason` (`str`, optional) - default: `No reason provided`
- Required user permissions: `Moderate Members`
- Bot action:
  - Clears member timeout.
  - Replies ephemerally with success or failure.
  - Logs success/failure to `Bot_Log_Channel` and SQLite action history.

## `/purge`

- Description: Delete a number of recent messages.
- Parameters:
  - `amount` (`int`, range `1-100`) - number of messages to remove
- Required user permissions: `Manage Messages`
- Bot action:
  - Validates command is run in a channel context.
  - Defers response, purges messages, sends ephemeral count deleted.
  - Logs success/failure to `Bot_Log_Channel` and SQLite action history.

## `/unban`

- Description: Unban a user by Discord user ID.
- Parameters:
  - `user_id` (`str`) - target user ID
  - `reason` (`str`, optional)
- Required user permissions: `Ban Members`
- Bot action:
  - Attempts unban by ID.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to `Bot_Log_Channel` and SQLite action history.

## `/addrole`

- Description: Add a role to a member.
- Parameters:
  - `member` (`discord.Member`) - member to update
  - `role` (`discord.Role`) - role to add
  - `reason` (`str`, optional)
- Required user permissions: `Manage Roles`
- Bot action:
  - Validates member/role hierarchy constraints.
  - Adds role on success.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to `Bot_Log_Channel` and SQLite action history.

## `/removerole`

- Description: Remove a role from a member.
- Parameters:
  - `member` (`discord.Member`) - member to update
  - `role` (`discord.Role`) - role to remove
  - `reason` (`str`, optional)
- Required user permissions: `Manage Roles`
- Bot action:
  - Validates member/role hierarchy constraints.
  - Removes role on success.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to `Bot_Log_Channel` and SQLite action history.

## Shared Error Behavior

For moderation commands (`kick`, `ban`, `timeout`, `untimeout`, `purge`):

- Missing user permissions:
  - User gets ephemeral `You do not have permission to use this command.`
  - Bot logs a `permission_denied` action.
- Missing bot permissions:
  - User gets ephemeral `I do not have the permissions needed for that action.`
  - Bot logs a `bot_missing_permissions` action.
- Other command exceptions:
  - User gets ephemeral `An unexpected error occurred.`
  - Bot logs a `command_error` action.

## Update Checklist (When Adding Commands)

When you add a new `@bot.tree.command` in `bot.py`:

1. Add a new section here with description, parameters, and required permissions.
2. Document success/failure responses and logging behavior.
3. Update the "Last Updated" date at the top of this file.
