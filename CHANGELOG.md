# Changelog

All notable changes to `music-rules` will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
and the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- **Phase 8 — full EIS composer, SkyTNT generation, voice-range
  constraints, per-voice instruments, Cowork compose skill.** All
  Phase-7 stubs are now live. Tests: 236 → 316 (80 new). MCP tool
  surface: 27 → 34. `core/` is still pure Python (only
  `skytnt_bridge.py` reaches for `transformers`/`torch`, lazily).
  - **`music_rules.core.eis.chords`** — chord builder. Public API:
    - `CHORD_CLASSES` and `list_chord_classes()` — frozen registry
      of triads, 6/7/9/11/13 chords, altered dominants (♭9 / ♯9 /
      ♯11 / ♭13), suspended chords, 4th-chord stacks (3-/4-part), and
      polytonal upper-structure stacks. Each entry is defined by
      semitone intervals from the root (so altered tones like ♭9 are
      handled cleanly, independent of scale degree) plus an
      `implied_scale` and `quality` for melodic context.
    - `pitch_classes(root, chord_class, *, scale_id=None)` and
      `build_chord(root, chord_class, *, scale_id=None, parts=None,
      voicing="close"|"open", inversion=0, base_octave=4)` — produce
      MIDI numbers with smart reductions (drop the 5th first if the
      target `parts` count is smaller than the chord's intervals,
      then truncate from the top), inversion handling (lowest-up by
      octave), and "open" drop-2 voicing.
  - **`music_rules.core.eis.voice_leading`** — voice-leading
    formalising V-001..V-015. Public API:
    - `voice_lead(prev_chord, next_pcs, *, style="bracket"|"parallel",
      max_jump=12)` — re-voice a target chord so each voice moves by
      the smallest possible amount, holding common tones (V-001),
      moving to nearest tones (V-002), and avoiding parallel octaves
      (V-014). `parallel` style respects soft V-007 brackets.
    - `check_progression(prev_chord, next_chord)` — score an existing
      two-chord move. Returns `{smoothness (0..1), common_tones,
      total_motion, contrary_motion, violations: [...rules]}` with
      explicit V-002 (large jumps), V-007/V-008 ("no three tones
      together"), V-014 (parallel octaves), and V-015
      (contrary-motion preference) flagging.
  - **`music_rules.core.eis.nct`** — Non-Chord Tone insertion. Public
    API: `NCT_TYPES`, `list_nct_types()`, and `insert_nct(chord_a,
    chord_b, *, voice, nct_type, scale_id, beat=0.5)` for the six
    Murphy NCT categories (Passing Tone, Chromatic Alteration,
    Returning Tone, Chord Tone, Suspension, Anticipation). Returns
    an `NCTEvent` with the inserted MIDI pitch + beat position.
  - **`music_rules.core.eis.ood`** — Outside-Octave Dissonance
    checker. Public API: `OOD_RULES`, `check_voicing(chord, *,
    has_b7=False, has_pedal=False)`, `check_passage(chords, ...)`.
    Flags O-001 (♭9 across an octave), O-002 (♭9 without ♭7), and
    O-003 (♭2 across an octave when no pedal), with the documented
    Murphy exceptions (♭9 + ♭7 OK; ♭2 over a pedal OK).
  - **`music_rules.core.eis.scales`** — promoted **all 14 previously
    `pending` scales to `inferred` status** with concrete degree
    lists derived from standard EIS / jazz / modal theory (Dorian,
    Phrygian, Lydian, Mixolydian, Aeolian, Harmonic Minor, Melodic
    Minor, Whole Tone, Altered, Locrian, Bebop Dominant, etc.). The
    full 1..18 surface is now usable end-to-end; the test suite
    keeps a synthetic-pending fixture so the `ValueError` path stays
    exercised.
  - **`music_rules.core.midi.skytnt_bridge`** — SkyTNT generation
    fully wired:
    - `skytnt_generate(prompt_midi=None, *, max_new_tokens=512,
      temperature=1.0, top_p=0.94, top_k=20, seed=None,
      model_id="skytnt/midi-model")` — lazy-imports `torch` +
      `transformers` (so the dependency stays optional), caches the
      model + tokenizer, and returns base64 MIDI.
    - `skytnt_constrained_generate(prompt_midi, *, ruleset="both",
      max_hard_violations=0, max_total_cost=5.0,
      num_candidates_per_try=4, max_tries=4, ...)` — the
      propose-then-check loop: generates `num_candidates_per_try`
      candidates per try, runs each through `evaluate_passage`,
      keeps the best one that satisfies the caps (or the cheapest
      ever seen if nothing fully qualifies). Returns
      `{midi_base64, accepted, tries, report}`.
    - Both raise `SkyTNTUnavailableError` with a clear "install
      `music-rules[skytnt]`" message if the optional extras are
      missing — no surprise import failures at module load.
    - `rolls_to_midi(voices, ..., programs=[...])` — new optional
      `programs` parameter assigns a different General-MIDI program
      per voice, enabling chip-tune (`[80, 80, 87, 122]`) or mixed
      orchestrations (`[0, 48, 48, 48]` = piano + 3× ensemble
      strings).
  - **`music_rules.core.evaluate`** — passage evaluator extended:
    - **EIS pass** — when `ruleset` is `"EIS"` or `"both"` (the
      default), now actually runs `eis_ood.check_voicing` over each
      vertical sonority and reports OOD hits as soft violations. Can
      be disabled with `check_ood=False`.
    - **Voice-range constraints (RG-001)** — new `voice_ranges`
      field on `PassagePiece`. Accepts the `"satb"` preset (mapping
      to standard SATB ranges) or an explicit `[[low, high], ...]`
      list; pitches outside the per-voice range become hard
      violations.
  - **MCP adapter** — wired all new tools and bumped the surface
    from 27 → 34 live tools. Group B (EIS helpers) and Group E
    (SkyTNT bridge) no longer have any stubs:
    - **Group B live**: `eis_pick_root_line`, `eis_list_scales`,
      `eis_list_chord_classes`, `eis_build_chord`, `eis_voice_lead`,
      `eis_check_voice_leading`, `eis_insert_nct`,
      `eis_list_nct_types`, `eis_check_ood`.
    - **Group E live**: `midi_to_rolls`, `rolls_to_midi` (now
      accepts `programs`), `skytnt_generate`,
      `skytnt_constrained_generate` (returns
      `{"status": "skytnt_unavailable", "fix": "..."}` if extras
      missing).
  - **Cowork plugin bundle** — fourth skill added:
    - **`music-rules-compose`** — the headline "generate music"
      skill. Teaches the agent the five-step symbolic composition
      recipe (Root-line → chord class → build → voice-lead →
      render+grade) plus the SkyTNT propose-then-check loop, with a
      cookbook for common requests (EIS harmonisation, Bach 3-part
      invention in 1st species, chip-tune arrangement, piano +
      strings re-orchestration). Hard rule: always finish with
      `evaluate_passage` so output is graded before being handed
      back. Plugin manifest + README updated to advertise the
      expanded tool surface.

- **Phase 7 — EIS roots + scales, SkyTNT scaffolding, Cowork plugin.**
  - **`music_rules.core.eis.roots`** — full implementation of Spud
    Murphy's six Equal-Interval cycles (E1..E6, generating intervals
    minor 2nd → tritone). Public API:
    - `E_CYCLES` and `CYCLE_LENGTHS` — frozen registries.
    - `cycle_root_pcs(cycle, start)` and `cycle_root_names(cycle,
      start, *, style="auto")` — generate an entire cycle as pitch
      classes or note-name strings (auto picks flats for E5 ⟂ sharps
      elsewhere, matching how Murphy / Greene notate them).
    - `pick_root_line(length, cycles=None, *, start_root="C",
      allow_elision=True, seed=None)` — generate a Root-line of N
      tones, walking through one or more cycles with optional 1- /
      2-step elision at cycle boundaries; deterministic given a seed.
    - `is_valid_progression(roots, *, allowed_cycles=None)` — judge
      Root progressions by interval class, so inversions count
      (C → G is valid in E5 even though E5's canonical step is the P4).
  - **`music_rules.core.eis.scales`** — registry for the 18 EIS
    scales. Ships **4 verified / inferred definitions** today
    (Scale #1 Natural Major, #4 + #5 Lydian Dominant / overtone,
    #10 Dominant 7♭9 / Half-Whole Diminished — all derived from
    explicit master-rules-doc references) and 14 honest `pending`
    placeholders so callers can already enumerate the full 1..18
    surface. Public API: `SCALES`, `list_scales(*, status=None)`,
    `get_scale(scale_id)`, `scale_pcs(scale_id, root)`,
    `available_count()`.
  - **`music_rules.core.eis.chords` / `voice_leading` / `nct`** —
    Phase-8 stubs. Importable, documented, raise
    `NotImplementedError` with a clear pointer to the Phase-8 plan.
  - **`music_rules.core.midi.skytnt_bridge`** — MIDI round-trip for
    SkyTNT integration (the *only* file in `core/` permitted to
    import `transformers` / `huggingface_hub` per
    Non-Negotiable #1):
    - `midi_to_rolls(midi_input, *, beats_per_quarter=1)` decodes a
      base64 MIDI blob (or filesystem path) into per-voice MIDI-number
      lists with rests as `-1`, plus inferred meta (meter, tempo,
      key guess, ticks-per-beat).
    - `rolls_to_midi(voices, *, meter, tempo, ticks_per_beat,
      velocity, program)` encodes per-voice piano-rolls into a
      base64-encoded MIDI string. Round-trip with `midi_to_rolls`
      is exact at the grid step.
    - `skytnt_generate(...)` and `skytnt_constrained_generate(...)`
      are scaffolded with locked signatures and a documented
      Phase-8 implementation plan; calling either raises
      `NotImplementedError` today.
  - **MCP adapter** rewires Group B's `eis_pick_root_line` and
    `eis_list_scales` and Group E's `midi_to_rolls` and
    `rolls_to_midi` from stubs to the real implementations. The
    remaining 6 stubs (4 EIS + `skytnt_generate{,_constrained}`)
    keep the same shape but now report `available_in: "Phase 8"`.
  - **`music-rules.plugin/`** — drop-in Cowork / Cursor plugin
    bundle at the repo root, packaging the MCP server + 3 skills:
    - `music-rules-setup` — first-time install / activation flow
      with a `music-rules-mcp --help` health probe.
    - `music-rules-corpus` — guided pattern for browsing rules by
      system / category / kind / input-shape, with anti-patterns to
      keep agents from inventing rule IDs.
    - `music-rules-evaluate` — turn-key recipe for assembling a
      `piece` payload, calling `evaluate_passage`, summarising
      grade + violations, and round-tripping SkyTNT MIDI.
    - Companion `mcp.json` (registers the `music-rules` server
      against the `music-rules-mcp` console script) and
      `.cursor-plugin/plugin.json` manifest.
- 60 new tests across `test_eis_roots.py` (33), `test_eis_scales.py`
  (14), and `test_skytnt_bridge.py` (12), plus 8 reworked tests in
  `test_mcp_adapter.py` covering Phase-7 live wiring. Suite total:
  **236 passing** (up from 176).

### Why

Phase 7 closes the loop on the "portable core, thin adapters"
promise. By implementing E1..E6 cycles + Root-line generation +
verified scale templates today, even the partial corpus is enough
to drive a constrained-generation loop. Wiring the MIDI bridge
means SkyTNT output can be evaluated round-trip *now* — the only
piece still gated on Phase 8 is the actual `transformers` call to
the model (everything around it works). The Cowork plugin bundle
turns the whole stack into a one-click install for any agent
client that speaks the Cursor plugin format.

- **Phase 6 — OpenAI-compatible adapter + CLI.**
  - `music_rules.adapters.openai` auto-generates OpenAI function-calling
    schemas from each tool's Python type hints (no extra dependencies):
    - `get_tools_schema()` → ready to pass as `tools=...` to
      `openai.ChatCompletion.create(...)`, LiteLLM, Groq, Together,
      Ollama, vLLM, etc.
    - `get_tool_schema(name)` for single-tool lookup.
    - `dispatch(name, arguments)` invokes a tool via the same
      registry the MCP adapter uses, so MCP and OpenAI clients can
      never drift.
  - The schema generator handles primitives, `list[X]`, `dict[str, X]`,
    `tuple`, `Literal[...]`, `X | Y` unions, and `Optional[X]` —
    everything the current tool surface uses. Includes a
    PEP 563 / 649 fix (uses `typing.get_type_hints` so string-form
    annotations under `from __future__ import annotations` resolve
    correctly).
  - `music_rules.adapters.cli` is the **`music-rules` console script**,
    built with Typer:
    ```
    music-rules version
    music-rules rules list   [--system EIS|Fux] [--category C] [--kind K]
                             [--input-shape S] [--limit N] [--json]
    music-rules rules show   <rule_id> [--json]
    music-rules rules search <text>    [--limit N] [--json]
    music-rules evaluate     <piece.json> [--species N] [--strict]
                             [--ruleset Fux|EIS|both]
                             [--include id ...] [--exclude id ...] [--json]
    music-rules tools list                 [--json]
    music-rules tools schema [--name X]    [--json]
    music-rules mcp serve                  # FastMCP over stdio
    ```
    Exit codes follow Unix convention: `0` for success, `1` for hard
    rule violations, `2` for user errors (missing file, unknown rule).
- 49 new tests (`test_openai_adapter.py` + `test_cli.py`) covering
  schema completeness, JSON-Schema validity (validated against
  Draft 2020-12 via `jsonschema`), every CLI subcommand, exit-code
  semantics, and `dispatch` round-tripping. Suite total: **176 passing**.

### Why

These two adapters round out the "ship to any AI frontend in a day"
promise from `PROJECT.md`. The OpenAI schema generator means
`music_rules` works with every OpenAI-compatible API today (LiteLLM,
Groq, Together, Ollama, vLLM, …) without writing a separate adapter
per vendor — the schemas are generated mechanically from the same
function signatures the MCP server already exposes. The CLI gives
the human user (and any shell-driven workflow) the same surface
without spinning up a chat client. Both share the MCP adapter's
`call_tool` registry, so a rule added to the corpus tomorrow is
automatically callable from MCP, OpenAI, AND the CLI with zero
extra wiring.

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
