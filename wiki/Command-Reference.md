# Command Reference

Last Updated: 2026-03-28

Guild-scoped slash commands currently registered in `bot.py`.

This page documents slash commands only. Background feed automation configured in the web GUI is documented in [Feed Integrations](./Feed-Integrations.md).

Response visibility for most slash commands is controlled by `COMMAND_RESPONSES_EPHEMERAL`:
- `false` (default): bot responses are public in-channel
- `true`: bot responses are only visible to the command user

## `/ping`

- Description: Check if the bot is online.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Replies with `Wicked Yoda's Little Helper is online.`.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/sayhi`

- Description: Introduce the bot in the current channel.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Posts a public introduction message in the channel.
  - This response is intentionally non-ephemeral so everyone in the channel can see it.
  - Logs success to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/happy`

- Description: Post a random puppy picture in the channel.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Fetches a random dog image URL from `PUPPY_IMAGE_API_URL`.
  - Sends an embed with the image.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/cat`

- Description: Post a random cat picture.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Fetches an image from `CAT_IMAGE_API_URL`.
  - Sends an embed with the image.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/meme`

- Description: Post a random meme.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Fetches a meme from `MEME_API_URL`.
  - Rejects NSFW responses.
  - Sends an embed with title, subreddit, and image.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/dadjoke`

- Description: Return a random dad joke.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Fetches a joke from `DAD_JOKE_API_URL`.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/eightball`

- Description: Ask the bot a question and get a random magic eight-ball answer.
- Parameters:
  - `question` (`str`)
- Required user permissions: none
- Bot action:
  - Picks a random canned answer.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/coinflip`

- Description: Flip a coin.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Randomly returns `Heads` or `Tails`.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/roll`

- Description: Roll dice with expressions like `1d20`, `2d6+3`, or `4d8-1`.
- Parameters:
  - `expression` (`str`, optional) - default: `1d20`
- Required user permissions: none
- Bot action:
  - Validates dice count, sides, and modifier.
  - Returns individual rolls, subtotal, modifier, and total.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/dnd`

- Description: D&D 20th Anniversary helper family.
- Parent group: `/dnd`
- Required user permissions: none for public subcommands
- Bot action:
  - Uses local SQLite storage under `/app/data/dnd.db`.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel and SQLite action history.
- Subcommands:
  - `/dnd roll`
    - Description: 20th Anniversary Edition dice roll.
    - Parameters:
      - `pool` (`int`) - number of dice to roll, `1-50`
      - `difficulty` (`int`) - success threshold, `2-10`
      - `willpower` (`bool`) - add 1 automatic success
      - `modifier` (`int`, optional) - automatic successes/penalties, `-20` to `20`
      - `speciality` (`str`, optional) - specialty applied to the roll
      - `nightmare` (`int`, optional) - nightmare dice count, `0-50`
      - `no_botch` (`bool`) - 1s do not remove successes
      - `character` (`str`, optional) - linked character name
      - `notes` (`str`, optional) - extra notes
  - `/dnd general`
    - Description: General multi-set dice roll.
    - Parameters:
      - `dice_set_01` (`str`) - required dice set, e.g. `2d6`
      - `dice_set_02` through `dice_set_05` (`str`, optional) - additional dice sets
      - `modifier` (`int`, optional) - add/subtract from total
      - `difficulty` (`int`, optional) - total needed to pass
      - `notes` (`str`, optional) - extra notes
  - `/dnd initiative`
    - Description: Initiative tracker helpers.
    - Parameters:
      - `action` (`str`) - `new` to start a tracker, `roll` to add an entry
      - `dex_wits` (`int`) - Dexterity + Wits total
      - `character` (`str`, optional) - linked character name
      - `notes` (`str`, optional) - extra notes
  - `/dnd character`
    - Description: Storage-backed character helpers.
    - Parameters:
      - `action` (`str`) - `find`, `list`, or `delete`
      - `splat` (`str`, optional) - character type context
      - `name` (`str`, optional) - character name target

## `/choose`

- Description: Pick one option from a comma-, pipe-, or newline-separated list.
- Parameters:
  - `options` (`str`)
- Required user permissions: none
- Bot action:
  - Requires at least two options.
  - Randomly chooses one and returns it.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/roastme`

- Description: Send a playful roast to you or an optionally selected member.
- Parameters:
  - `target` (`discord.Member`, optional)
- Required user permissions: none
- Bot action:
  - Uses a light canned roast.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/compliment`

- Description: Send a compliment to you or an optionally selected member.
- Parameters:
  - `target` (`discord.Member`, optional)
- Required user permissions: none
- Bot action:
  - Uses a canned compliment.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/wisdom`

- Description: Return a random Yoda-style line.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Sends a short themed wisdom line.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/gif`

- Description: Post a reaction GIF for a selected theme.
- Parameters:
  - `theme` (`str`, optional) - one of `random`, `celebrate`, `laugh`, `hype`, `cute`
- Required user permissions: none
- Bot action:
  - Uses a curated internal GIF library.
  - Sends an embed with the selected GIF.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/poll`

- Description: Create a quick channel poll with two to ten options.
- Parameters:
  - `question` (`str`)
  - `options` (`str`) - comma- or pipe-separated options
- Required user permissions: none
- Bot action:
  - Posts the poll publicly in the channel.
  - Attempts to add matching number reactions (`1️⃣`-`🔟`).
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/questionoftheday`

- Description: Post a random conversation starter.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Posts the prompt publicly in the channel.
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/spicy`

- Description: Post a random spicy prompt from the cached repo-backed prompt library.
- Parameters:
  - `tag` (`str`, optional) - category tag, or `help` to list categories
- Required user permissions: none
- Bot action:
  - Only works when `SPICY_PROMPTS_ENABLED=true`.
  - Only works in the guild-specific channel configured from `/admin/spicy-prompts`.
  - Rejects use outside the configured channel.
  - Rejects use if the configured channel is not age-restricted.
  - If `tag=help`, lists available categories and usage.
  - If `tag=<category>`, pulls a prompt from that category; otherwise chooses a random category.
  - Rejects use when the prompt cache is empty and instructs admins to refresh from the web GUI.
  - Posts the prompt publicly in the configured channel.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

Example usage:
- `/spicy`
- `/spicy tag:help`
- `/spicy tag:dirty_truth`

## `/randomuser`

- Description: Pick a random guild member, excluding users picked in the last 30 days.
- Parameters:
  - `role` (`discord.Role`, optional) - restrict the selection to a specific role
- Required user permissions: none
- Bot action:
  - Excludes bots and recent picks for the same guild.
  - If a role is provided, only members with that role are eligible.
  - Replies with the selected member mention and eligible counts.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/translate`

- Description: Translate text to a selected language.
- Parameters:
  - `text` (`str`)
  - `language` (`choice`) - target language
- Required user permissions: none
- Bot action:
  - Uses `TRANSLATE_API_URL` (default LibreTranslate) to translate the input text.
  - Returns translated text (truncated if extremely long).
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/wikihelp`

- Description: Search the configured game help wiki.
- Parameters:
  - `query` (`str`)
- Required user permissions: none
- Bot action:
  - Requires `WIKI_SEARCH_ENABLED=true` and `WIKI_SEARCH_URL` configured.
  - Returns up to a small set of best matches.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/ollama`

- Description: Ask the configured Ollama model.
- Parameters:
  - `prompt` (`str`)
- Required user permissions: none
- Bot action:
  - Requires `OLLAMA_ENABLED=true` and `OLLAMA_BASE_URL` configured.
  - Uses `OLLAMA_MODEL` and `OLLAMA_TIMEOUT_SECONDS` for requests.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/countdown`

- Description: Count down to a future date.
- Parameters:
  - `event` (`str`)
  - `when` (`str`) - `YYYY-MM-DD` or `YYYY-MM-DD HH:MM`; UTC when no timezone is supplied
- Required user permissions: none
- Bot action:
  - Parses the target date and shows remaining time.
  - Rejects past dates or invalid formats.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

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
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

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
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/uptime`

- Description: Show current monitor health from the configured Uptime Kuma status page.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Calls Uptime Kuma API endpoints derived from `UPTIME_STATUS_PAGE_URL`.
  - Summarizes monitor counts (`Up`, `Down`, `Pending`, `Maintenance`, `Unknown`).
  - Includes a short list of currently down monitors.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/monitor`

- Description: Show internal uptime monitor status summary for the current guild.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Summarizes monitor counts and lists down monitors.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/logs`

- Description: View recent lines from `container_errors.log`.
- Parameters:
  - `lines` (`int`, range `10-400`) - number of recent lines to return
- Required user permissions: `Manage Messages`
- Bot action:
  - Reads latest lines from runtime error log file.
  - Sends inline code block when short enough, otherwise sends as a file attachment.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/stats`

- Description: Show the calling user's private message activity summary for the current guild.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Summarizes the user's recent message activity from the internal activity tracker.
  - Includes activity windows for the recent `24h`, `7d`, `30d`, and `90d` periods when data is available.
  - Uses an ephemeral/private response so only the calling user sees the output.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/leaderboard`

- Description: Show the guild member activity leaderboard for a selected time window.
- Parameters:
  - `window` (`str`, optional) - one of `1d`, `7d`, `30d`, `90d`
- Required user permissions: none
- Bot action:
  - Uses the internal member activity tracker.
  - Excludes bots and moderator-ranked members from the leaderboard output.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/trivia`

- Description: Get a random trivia question.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Sends a multiple-choice trivia prompt.
  - Includes the answer behind Discord spoiler formatting.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/wouldyourather`

- Description: Get a random would-you-rather prompt.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Sends a themed prompt.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/rps`

- Description: Play rock-paper-scissors against the bot.
- Parameters:
  - `choice` (`str`) - `rock`, `paper`, or `scissors`
- Required user permissions: none
- Bot action:
  - Randomly picks the bot's throw.
  - Reports win, loss, or tie.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/guess`

- Description: Play the guild guessing game.
- Parameters:
  - `number` (`int`, optional) - guess between `1` and `100`
- Required user permissions: none
- Bot action:
  - Maintains one active guessing game per guild in SQLite.
  - Starts a new game automatically when needed.
  - Returns higher/lower hints and resets the game after a correct guess.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/birthday set`

- Description: Store your birthday for the current guild.
- Parameters:
  - `date` (`str`) - `MM-DD`, `MM/DD`, or `YYYY-MM-DD`
- Required user permissions: none
- Bot action:
  - Stores month/day in SQLite for the current guild and user.
  - Returns the next upcoming occurrence date.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/birthday view`

- Description: View a stored birthday.
- Parameters:
  - `member` (`discord.Member`, optional) - defaults to the caller
- Required user permissions: none
- Bot action:
  - Returns the stored birthday and next occurrence date for the selected member.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/birthday upcoming`

- Description: Show upcoming birthdays for the current guild.
- Parameters:
  - `days` (`int`, optional) - future lookahead window, default `30`
- Required user permissions: none
- Bot action:
  - Lists upcoming birthdays from SQLite for the selected guild.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/birthday remove`

- Description: Remove your stored birthday.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Deletes the caller's birthday for the current guild from SQLite.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/help`

- Description: Show a quick overview of bot capabilities and command groups.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Sends a quick reference summary.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs action to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/tags`

- Description: List configured tag shortcuts.
- Parameters: none
- Required user permissions: none (unless overridden by command permissions policy)
- Bot action:
  - Lists currently configured tag keys.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs action to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

## `/tag`

- Description: Post the configured response for a specific tag.
- Parameters:
  - `name` (`str`) - tag key (with or without `!`)
- Required user permissions: none (unless overridden by command permissions policy)
- Bot action:
  - Sends configured tag response if found.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite.

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
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

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
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

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
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/untimeout`

- Description: Remove timeout from a member.
- Parameters:
  - `member` (`discord.Member`) - member to untimeout
  - `reason` (`str`, optional) - default: `No reason provided`
- Required user permissions: `Moderate Members`
- Bot action:
  - Clears member timeout.
  - Replies ephemerally with success or failure.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/purge`

- Description: Delete a number of recent messages.
- Parameters:
  - `amount` (`int`, range `1-100`) - number of messages to remove
- Required user permissions: `Manage Messages`
- Bot action:
  - Validates command is run in a channel context.
  - Defers response, purges messages, sends ephemeral count deleted.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

## `/unban`

- Description: Unban a user by Discord user ID.
- Parameters:
  - `user_id` (`str`) - target user ID
  - `reason` (`str`, optional)
- Required user permissions: `Ban Members`
- Bot action:
  - Attempts unban by ID.
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`.
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

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
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

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
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history.

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
