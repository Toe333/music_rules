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

1. The rules in machine-readable form. ✅ 158 rules in
   [`rules_combined.json`](src/music_rules/data/rules_combined.json).
2. Pure-Python checkers that verify a passage against those rules,
   returning hard violations and soft costs. ✅ Phase 3.
3. A *thin* adapter for each AI frontend so adding the next vendor is a
   weekend, not a rewrite. ✅ Phases 5 & 6.
4. A bridge to an actual MIDI generator (SkyTNT's `midi-model`) that
   does rejection sampling against those checkers. ✅ Phase 7.

Each layer is independently useful — you can use the corpus and checkers
from any Python script with zero AI dependencies pulled in.

## Status

**v0.1.0 — Phase 1 of 7 complete.** Repo, corpus, and docs are in place;
package scaffold and checkers are next. See
[`CHANGELOG.md`](CHANGELOG.md) for what's done and
[`PROJECT.md`](PROJECT.md) for the build plan.

## Install

> Phase 2 will publish the package to PyPI. For now, install from source.

```bash
git clone https://github.com/<your-account>/music-rules.git
cd music-rules

# uv (recommended — fast, no surprises)
uv venv && source .venv/bin/activate
uv sync --all-extras

# or, plain pip
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Quickstart (preview — live in Phase 2)

```python
from music_rules import corpus

# Discover what's there
print(corpus.list_systems())              # ['EIS', 'Fux']
print(len(corpus.get_rules()))            # 158
print(len(corpus.get_rules(system="Fux"))) # 39

# Find a specific rule
h11 = corpus.get_rule("H1_1")
print(h11.rule)
# 'The harmonic intervals on the first note of each measure ...'
```

```python
# Evaluating a passage (live in Phase 4)
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
# CLI (live in Phase 6)
music-rules rules list --system Fux
music-rules rules show H1_1
music-rules evaluate examples/2v_1st_species.json --species 1 --strict
```

```jsonc
// MCP (live in Phase 5) — drop into ~/.cursor/mcp.json or Claude Desktop
{
  "mcpServers": {
    "music-rules": {
      "command": "uvx",
      "args": ["--from", "music-rules", "music-rules-mcp"]
    }
  }
}
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
