# Changelog

## dnd-debug-logs-2026-07-30

### Added
- Edition-aware autocomplete for `/dnd roll` and `/dnd sheet`.
- Per-splat character sheet templates in `dnd/character_builder.py`.
- Full character sheet builder: `/dnd character create|show|edit|list|delete` with SQLite persistence via `dnd/characters.py`.
- Edition-aware dice rerouting for V5/W5/Hunter via `dnd/roll_router.py`.
- `/dnd group create|add|remove|list` with backend schema/service.
- `/dnd reproxy create|list` with tracking backend.
- Wikipedia reference `https://share.google/aEG5ltpsiHwTaw2Zc` surfaced in `/dnd info edition`.
- Resilient Wikipedia 3-level extraction with fallback metadata in `dnd/wiki_reference.py`.
- Debug logging across all `/dnd` commands for release-note evidence.
- Tagged release `dnd-debug-logs-2026-07-30`.

### Changed
- `/dnd roll` validates `system` against edition and executes through shared router.
- `/dnd sheet` validates splats/species against edition and routes 5e-style sheet rolls.
- `/dnd server setup` now records edition defaults in chronicle state.
- `/dnd` command group description updated to multi-edition wording.

### Fixed
- Duplicate decoration issue in `/dnd group` implementation.
- Missing debug coverage for `/dnd info`, `/dnd character`, and `/dnd server` reject paths.
