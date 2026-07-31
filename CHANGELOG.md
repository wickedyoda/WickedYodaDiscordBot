# Changelog

## dnd-debug-logs-2026-07-30

### Added
- Edition-aware autocomplete for `/dnd roll` and `/dnd sheet`.
- Per-splat character sheet templates in `dnd/character_builder.py`.
- `/dnd character create` now surfaces template fields.
- `/dnd group create|add|remove|list` with backend schema/service.
- `/dnd reproxy create|list` with tracking backend.
- Wikipedia reference `https://share.google/aEG5ltpsiHwTaw2Zc` surfaced in `/dnd info edition`.
- Debug logging across all `/dnd` commands for release-note evidence.
- Tagged release `dnd-debug-logs-2026-07-30`.

### Changed
- `/dnd roll` validates `system` against edition.
- `/dnd sheet` validates splats/species against edition.
- `/dnd server setup` now records edition defaults in chronicle state.

### Fixed
- Duplicate decoration issue in `/dnd group` implementation.
