# PROJECT.md — orient here first

> **For future AI sessions and human contributors alike.** Read this end-to-end
> before touching code. It takes ~2 minutes and saves hours of wrong turns.

---

## What this project is

`music-rules` is a **portable, AI-agnostic Python package** that encodes two
formal music-theory systems as machine-readable rules and provides pure-Python
checkers and generators on top:

1. **EIS** — Spud Murphy's *Equal Interval System*, as taught by Ted Greene
   in his 1977-78 lesson notes (plus public web supplements). Procedural and
   generative: choose Root lines, scales, chord stacks, voice-leading.
2. **Fux** — Fuxian species counterpoint, formalized by FuxCP5 (UCLouvain
   MSc thesis, Tom Lai). Constraint-based: every passage is a sequence of
   note-pairs / chord-windows that must satisfy hard rules and minimize soft
   costs.

The package is the substrate for **constraining AI MIDI generation**, with
SkyTNT's `midi-model` HuggingFace transformer as the first integration target.

## Design principle: portable core, thin adapters

```
                                 ┌─────────────────────┐
                                 │  rules_combined.json │  ← single source of truth
                                 └──────────┬──────────┘
                                            │
                       ┌────────────────────┴────────────────────┐
                       │   src/music_rules/core/                 │
                       │   PURE PYTHON. No AI-framework imports. │
                       │     corpus  ·  eis  ·  fux  ·  evaluate │
                       │     midi (mido + skytnt_bridge)         │
                       └────────────────────┬────────────────────┘
                                            │
       ┌────────────────┬───────────────────┼────────────────┬────────────────┐
       │                │                   │                │                │
   adapters/mcp     adapters/openai    adapters/api     adapters/cli      (future)
   FastMCP shim     OpenAI fn-calls    FastAPI routes   typer CLI       LangChain,
                                                                          Ollama, etc.
```

Every AI frontend that emerges in the next few years should be a one-day
~50-100-line shim over the same core, **never a rewrite**.

## Folder layout

```
music_rules/
├── PROJECT.md                  ← you are here
├── README.md                   ← user-facing install + quickstart
├── CHANGELOG.md
├── LICENSE                     ← MIT for code (data terms in data/README.md)
├── pyproject.toml
├── uv.lock                     ← committed for reproducible installs
├── .gitignore
│
├── data/                       ← reference materials, NOT installed in wheel
│   ├── README.md               ← provenance, licensing, what's where
│   ├── chord_tables/           ← exported chord lexicon + MIDI mappings
│   ├── eis/
│   │   ├── EIS_MASTER_RULES.md ← human-readable rulebook
│   │   └── extracted/          ← raw PDF text (dev only, not shipped)
│   ├── fux/
│   │   ├── Counterpoint_rules_table.csv
│   │   └── FuxCP5_attribution.md
│   └── tables/                 ← xlsx exports for spreadsheet users
│
├── src/music_rules/
│   ├── __init__.py             ← __version__
│   ├── data/
│   │   ├── rules_combined.json ← canonical corpus, shipped in wheel
│   │   └── rules.schema.json   ← JSON-Schema validator
│   │
│   ├── core/                   ← PURE PYTHON, no AI imports
│   │   ├── corpus.py           ← load JSON, Pydantic Rule, filtering
│   │   ├── pitch.py            ← MIDI<->name, intervals, key membership
│   │   ├── evaluate.py         ← evaluate_passage() orchestrator
│   │   ├── report.py           ← CheckReport TypedDict + helpers
│   │   ├── eis/
│   │   │   ├── roots.py        ← E1..E6 cycles, pick_root_line()
│   │   │   ├── scales.py       ← the 18 EIS scales
│   │   │   ├── chords.py       ← triads/7/9/11/13/quartal/upper-structure
│   │   │   ├── voice_leading.py ← V-001..V-015
│   │   │   ├── nct.py          ← PT/CA/RT/CT/Sus/Ant
│   │   │   └── ood.py          ← outside-octave-dissonance checker
│   │   ├── fux/
│   │   │   ├── melodic.py      ← G6, G7, M1, M2, M3
│   │   │   ├── harmonic.py     ← H1..H8
│   │   │   ├── motion.py       ← P1..P7 (delegates to music21)
│   │   │   ├── dissonance.py   ← passing-tone / suspension etc.
│   │   │   ├── _common.py      ← shared rule-applicability helpers
│   │   │   └── _m21.py         ← music21 thin-wrapper (typed)
│   │   └── midi/
│   │       └── skytnt_bridge.py ← mido + HuggingFace midi-model wrapper
│   │                              (the ONLY file in core allowed to
│   │                              import `transformers`/`torch`,
│   │                              lazy + behind the [skytnt] extra)
│   │
│   └── adapters/               ← thin shims over core
│       ├── mcp.py              ← FastMCP server (34 tools)
│       ├── openai.py           ← OpenAI fn-call schema generator
│       └── cli.py              ← typer-based `music-rules` console script
│
├── tests/                      ← 320 tests, all passing
│   ├── fixtures/
│   └── test_*.py
├── docs/
│   └── MCP_TOOL_SURFACE_SPEC.md ← THE spec; read before adding tools
├── examples/                   ← worked examples (MIDI + CSV + scripts)
└── music-rules.plugin/         ← Cowork/Cursor plugin bundle (mcp.json + skills)
```

## How to run things

```bash
# install (uv recommended; pip works too)
uv venv && source .venv/bin/activate
uv sync --extra dev

# run the test suite
uv run pytest

# quick sanity check on the corpus
uv run python -c "from music_rules import corpus; print(len(corpus.get_rules()))"

# CLI
uv run music-rules rules list --system Fux
uv run music-rules rules show H1_1
uv run music-rules evaluate path/to/piece.json --species 1 --strict

# CI gauntlet (matches .github/workflows/ci.yml)
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src/music_rules/core
uv run pytest
```

## How to add a new rule

1. Open `src/music_rules/data/rules_combined.json`.
2. Append an object to `"rules"`. Required fields: `id`, `system`,
   `category`, `rule`, `scope`, `exceptions`, `tier`, `source`, `kind`,
   `input_shape`, `species`, `voices`. Pick `input_shape` from the
   `"input_shapes"` dict at the top of the same file — **do not invent a
   new shape** unless you also add a new checker function.
3. Run `pytest tests/test_corpus.py` — the JSON-Schema validator catches
   structural mistakes immediately.
4. If your rule's `input_shape` already has a checker, you're done — the
   evaluator will pick it up automatically. If it's a brand-new shape,
   write the checker in `src/music_rules/core/{eis,fux}/<topic>.py` and
   register it in the dispatch table in `core/evaluate.py`.

## Non-negotiable rules for code that lives here

These are listed in priority order. Future-you will thank present-you for
holding the line.

1. **No vendor lock-in in `core/`.** No imports of `mcp`, `openai`,
   `anthropic`, `langchain`, `litellm`, or any other AI-framework SDK
   under `src/music_rules/core/`. Only `core/midi/skytnt_bridge.py` may
   import `transformers` or `huggingface_hub`. Adapters are the *only*
   place AI-frontend SDKs are allowed.
2. **Data is canonical.** Every enforcement function reads its rule
   metadata from `rules_combined.json` via `corpus.py`. **Rule IDs are
   never hardcoded as string literals inside business logic** — look them
   up by ID. If you find yourself typing `"H1_1"` inside a checker
   function, you've already drifted.
3. **Type-hint every public function** with Pydantic models or `typing`
   primitives. The OpenAI schema generator (`adapters/openai.py`)
   auto-derives JSON Schemas from these — untyped functions silently
   break that adapter.
4. **Tests are the safety net.** Every checker has at least one passing
   fixture and one failing fixture, drawn from a documented source
   (typically Fux's *Gradus ad Parnassum* for counterpoint and Ted
   Greene's lesson examples for EIS). CI runs them on every push.
5. **Copyright hygiene.** Ted Greene's raw PDF text stays in
   `data/eis/extracted/` and is excluded from the published wheel via
   `pyproject.toml`. Any quotes in rule descriptions are <15 words and
   attributed in the `source` field.
6. **Reversibility.** Every commit message explains the *why*, not just
   the *what*, so any decision can be rewound with confidence.

## When you (or an AI session) get stuck

Ask Tony (in chat). Don't invent musical conventions.

- **Ambiguous Fux rule?** Quote the relevant FuxCP5 source
  (`FuxCP/c++/src/constraints.cpp`, line range), state the ambiguity
  in one sentence, and ask. Don't guess — wrong-baked counterpoint
  rules cascade into wrong-baked passages downstream.
- **Ambiguous EIS rule?** Quote the relevant paragraph from
  `data/eis/EIS_MASTER_RULES.md` (with section number), state the
  ambiguity, and ask.
- **A rule you want doesn't have a clear `input_shape` match?** Write up
  what shape you'd add and why, and ask before extending the
  `"input_shapes"` dict.

Tony would rather answer three small questions than un-bake three wrong
assumptions later.

## Build phases (where we are)

- [x] **Phase 0** — Read spec + JSON, confirm understanding.
- [x] **Phase 1** — Repo setup, file moves, docs, initial commit.
- [x] **Phase 2** — Package scaffold (pyproject, corpus loader, JSON
      schema, baseline tests).
- [x] **Phase 3** — Fux checkers + fixtures (melodic, harmonic, motion,
      dissonance; delegates to `music21` where the heavy lifting is).
- [x] **Phase 4** — `evaluate_passage` orchestrator with per-rule
      dispatch and `CheckReport` aggregation.
- [x] **Phase 5** — MCP adapter (`adapters/mcp.py` via `fastmcp`).
- [x] **Phase 6** — OpenAI-compatible adapter + typer CLI
      (`adapters/openai.py`, `adapters/cli.py`).
- [x] **Phase 7** — EIS roots/scales/chords/voice-leading/NCT, SkyTNT
      bridge with rejection-sampling against `evaluate_passage`,
      Cursor/Cowork plugin bundle.
- [ ] **Phase 8** — Logit-mask-based hard constraints in the SkyTNT
      bridge (current loop is rejection-sampling only); FastAPI route
      surface (`adapters/api.py`, gated behind the `[api]` extra).

See `docs/MCP_TOOL_SURFACE_SPEC.md` for the complete tool surface this
project is building toward.
