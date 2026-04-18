# MCP Tool-Surface Spec — EIS + Fux → SkyTNT MIDI constraining

Draft v0.1 · 2026-04-18

This document specifies the MCP tools Claude should be able to call to (a) pick/validate musical structure per the EIS and Fux rule corpora, and (b) constrain or post-filter MIDI output from the SkyTNT `midi-model` transformer. It is intentionally ahead of implementation: nail the shape first, build to it second.

The rule corpus that backs every checker is `rules_combined.json` (158 rules: 119 EIS, 39 Fux). Every checker tool reads exactly one `input_shape` from that JSON, so the tool registry is mechanically derivable from the corpus.

---

## 1. Design goals

1. **Rule-grounded**: every call is traceable to a specific rule ID (`V-014`, `H5_1cf`, etc.) — no free-floating "music theory says…".
2. **Hard/soft separation**: each check returns either a violation (hard) or a cost (soft). Generators pick a temperature for the soft weight.
3. **Composable**: checkers operate on tiny fragments (an interval pair, a single measure). An `evaluate_passage` tool loops over a piece and aggregates.
4. **Style-agnostic**: EIS and Fux rules can be enabled/disabled per-task via a `ruleset` argument. The same tool surface works whether the user wants strict 1st-species counterpoint or free EIS horizontal composition.
5. **SkyTNT round-trip**: a generator tool wraps SkyTNT so constraints can be applied via (a) prompt conditioning, (b) rejection sampling, or (c) beam-filter.

---

## 2. Five tool groups

### Group A — Corpus introspection

No audio/MIDI I/O. These just query `rules_combined.json` so an agent can discover what it can enforce.

```
list_rule_systems()
  → ["EIS", "Fux"]

list_rule_categories(system: "EIS" | "Fux" | "all" = "all")
  → ["principle", "root-progression", "voice-leading", "range", "ood",
     "nct", "general", "harmonic", "melodic", "motion", "rhythm", ...]

get_rules(system=None, category=None, species=None, voices=None,
          kind=None, tier=None)
  → [ { id, rule, scope, exceptions, input_shape, kind, source, ... } ]
  # Filters combine with AND. Returns at most `limit` (default 200) rules.

get_rule(rule_id: str)
  → full rule object + resolved `input_shape` signature.

explain_rule(rule_id: str)
  → short natural-language paraphrase + a 1-bar worked example.
```

### Group B — EIS helpers (content generators, not checkers)

EIS is procedural: you *choose* a Root line, scale, chord stack, VL. These tools generate candidates and never emit violations.

```
eis_pick_root_line(length: int, cycles: ["E1".."E6"], start_root: "C",
                   allow_elision: bool = True)
  → [ "C", "G", "D", "A", ... ]   # sequence of Root tones

eis_list_scales()
  → [ { id: "EIS-18-07", name: "Lydian Dominant", degrees: [0,2,4,6,7,9,10] }, ... ]

eis_build_chord(root: "C", scale_id: "EIS-18-03",
                chord_class: "triad-open" | "triad-close" | "nat7"
                           | "9" | "11" | "13" | "quartal" | "quintal"
                           | "secondal" | "polytonal",
                parts: 2 | 3 | 4 | 5)
  → { pitches: [48, 55, 64, 71], voicing: "...description..." }

eis_voice_lead(prev_chord: [...], next_chord: [...], mode: "strict" | "relaxed")
  → { pitches: [...], applied_rules: ["V-001", "V-004"], cost: 0.0 }

eis_insert_nct(voice: [notes...], nct_type: "PT"|"CA"|"RT"|"CT"|"Sus"|"Ant",
               beat: float)
  → voice with NCT inserted, per EIS NCT rules.

eis_check_ood(chord: [...], outside_octave_pairs: [...])
  → violations[] referencing OOD rules.
```

### Group C — Fux checkers

One tool per `input_shape`. The tool accepts the fragment plus a `ruleset` filter, returns a list of `(rule_id, cost_or_violation)` tuples.

```
check_melodic_interval(prev_midi, curr_midi,
                       species: 1..5 | "all", voices: 2|3|4 = 2,
                       strict: bool = True)

check_melodic_triple(n1, n2, n3, species, voices, strict=True)

check_motion_pair(prev_pair: {cf, cp}, curr_pair: {cf, cp},
                  species, voices, strict=True)

check_vertical_chord(chord: [...], key: "C", position: int,
                     total_length: int, species, voices, strict=True)

check_dissonance_context(prev, diss, next, species, voices, strict=True)

check_voice_pair(voice_a: [...], voice_b: [...], species, strict=True)

check_cantus_firmus_fit(cf: [...], cp: [...], species, strict=True)

check_five_note_window(window: [5 notes], species, strict=True)

check_first_interval(chord, species, voices)
check_final_interval(chord, species, voices)
check_penultimate(chord, position, key, species, voices)
```

Each returns:
```json
{
  "ok": false,
  "violations": [
    {"rule_id": "H1_1", "cost": null, "msg": "parallel 8ves between bass & tenor"}
  ],
  "soft_costs": [
    {"rule_id": "G4", "cost": 1.0, "msg": "borrowed note: F# outside C major"}
  ]
}
```

### Group D — Passage evaluator (orchestrates C across a full piece)

```
evaluate_passage(piece: { voices: [[midi...], ...], meter: "4/4",
                          key: "C", species: 1..5 | "all",
                          cantus_firmus_voice: 0 },
                 ruleset: "Fux" | "EIS" | "both" = "both",
                 strict: bool = False,
                 include: [rule_ids] | None = None,
                 exclude: [rule_ids] | None = None)
  → {
      total_cost: 7.25,
      hard_violations: [ {rule_id, position, voices_involved, msg}, ... ],
      soft_violations: [ {rule_id, position, cost, msg}, ... ],
      per_rule_summary: { "H1_1": { count: 2, total_cost: null }, ... },
      grade: "B"   # rubric derived from strict-mode violation count
    }
```

This is the primary tool an agent will call after generation. It folds over the piece and dispatches each rule to its `input_shape`-matched checker.

### Group E — SkyTNT bridge

```
skytnt_generate(prompt_midi: base64 | null,
                conditioning: { key, meter, tempo, length_bars, style_tags },
                num_candidates: int = 4,
                temperature: float = 1.0,
                seed: int | null = null)
  → { candidates: [ { midi_base64, token_count, ... } ] }

skytnt_constrained_generate(
    prompt_midi, conditioning,
    ruleset: "Fux" | "EIS" | "both" = "both",
    strict: bool = False,
    max_hard_violations: int = 0,
    max_total_cost: float = 10.0,
    num_candidates_per_try: int = 8,
    max_tries: int = 8,
    seed: int | null = null)
  → {
      best: { midi_base64, report: <evaluate_passage output> },
      tried: int,
      accepted: int
    }
# Strategy: repeatedly call skytnt_generate, pipe each candidate through
# evaluate_passage, return the lowest-cost candidate satisfying the caps.

midi_to_rolls(midi_base64) → { voices: [[midi...]], meter, key_guess, ... }
rolls_to_midi(voices, meter, tempo) → midi_base64
```

---

## 3. How a typical call chain looks

User: "Write me a 2-voice 1st-species counterpoint in C major, 16 bars, strict Fux."

1. `eis_pick_root_line(...)` — skipped (we're in Fux mode).
2. `skytnt_constrained_generate(prompt_midi=<cantus firmus>, ruleset="Fux", strict=true, max_hard_violations=0)`.
3. Inside that tool: loop → `skytnt_generate` → `evaluate_passage(..., species=1, voices=2)` → keep best.
4. Return MIDI + `evaluate_passage` report.

User: "Write me an 8-bar EIS passage starting on C, moving in descending E5, close-position triads, then give me a Fux-style counterpoint above it."

1. `eis_pick_root_line(length=8, cycles=["E5"], start_root="C")`.
2. For each root: `eis_build_chord(..., chord_class="triad-close", parts=3)`.
3. `eis_voice_lead(...)` across adjacent chords.
4. `rolls_to_midi(...)` — write the EIS bass+treble as one MIDI.
5. Feed it into `skytnt_constrained_generate(prompt_midi=<that>, ruleset="Fux", strict=false)` to generate a counterpoint voice.
6. Merge, `evaluate_passage(..., ruleset="both")` on the whole.

---

## 4. Where each rule lives in the tool surface

| Rule group | Count | Handled by |
|-------------|-------|------------|
| EIS principles / terminology | ~35 | Group A (introspection only) |
| EIS root-progression | ~12 | Group B `eis_pick_root_line` |
| EIS scales | ~4  | Group B `eis_list_scales` |
| EIS chord-class / voicing | ~18 | Group B `eis_build_chord` |
| EIS voice-leading | ~15 | Group B `eis_voice_lead` + check at Group D |
| EIS NCT | ~8  | Group B `eis_insert_nct` |
| EIS range / OOD | ~9  | Group C-style checker + Group D |
| EIS bass / six-four / resolutions | ~18 | Group B generators + Group D |
| Fux general (G*)  | 5 | Group C `check_melodic_*`, `check_vertical_*` |
| Fux harmonic (H*) | 11 | Group C `check_vertical_chord`, `check_voice_pair` |
| Fux melodic (M*)  | 5 | Group C `check_melodic_interval`, `_triple` |
| Fux motion (P*)  | 15 | Group C `check_motion_pair` |
| Fux rhythm (R*)  | 3 | Group C `check_five_note_window`, rhythmic-diversity |

Total rules routed: 158. Hard-coded checkers needed: ~12 checker tools (one per `input_shape`) + ~6 EIS helpers + 4 SkyTNT-bridge tools + 5 corpus-introspection tools = **~27 tools in the MCP server**.

---

## 5. Server layout (proposed)

```
eis_fux_mcp/
├── pyproject.toml
├── rules_combined.json           # shipped as data
├── src/eis_fux_mcp/
│   ├── __init__.py
│   ├── server.py                 # MCP server entrypoint (FastMCP)
│   ├── corpus.py                 # loads rules_combined.json, filtering helpers
│   ├── eis/
│   │   ├── roots.py              # E1..E6 cycles, elision, pick_root_line
│   │   ├── scales.py             # 18 EIS scales
│   │   ├── chords.py             # triads → polytonal stacks
│   │   ├── voice_leading.py      # VL rules V-001..V-015
│   │   └── nct.py                # PT/CA/RT/CT/Sus/Ant
│   ├── fux/
│   │   ├── melodic.py            # G6, M1..M3, ...
│   │   ├── harmonic.py           # H1..H8
│   │   ├── motion.py             # P1..P7
│   │   ├── rhythm.py             # R1..R9
│   │   └── species.py            # species-level orchestration
│   ├── evaluate.py               # evaluate_passage
│   └── skytnt_bridge.py          # generate + constrained_generate
└── tests/
    ├── fixtures/                 # canonical Fux examples from Gradus ad Parnassum
    └── test_*.py
```

A single `SKILL.md` in the Cowork skills folder then reads roughly:

> When the user asks for MIDI generation with counterpoint or EIS rules, call `list_rule_systems` first, then `get_rules` to discover available constraints, then `skytnt_constrained_generate` or the manual chain above.

---

## 6. Open decisions (to confirm before implementation)

1. **Hard vs soft default**: ship with `strict=False` everywhere so generation rarely fails outright, and let the user flip the switch. OK?
2. **SkyTNT hosting**: call the HuggingFace `midi-model` via the `transformers` library (CPU/GPU on the user's machine) or via the Inference API? Inference API is simpler; local is cheaper for long runs.
3. **music21 dependency**: pull in music21 for MIDI parsing / pitch-to-note conversion, or keep the server dependency-light with just `mido`?
4. **Voice-count caps**: FuxCP5 handles 2–4 voices; EIS handles 2–5+. Clamp at 5 to bound complexity?
5. **Serialized / polytonal EIS tools**: EIS books 10–12 cover tropes / polytonality. Tag these as advanced and stub for v2?

Once those are settled I can stand up the server skeleton, write the EIS helper functions, translate the ~12 Fux checkers (mostly direct ports of FuxCP5's `constraints.cpp` logic), and wire `evaluate_passage` to route every rule to its checker via `input_shape`.
