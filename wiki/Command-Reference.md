# Command Reference

Last Updated: 2026-07-28

Guild-scoped slash commands currently registered in `bot.py`.

This page documents slash commands only. Background feed automation configured in the web GUI is documented in [Feed Integrations](./Feed-Integrations.md).

Response visibility for most slash commands is controlled by `COMMAND_RESPONSES_EPHEMERAL`:
- `false` (default): bot responses are public in-channel
- `true`: bot responses are only visible to the command user

Roll commands support RPG presets plus dice expression input. See `/roll` for current parameter/choice behavior.

## Public / Fun

## `/ping`
- Description: Check if the bot is online.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Replies with `Wicked Yoda's Little Helper is online.`
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/sayhi`
- Description: Introduce the bot in the current channel.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Posts a public introduction message in the channel
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/happy`
- Description: Post a random puppy picture.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Fetches image from `PUPPY_IMAGE_API_URL`
  - Sends an embed with the image
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/cat`
- Description: Post a random cat picture.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Fetches image from `CAT_IMAGE_API_URL`
  - Sends an embed with the image
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/meme`
- Description: Post a random meme.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Fetches a meme from `MEME_API_URL`
  - Rejects NSFW responses
  - Sends an embed with title, subreddit, and image
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/dadjoke`
- Description: Return a random dad joke.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Fetches a joke from `DAD_JOKE_API_URL`
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/gif`
- Description: Post a reaction GIF for a selected theme.
- Parameters:
  - `theme` (`str`, optional) - one of `random`, `celebrate`, `laugh`, `hype`, `cute`
- Required user permissions: none
- Bot action:
  - Uses a curated internal GIF library
  - Sends an embed with the selected GIF
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## `/poll`
- Description: Create a quick channel poll with two to ten options.
- Parameters:
  - `question` (`str`)
  - `options` (`str`) - comma- or pipe-separated options
- Required user permissions: none
- Bot action:
  - Posts the poll publicly in the channel
  - Attempts to add matching reactions
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/questionoftheday`
- Description: Post a random conversation starter.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Posts the prompt publicly in the channel
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## `/trivia`
- Description: Get a random trivia question.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Sends a multiple-choice trivia prompt
  - Includes the answer behind Discord spoiler formatting
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## `/wouldyourather`
- Description: Get a random would-you-rather prompt.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Sends a themed prompt
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## `/rps`
- Description: Play rock-paper-scissors against the bot.
- Parameters:
  - `choice` (`str`) - `rock`, `paper`, or `scissors`
- Required user permissions: none
- Bot action:
  - Randomly picks the bot's throw
  - Reports win, loss, or tie
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## `/guess`
- Description: Play the guild guessing game.
- Parameters:
  - `number` (`int`, optional) - guess between `1` and `100`
- Required user permissions: none
- Bot action:
  - Maintains one active guessing game per guild in SQLite
  - Starts a new game automatically when needed
  - Returns higher/lower hints and resets the game after a correct guess
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## Interactive / Utility

## `/choose`
- Description: Pick one option from a comma-, pipe-, or newline-separated list.
- Parameters:
  - `options` (`str`)
- Required user permissions: none
- Bot action:
  - Requires at least two options
  - Randomly chooses one and returns it
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/shorten`
- Description: Create a short URL.
- Parameters:
  - `url` (`str`) - long URL to shorten
- Required user permissions: none
- Bot action:
  - Validates URL format (`http`/`https`)
  - Sends URL to `SHORTENER_BASE_URL` via Shortipy form POST
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/expand`
- Description: Resolve a short code or short URL to the destination URL.
- Parameters:
  - `value` (`str`) - numeric short code or full short URL
- Required user permissions: none
- Bot action:
  - Validates short code/URL against `SHORTENER_BASE_URL`
  - Reads redirect target and replies with destination URL
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/countdown`
- Description: Count down to a future date or event.
- Parameters:
  - `event` (`str`)
  - `when` (`str`) - `YYYY-MM-DD` or `YYYY-MM-DD HH:MM`; UTC when no timezone is supplied
- Required user permissions: none
- Bot action:
  - Parses the target date and shows remaining time
  - Rejects past dates or invalid formats
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/translate`
- Description: Translate text to a selected language.
- Parameters:
  - `text` (`str`)
  - `language` (`choice`) - target language
- Required user permissions: none
- Bot action:
  - Uses `TRANSLATE_API_URL` (default LibreTranslate)
  - Returns translated text
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## `/wikihelp`
- Description: Search the configured game help wiki.
- Parameters:
  - `query` (`str`)
- Required user permissions: none
- Bot action:
  - Requires `WIKI_SEARCH_ENABLED=true` and `WIKI_SEARCH_URL` configured
  - Returns up to a small set of best matches
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## `/ollama`
- Description: Ask the configured Ollama model.
- Parameters:
  - `prompt` (`str`)
- Required user permissions: none
- Bot action:
  - Requires `OLLAMA_ENABLED=true` and `OLLAMA_BASE_URL` configured
  - Uses `OLLAMA_MODEL` and `OLLAMA_TIMEOUT_SECONDS` for requests
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## `/uptime`
- Description: Show current monitor health from the configured Uptime Kuma status page.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Calls Uptime Kuma API endpoints derived from `UPTIME_STATUS_PAGE_URL`
  - Summarizes monitor counts
  - Includes a short list of currently down monitors
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/monitor`
- Description: Show internal uptime monitor status summary for the current guild.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Summarizes monitor counts and lists down monitors
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## `/leaderboard`
- Description: Show the guild member activity leaderboard for a selected time window.
- Parameters:
  - `window` (`str`, optional) - one of `1d`, `7d`, `30d`, `90d`
- Required user permissions: none
- Bot action:
  - Uses the internal member activity tracker
  - Excludes bots and moderator-ranked members from leaderboard output
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/stats`
- Description: Show the calling user's private message activity summary for the current guild.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Summarizes recent message activity for `24h`, `7d`, `30d`, and `90d` when data is available
  - Uses an ephemeral/private response
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/logs`
- Description: View recent lines from `container_errors.log`.
- Parameters:
  - `lines` (`int`, range `10-400`) - number of recent lines to return
- Required user permissions: `Manage Messages`
- Bot action:
  - Reads latest lines from runtime error log file
  - Sends inline code block when short enough, otherwise sends as a file attachment
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/randomuser`
- Description: Pick a random guild member, excluding users picked in the last 30 days.
- Parameters:
  - `role` (`discord.Role`, optional) - restrict selection to a specific role
- Required user permissions: none
- Bot action:
  - Excludes bots and recent picks for the same guild
  - If a role is provided, only members with that role are eligible
  - Replies with the selected member mention and eligible counts
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## Community / RPG

## `/roll`
- Description: Roll TTRPG dice with common RPG presets.
- Parameters:
  - `dice_type` (`choice`) - preset style, defaults to `d20`; supported presets include standard dice plus `d00/percentile`
  - `count` (`int`, optional) - number of dice, default `1`
  - `modifier` (`int`, optional) - numeric modifier, example `+2` or `-1`
- Required user permissions: none
- Bot action:
  - Validates dice count, sides, and modifier
  - Returns preset meaning text when available
  - Shows rolls list, subtotal, modifier, and total
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/spicy`
- Description: Post a random spicy prompt in the configured 18+ channel.
- Parameters:
  - `tag` (`str`, optional) - category tag, or `help` to list categories
- Required user permissions: none
- Bot action:
  - Only works when `SPICY_PROMPTS_ENABLED=true`
  - Only works in the guild-specific channel configured from `/admin/spicy-prompts`
  - Rejects use outside the configured channel
  - Rejects use if the configured channel is not age-restricted
  - If `tag=help`, lists available categories and usage
  - If `tag=<category>`, pulls a prompt from that category; otherwise chooses a random category
  - Rejects use when the prompt cache is empty
  - Posts the prompt publicly in the configured channel
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/color`
- Description: Choose your name color from the configured list.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Presents color selection from the bot-managed color palette/options
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/dnd`
- Description: D&D 20th Anniversary helper command group.
- Required user permissions: command-permission policy applies
- Bot action:
  - Uses local SQLite storage
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Schema is initialized automatically at runtime
  - Logs actions to SQLite action history
- Subcommands:
  - `/dnd character` - manage guild D&D character records
  - `/dnd session` - track story sessions with outcomes
  - `/dnd proxy` - record session proxies for absent players
  - `/dnd xp` - add/record XP transactions per character
  - `/dnd reward` - assign rewards/boons tied to character or session

## Social / Fun

## `/roastme`
- Description: Send a playful roast.
- Parameters:
  - `target` (`discord.Member`, optional)
- Required user permissions: none
- Bot action:
  - Uses a light canned roast
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## `/compliment`
- Description: Send a compliment.
- Parameters:
  - `target` (`discord.Member`, optional)
- Required user permissions: none
- Bot action:
  - Uses a canned compliment
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## `/wisdom`
- Description: Return a random Yoda-style line.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Sends a short themed wisdom line
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## `/eightball`
- Description: Ask the bot a question and get a random magic eight-ball answer.
- Parameters:
  - `question` (`str`)
- Required user permissions: none
- Bot action:
  - Picks a random canned answer
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## `/coinflip`
- Description: Flip a coin.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Randomly returns `Heads` or `Tails`
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs the interaction to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## Birthdays

## `/birthday set`
- Description: Store your birthday for the current guild.
- Parameters:
  - `date` (`str`) - `MM-DD`, `MM/DD`, or `YYYY-MM-DD`
- Required user permissions: none
- Bot action:
  - Stores month/day in SQLite for the current guild and user
  - Returns the next upcoming occurrence date
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/birthday view`
- Description: View a stored birthday.
- Parameters:
  - `member` (`discord.Member`, optional) - defaults to the caller
- Required user permissions: none
- Bot action:
  - Returns the stored birthday and next occurrence date for the selected member
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/birthday upcoming`
- Description: Show upcoming birthdays for the current guild.
- Parameters:
  - `days` (`int`, optional) - future lookahead window, default `30`
- Required user permissions: none
- Bot action:
  - Lists upcoming birthdays from SQLite for the selected guild
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/birthday remove`
- Description: Remove your stored birthday.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Deletes the caller's birthday for the current guild from SQLite
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## Tags

## `/tags`
- Description: List configured tag shortcuts.
- Parameters: none
- Required user permissions: none (unless overridden by command permissions policy)
- Bot action:
  - Lists currently configured tag keys
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs action to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## `/tag`
- Description: Post the configured response for a specific tag.
- Parameters:
  - `name` (`str`) - tag key (with or without `!`)
- Required user permissions: none (unless overridden by command permissions policy)
- Bot action:
  - Sends configured tag response if found
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

Message tags are also supported for `!tag` style messages when message content intent is available.

## Help

## `/help`
- Description: Show a quick overview of bot capabilities and command groups.
- Parameters: none
- Required user permissions: none
- Bot action:
  - Sends a quick reference summary
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs action to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite

## Moderation

## `/kick`
- Description: Kick a member from the server.
- Parameters:
  - `member` (`discord.Member`) - member to kick
  - `reason` (`str`, optional) - default: `No reason provided`
- Required user permissions: `Kick Members`
- Bot action:
  - Attempts to kick target member
  - Replies ephemerally with success or failure
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/ban`
- Description: Ban a member from the server.
- Parameters:
  - `member` (`discord.Member`) - member to ban
  - `reason` (`str`, optional) - default: `No reason provided`
  - `delete_days` (`int`, range `0-7`) - days of message history to delete
- Required user permissions: `Ban Members`
- Bot action:
  - Validates command is run in guild context
  - Bans member
  - Logs moderation action to action history

## `/timeout`
- Description: Timeout a member.
- Parameters:
  - `member` (`discord.Member`) - member to timeout
  - `minutes` (`int`, range `1-40320`)
  - `reason` (`str`, optional)
- Required user permissions: `Moderate Members`
- Bot action:
  - Applies timeout and replies with result
  - Logs success/failure

## `/untimeout`
- Description: Remove timeout from a member.
- Parameters:
  - `member` (`discord.Member`) - member to untimeout
  - `reason` (`str`, optional)
- Required user permissions: `Moderate Members`
- Bot action:
  - Clears timeout and replies with result
  - Logs success/failure

## `/purge`
- Description: Delete recent messages.
- Parameters:
  - `amount` (`int`, range `1-100`) - number of recent messages to delete
- Required user permissions: `Manage Messages`
- Bot action:
  - Deletes messages and replies with count
  - Logs success/failure

## `/unban`
- Description: Unban a user by Discord user ID.
- Parameters:
  - `user_id` (`str`)
  - `reason` (`str`, optional)
- Required user permissions: `Ban Members`
- Bot action:
  - Attempts unban by ID
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/addrole`
- Description: Add a role to a member.
- Parameters:
  - `member` (`discord.Member`)
  - `role` (`discord.Role`)
  - `reason` (`str`, optional)
- Required user permissions: `Manage Roles`
- Bot action:
  - Validates hierarchy constraints
  - Adds role when allowed
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

## `/removerole`
- Description: Remove a role from a member.
- Parameters:
  - `member` (`discord.Member`)
  - `role` (`discord.Role`)
  - `reason` (`str`, optional)
- Required user permissions: `Manage Roles`
- Bot action:
  - Validates hierarchy constraints
  - Removes role when allowed
  - Reply visibility follows `COMMAND_RESPONSES_EPHEMERAL`
  - Logs success/failure to configured guild log channel (or global `Bot_Log_Channel` fallback) and SQLite action history

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
