# D&D 20th How-To

Last Updated: 2026-07-28

This page explains how to use the D&D 20th Anniversary Edition command set and how the story data is stored.

## Storage

* Local SQLite database: `/app/data/dnd.db`
* Schema is initialized automatically at bot startup
* No external database or user setup is required

## Quick Start

1. Enable D&D commands for your server via command-permission policy if required.
2. Use `/dnd` subcommands in a guild text channel.
3. Character, proxy, chronicle, XP, and reward data persist across bot restarts.

## Command Workflows

### Dice rolling

`/dnd roll`
* Use for World of Darkness / 20th Anniversary Edition dice pools.
* Required inputs: `pool` and `difficulty`
* Optional inputs: `willpower`, `modifier`, `speciality`, `nightmare`, `no_botch`, `character`
* If `character` matches a saved character name, the bot resolves it before display.

`/dnd general`
* Use for multi-set dice expressions.
* Required inputs: `dice_set_01`
* Optional inputs: `modifier`, `dice_set_02` through `dice_set_05`, `difficulty`, `notes`

### Initiative

`/dnd initiative action:new dex_wits:3`
* Creates a new initiative tracker for the current channel.

`/dnd initiative action:roll dex_wits:3`
* Adds your roll to the current tracker and shows turn order.

`/dnd initiative action:end`
* Removes the active initiative tracker for the current channel.

Initiative state is tracked per channel. Each entry stores a random d10 roll plus `dex_wits`, optional `modifier`, and `extra_actions`.

### Characters

`/dnd character action:find name:`
* Finds a saved character by name or splat search.

`/dnd character action:show name: splat:`
* Returns a formatted character view when exact name resolution succeeds.

`/dnd character action:sheet name: splat:`
* Returns a splat-aware sheet when the record exists.
* If the chronicle restricts `allowed_splats`, non-allowed splats are flagged in the sheet response.

`/dnd character action:list`
* Lists saved characters for the calling user in the current guild.

`/dnd character action:save name: splat: payload:`
* Saves character data for later lookup.

`/dnd character action:delete name:`
* Deletes a saved character record.

Sheet fields vary by splat. Supported special handling includes:
* `vampire20th` / `vampire`
* `werewolf` / `garou`
* `mage` / `m20`
* `demon` / `demon20th`
* `changeling` / `ctd`
* `wraith` / `wto`

### Proxies

`/dnd proxy action:create name: avatar_url:`
* Creates a saved proxy identity tied to your user/guild.

`/dnd proxy action:send name: message:`
* Sends a proxied message to the current channel.
* Uses template substitution for `{name}` and `{content}`.

`/dnd proxy action:reply name:`
* Confirms the proxy is active in the current channel.

`/dnd proxy action:list`
* Lists your saved proxies for this guild.

`/dnd proxy action:delete name:`
* Deletes a saved proxy.

### Chronicles

`/dnd chronicle action:create name:`
* Creates or updates the guild chronicle record.

`/dnd chronicle action:show`
* Shows chronicle settings for the current guild.

`/dnd chronicle action:update name:`
* Updates chronicle settings.

### Experience Points

`/dnd xp action:add amount: reason:`
* Adds XP to the calling user's guild pool.

`/dnd xp action:history`
* Shows recent XP entries for the calling user.

### Rewards

`/dnd reward action:create rule_name: threshold: reward:`
* Creates a reward rule with one initial tier.

`/dnd reward action:status`
* Evaluates recent XP history against reward rules and shows progress.

`/dnd reward action:ledger`
* Returns reward evaluation details.

## D&D Data Model

* Characters are keyed by guild + user + name.
* XP pools are keyed by guild + user.
* Reward rules are keyed by guild.
* Initiative trackers are keyed by channel.

## Notes

* All `/dnd` subcommands obey the command-permission policy.
* Most responses are ephemeral unless permission or access logic changes visibility.
* Bot-side D&D logging uses the standard interaction logging flow when helpers are provided.
