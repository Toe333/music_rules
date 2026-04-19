---
name: music-rules-evaluate
description: Evaluate a complete musical passage (any number of voices, species 1..5) against the music-rules corpus and report the grade. Use this skill whenever the user asks to "check" / "evaluate" / "grade" a piece, paste-asks you to find errors in a counterpoint exercise, requests an A–F report, or feeds you SkyTNT output to validate. Also use it before returning generated MIDI to the user — never ship unverified output.
allowed-tools: mcp__plugin-music-rules-music-rules__evaluate_passage, mcp__plugin-music-rules-music-rules__midi_to_rolls, mcp__plugin-music-rules-music-rules__rolls_to_midi, mcp__plugin-music-rules-music-rules__explain_rule
license: MIT
metadata:
  author: Tony Bove
  version: "0.1.0"
---

# Evaluating a passage with `evaluate_passage`

The single tool you almost always reach for is
`evaluate_passage`. It walks every position in the piece, dispatches
to all nine Phase-3 checkers, aggregates hard violations + soft costs,
and assigns an A–F grade.

## Required `piece` shape

```json
{
  "voices": [
    [60, 62, 64, 65, 67, 69, 71, 72],
    [48, 50, 52, 53, 55, 57, 59, 60]
  ],
  "meter": "4/4",
  "key": "C",
  "species": 1,
  "cantus_firmus_voice": 0
}
```

Field rules:

- `voices` — list-of-lists of MIDI numbers. **All voices must be the
  same length.** Use `-1` for a rest if the input has them.
- `meter` — string like `"4/4"` or `"3/4"`.
- `key` — note name (`"C"`, `"Bb"`, `"F#"`).
- `species` — integer 1..5.
- `cantus_firmus_voice` — index into `voices` of the CF (the part the
  CP is written *against*). Required for parallel-motion checks.

## Optional knobs

- `include`: list of rule IDs to consider (everything else ignored).
- `exclude`: list of rule IDs to skip.

Useful when the user is doing a focused exercise:
"only check P1_*, P2_*, and the opening / closing rules".

## Output shape (don't abbreviate when reporting back)

```json
{
  "total_cost": 0.6,
  "hard_violations": [
    {"rule_id": "P1_1_2v", "position": 1, "voices": [0, 1], "detail": "..."}
  ],
  "soft_violations": [
    {"rule_id": "M3_1", "position": 4, "voices": [1], "weight": 0.2, "detail": "..."}
  ],
  "per_rule_summary": [
    {"rule_id": "P1_1_2v", "kind": "hard", "hits": 1, "total_cost": null},
    {"rule_id": "M3_1",    "kind": "soft", "hits": 3, "total_cost": 0.6}
  ],
  "grade": "F"
}
```

Grading rubric (already applied for you):

| Hard hits | Total soft cost | Grade |
|----------:|----------------:|:-----:|
|         0 | ≤ 0.5           | A     |
|         0 | ≤ 1.5           | B     |
|         0 | ≤ 3.0           | C     |
|         0 | > 3.0           | D     |
|       ≥ 1 | (any)           | F     |

## Reporting pattern

When you summarise the report to the user:

1. **Lead with the grade.** Then the headline counts: "1 hard, 3 soft,
   total cost 0.6".
2. **Group violations by rule_id**, not by position. The
   `per_rule_summary` already does this.
3. **For each unique rule_id, call `explain_rule`** to get the
   human-readable summary, and quote the `checker_hint` so the user
   knows which tool to re-invoke if they want to dig in.
4. **Cite positions and voice indices verbatim** — never round or
   re-number them.

## Working with SkyTNT MIDI output

When the user pastes a MIDI blob (base64) or filesystem path:

1. `midi_to_rolls({"midi_base64": "..."})` → get `voices`, `meter`,
   `key_guess`, `tempo`.
2. Build a `piece` payload using those fields. If `key_guess` is
   `null`, ask the user for the key (or default to `"C"` and say so
   explicitly).
3. Call `evaluate_passage`.
4. If the user wants to round-trip the output, call
   `rolls_to_midi({"voices": [...], "meter": "...", "tempo": ...})` —
   it returns a fresh base64 blob.

## Anti-patterns

- **Don't try to evaluate without all voices the same length.** Pad
  the shorter voice with `-1` rests *and* tell the user you did so.
- **Don't silently change `species`.** If the user gives an ambiguous
  passage, ask before assuming.
- **Don't post-process the report.** The grading rubric is part of the
  contract; downstream tools and the user both rely on consistent
  outputs.
