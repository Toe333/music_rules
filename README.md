# music-rules

> **An AI-agnostic music theory constraint system** for EIS (Spud Murphy's
> Equal Interval System) and Fuxian species counterpoint, with thin adapters
> for MCP (Claude / Cursor), OpenAI function-calling, FastAPI, and a CLI.
> Designed to constrain AI MIDI generation without locking you into any one
> AI vendor.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Why this exists

If you want an AI assistant (Claude, ChatGPT, a local Ollama model, anything)
to generate MIDI that *actually* respects two centuries of contrapuntal
tradition or Spud Murphy's Equal Interval System, you need:

1. **The rules in machine-readable form.** 158 rules in
   [`rules_combined.json`](src/music_rules/data/rules_combined.json).
2. **Pure-Python checkers** that verify a passage against those rules,
   returning hard violations and soft costs.
3. **Thin adapters** for each AI frontend so adding the next vendor is a
   weekend, not a rewrite (MCP, OpenAI function-calling, CLI today; FastAPI
   gated behind the `[api]` extra).
4. **A bridge to an actual MIDI generator** — SkyTNT's `midi-model` — that
   does rejection sampling against those checkers.

Each layer is independently useful — you can use the corpus and checkers
from any Python script with zero AI dependencies pulled in.

## Status

**Active, 320 tests passing.** The portable core (corpus, Fux + EIS checkers,
passage evaluator, MIDI round-trip), all three adapters (MCP / OpenAI / CLI),
and the SkyTNT generation bridge are live. See [`CHANGELOG.md`](CHANGELOG.md)
for the per-release breakdown and [`PROJECT.md`](PROJECT.md) for the design.

## Install

```bash
git clone https://github.com/toe333/music_rules.git
cd music_rules

# uv (recommended — fast, reproducible against the committed uv.lock)
uv venv && source .venv/bin/activate
uv sync --extra dev

# or plain pip
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Optional extras:

| Extra      | Pulls in                              | Use when…                                              |
|------------|---------------------------------------|--------------------------------------------------------|
| `[api]`    | `fastapi`, `uvicorn`                  | you want the (planned) HTTP route surface              |
| `[skytnt]` | `torch`, `transformers`, `huggingface_hub` | you want `skytnt_generate` / `skytnt_constrained_generate` |
| `[dev]`    | `pytest`, `ruff`, `mypy`, `jsonschema`| contributing or running CI locally                     |

## Quickstart

```python
from music_rules import corpus

print(corpus.list_systems())               # ['EIS', 'Fux']
print(len(corpus.get_rules()))             # 158
print(len(corpus.get_rules(system="Fux"))) # 39

h11 = corpus.get_rule("H1_1")
print(h11.rule)
# 'The harmonic intervals on the first note of each measure ...'
```

```python
from music_rules.core.evaluate import evaluate_passage

piece = {
    "voices": [[60, 62, 64, 65, 67, 65, 64, 62, 60],   # cantus firmus
               [64, 65, 67, 69, 71, 69, 67, 65, 64]],  # counterpoint
    "meter": "4/4",
    "key": "C",
    "species": 1,
    "cantus_firmus_voice": 0,
}
report = evaluate_passage(piece, ruleset="Fux", strict=False)
print(report["grade"], report["total_cost"])
print(report["hard_violations"])
```

```bash
music-rules rules list --system Fux
music-rules rules show H1_1
music-rules evaluate path/to/piece.json --species 1 --strict
music-rules progression render-csv data/chord_tables/progression_template.csv \
  data/chord_tables/chord_lexicon.json examples/from_table.mid
music-rules progression render-voiced-csv examples/eis_e3_harmonized.csv \
  examples/eis_e3_harmonized_cli.mid
music-rules progression render-voiced-batch "examples/eis_*_harmonized.csv" \
  --out-dir examples
music-rules progression render-voiced-batch "examples/eis_*_harmonized.csv" \
  --out-dir examples --write-wav --soundfont-path /path/to/GeneralUser.sf2
# soundfont is optional when fluidsynth is installed; a default is auto-picked if found
music-rules progression find-soundfonts --json
music-rules progression audit-voiced-csv examples/eis_e3_harmonized.csv \
  --ruleset EIS --min-grade B --max-total-cost 10 \
  --fail-on-rule O-004 --max-rule-total-cost O-001=5 \
  --warn-on-rule O-002 --warn-rule-total-cost O-004=2 \
  --report-out examples/eis_e3_audit.json
music-rules progression audit-voiced-batch "examples/eis_*_harmonized.csv" \
  --ruleset EIS --min-grade B --summary-out examples/eis_audit_summary.json
music-rules progression audit-voiced-batch "examples/eis_*_harmonized.csv" \
  --ruleset EIS --json
music-rules progression pipeline-voiced-batch "examples/eis_*_harmonized.csv" \
  --out-dir examples --write-wav --ruleset EIS --min-grade B \
  --fail-on-rule O-002 \
  --summary-out examples/eis_pipeline_summary.json
music-rules progression summary-markdown examples/eis_pipeline_summary.json \
  --out-path examples/eis_pipeline_summary.md
music-rules progression summary-diff examples/eis_pipeline_summary_prev.json \
  examples/eis_pipeline_summary.json --out-path examples/eis_pipeline_diff.md
music-rules progression summary-diff examples/eis_pipeline_summary_prev.json \
  examples/eis_pipeline_summary.json --only-regressions
music-rules progression summary-history "examples/eis_pipeline_summary*.json" \
  --sort-by name --out-path examples/eis_pipeline_history.md
music-rules progression summary-history "examples/eis_pipeline_summary*.json" \
  --fail-on-latest-regression --max-total-regressions 0 --max-latest-regressions 0
music-rules progression summary-history "examples/eis_pipeline_summary*.json" \
  --latest-only --top-n-latest 5
music-rules progression summary-markdown examples/eis_pipeline_summary.json \
  --failures-only --sort-by cost --descending --top-n 5
music-rules progression apply-gates examples/eis_pipeline_summary.json \
  --min-grade B --fail-on-rule O-002 --out-path examples/eis_pipeline_regated.json
music-rules progression policy-template --out-path examples/gate_policy.json
music-rules progression audit-voiced-batch "examples/eis_*_harmonized.csv" \
  --ruleset EIS --policy-path examples/gate_policy.json --summary-out examples/eis_audit_summary.json
```

```jsonc
// MCP — drop into ~/.cursor/mcp.json or Claude Desktop's config
{
  "mcpServers": {
    "music-rules": {
      "command": "uvx",
      "args": ["--from", "music-rules", "music-rules-mcp"]
    }
  }
}
```

For OpenAI function-calling workflows, the adapter exposes chord-table
bridge tools (`chord_progression_to_rolls`, `chord_progression_to_midi`,
`chord_progression_csv_to_midi`). See
`examples/opencode_chord_progression_example.json` and the generated tables
under `data/chord_tables/`.

### Evaluate report triage

If you already have an `evaluate_passage` JSON report and want a compact
"what should I fix first?" summary:

```bash
music-rules evaluate-explain path/to/report.json
music-rules evaluate-explain path/to/report.json --json
```

## How it's organized

| Layer | Where | What it does |
|---|---|---|
| **Rule corpus** | `src/music_rules/data/rules_combined.json` | Single source of truth. 158 rules with `id`, `kind`, `input_shape`, `species`, etc. |
| **Core** | `src/music_rules/core/` | Pure Python. Loads the corpus, checks fragments, evaluates passages. **No AI imports.** |
| **MIDI bridge** | `src/music_rules/core/midi/skytnt_bridge.py` | The one core file allowed to touch `transformers` / SkyTNT. |
| **Adapters** | `src/music_rules/adapters/` | Thin shims (~50-100 lines each) for MCP, OpenAI, FastAPI, CLI. |

See [`PROJECT.md`](PROJECT.md) for the design philosophy and full folder
breakdown, and [`docs/MCP_TOOL_SURFACE_SPEC.md`](docs/MCP_TOOL_SURFACE_SPEC.md)
for the complete tool surface.

## Acknowledgments

- **Ted Greene** (1946-2005) — for his decades of meticulous EIS lesson
  notes and for keeping Spud Murphy's system alive. The distilled rules in
  this repo trace to his teaching pages.
- **Tom Lai** & **UCLouvain** — for [FuxCP5](https://github.com/TomLaiUCL/FuxCP5),
  the C++/Lisp constraint formalization of species counterpoint that this
  Python re-implementation is guided by. See
  [`data/fux/FuxCP5_attribution.md`](data/fux/FuxCP5_attribution.md).
- **SkyTNT** — for the [`midi-model`](https://huggingface.co/skytnt/midi-model)
  HuggingFace transformer that this project will constrain in Phase 7.

## License

- **Code** — MIT, see [`LICENSE`](LICENSE).
- **Data and rule corpora** — see [`data/README.md`](data/README.md) for the
  full breakdown (mostly original; Ted Greene PDF text is dev-only and not
  redistributed; future Stack Exchange contributions are CC BY-SA).
