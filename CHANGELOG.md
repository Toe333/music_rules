# Changelog

All notable changes to `music-rules` will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
and the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- **Phase 4 — passage evaluator.** New `music_rules.core.evaluate.evaluate_passage`
  orchestrator that walks a complete piece (any number of equal-length voices)
  and runs every Phase-3 Fux checker at every applicable position, folding the
  per-fragment `CheckReport`s into a single `PassageReport`:
  ```python
  {
      "total_cost":      float,
      "hard_violations": [{"rule_id", "position", "voices_involved", "msg"}, ...],
      "soft_violations": [{"rule_id", "position", "cost", "msg"}, ...],
      "per_rule_summary": {"H1_1": {"count": 2, "total_cost": None}, ...},
      "grade":           "A" | "B" | "C" | "D" | "F",
  }
  ```
  Matches `docs/MCP_TOOL_SURFACE_SPEC.md` §2 Group D exactly. Supports
  `ruleset` (`"Fux" | "EIS" | "both"`, EIS is a no-op until Phase 7),
  `strict=` (hybrid → hard promotion, forward-compat), and
  `include` / `exclude` rule-ID filters.
- `evaluate_passage` re-exported from the top-level `music_rules` package.
- 22 new tests in `tests/test_evaluate.py`: report-shape compliance,
  4-bar passage validation, parallel-fifths failure detection, opening /
  closing interval isolation, include/exclude filters, ruleset switching,
  and piece-input validation. Total suite is now **88 tests, all passing**.

### Why

Without `evaluate_passage` every adapter (MCP, OpenAI, CLI, FastAPI) would
have to reinvent the same fan-out + fan-in over the per-fragment checkers,
and they'd inevitably drift in subtle ways (different position indexing,
different rule-summary aggregation, different grading rubric). Centralizing
it in `core/` keeps Phases 5/6/7 trivial — each adapter becomes a thin
shim that calls `evaluate_passage` and renders the result.

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
