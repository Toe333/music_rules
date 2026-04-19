# Changelog

All notable changes to `music-rules` will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
and the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- **Phase 5 — MCP adapter.** New `music_rules.adapters.mcp` module
  exposing **27 tools** to any MCP-compatible client (Claude Desktop,
  Cursor, etc.) over `fastmcp`'s stdio transport:
  - **Group A — Corpus introspection** (7 tools): `list_rule_systems`,
    `list_rule_categories`, `list_rule_kinds`, `list_input_shapes`,
    `get_rules`, `get_rule`, `explain_rule` (the last includes a
    derived `checker_hint` so an agent can discover which Group-C tool
    to call without a hardcoded mapping).
  - **Group C — Fux checkers** (9 tools, the Phase-3 set):
    `check_melodic_interval`, `check_melodic_triple`,
    `check_motion_pair`, `check_vertical_chord`, `check_first_interval`,
    `check_final_interval`, `check_per_measure_downbeat`,
    `check_weak_beat_interval`, `check_dissonance_context`.
  - **Group D** (1 tool): `evaluate_passage`.
  - **Groups B & E — Phase-7 stubs** (10 tools): every EIS helper and
    SkyTNT-bridge tool is exposed today as a stub returning a
    `{"status": "not_implemented", "available_in": "Phase 7", ...}`
    payload. This means MCP clients can already discover the *future*
    tool surface — when Phase 7 lands, only the function bodies change.
- The adapter is split into **(a)** plain-Python tool implementations
  (importable and unit-testable without `fastmcp`) and **(b)** a
  `build_server()` factory that does the lazy `fastmcp` import. Tests
  exercise the implementation layer exhaustively (39 cases) plus a
  smoke test that constructs the real `FastMCP` server.
- `examples/mcp_config.json`: drop-in snippet for Claude Desktop and
  Cursor's `~/.cursor/mcp.json` with three command alternatives
  (console script, `python -m`, and `uv run`).
- Suite total is now **127 tests, all passing**.

### Why

The MCP adapter is the first AI-facing surface — it's what Cursor's
agent and Claude Desktop will actually call. Splitting "what each tool
does" from "how the server is wired up" means future adapters
(OpenAI in Phase 6, FastAPI later) can re-use the exact same
`call_tool(name, args)` dispatcher without any of `fastmcp`'s
runtime cost. Stubbing the Phase-7 tools today (rather than
omitting them) lets us nail the public tool surface once and avoid a
breaking change when EIS helpers and SkyTNT bridges land.

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
