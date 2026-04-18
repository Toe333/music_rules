# Changelog

All notable changes to `music-rules` will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
and the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

## [0.1.0] — 2026-04-18

### Added

- Initial repository scaffold and project layout (Phase 1).
- Unified rule corpus `rules_combined.json` (158 rules: 119 EIS, 39 Fux),
  installed as package data at `src/music_rules/data/`.
- Human-readable EIS rulebook `data/eis/EIS_MASTER_RULES.md`
  (18 sections, provenance-tagged).
- Spreadsheet exports of both rule systems under `data/tables/`.
- Raw extracted text from 5 Ted Greene EIS PDFs + 1 web supplement under
  `data/eis/extracted/` (development reference, excluded from wheel).
- Tool-surface design document `docs/MCP_TOOL_SURFACE_SPEC.md`.
- `PROJECT.md` orientation doc, `README.md` user-facing quickstart,
  `LICENSE` (MIT for code; data terms in `data/README.md`),
  `data/fux/FuxCP5_attribution.md` for the FuxCP5 reference implementation.
- `.gitignore` covering Python, uv, macOS, IDEs, and HuggingFace caches.

### Why this release exists

We need a clean git root to anchor the upcoming Phase 2 (package scaffold,
corpus loader, JSON Schema) and Phase 3 (first five Fux checkers). Pinning
the file layout and licensing posture *before* writing any business logic
means later phases never have to relitigate "where does this live?" or
"can we ship this file?" decisions.
