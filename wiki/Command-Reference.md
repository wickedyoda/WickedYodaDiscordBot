# Command Reference

Last Updated: 2026-03-02

Guild-scoped slash commands currently registered in `bot.py`.

## `/ping`

- Description: Check if the bot is online.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Replies with `WickedYoda's Little Helper is online.` (ephemeral).
  - Logs success to `Bot_Log_Channel` and SQLite action history.

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
