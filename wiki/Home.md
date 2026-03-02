# WickedYoda's Little Helper Wiki

This folder contains internal project wiki docs for bot operations and command behavior.

## Pages

- [Command Reference](./Command-Reference.md) - all active slash commands and permission requirements.

## Maintenance Rule

Whenever a command is added, removed, or changed in `bot.py`:

1. Update [Command Reference](./Command-Reference.md) in the same commit/PR.
2. Verify command options, permission checks, and responses match code.
3. Keep the "Last Updated" date current.

## Source Of Truth

- Runtime behavior: `bot.py`
- Human documentation: this wiki folder
