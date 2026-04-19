---
name: music-rules-compose
description: Compose constrained MIDI from a natural-language brief — "harmonise this melody with EIS roots in E5", "write a 3-part Bach invention in 1st species", "orchestrate this for chip-tune (square / square / triangle / noise)". Use this skill whenever the user asks you to GENERATE music (not just check it), or asks for an EIS / Fux-flavoured arrangement of an existing piece. Always finishes with `evaluate_passage` so the output is graded before you hand it back.
allowed-tools: mcp__plugin-music-rules-music-rules__eis_pick_root_line, mcp__plugin-music-rules-music-rules__eis_list_scales, mcp__plugin-music-rules-music-rules__eis_list_chord_classes, mcp__plugin-music-rules-music-rules__eis_build_chord, mcp__plugin-music-rules-music-rules__eis_voice_lead, mcp__plugin-music-rules-music-rules__eis_check_voice_leading, mcp__plugin-music-rules-music-rules__eis_insert_nct, mcp__plugin-music-rules-music-rules__eis_check_ood, mcp__plugin-music-rules-music-rules__skytnt_generate, mcp__plugin-music-rules-music-rules__skytnt_constrained_generate, mcp__plugin-music-rules-music-rules__midi_to_rolls, mcp__plugin-music-rules-music-rules__rolls_to_midi, mcp__plugin-music-rules-music-rules__evaluate_passage, mcp__plugin-music-rules-music-rules__get_rules
license: MIT
metadata:
  author: Tony Bove
  version: "0.1.0"
---

# Composing constrained MIDI with `music-rules`

Use this skill whenever the user asks you to **generate music**, not
just check it. The `music-rules` MCP server gives you two complementary
ways to do that:

1. **Symbolic composition** — you build the piece note-by-note out of
   `eis_build_chord`, `eis_voice_lead`, `eis_insert_nct`, then render
   to MIDI with `rolls_to_midi`. Deterministic, fully constrained, no
   model required. **Default to this whenever the user wants
   something "in the style of EIS / Fux" without specifying SkyTNT.**
2. **SkyTNT-driven composition** — you generate raw MIDI with
   `skytnt_constrained_generate` and let the propose-then-check loop
   keep the best candidate that passes `evaluate_passage`. Requires
   the optional `[skytnt]` extras to be installed; if they're not, the
   tool returns `{"status": "skytnt_unavailable"}` and you should fall
   back to symbolic composition.

Always finish with `evaluate_passage` so the output is graded before
you hand it back.

## The five-step recipe (symbolic)

For requests like *"harmonise this melody with EIS roots in E5"*,
*"write a 3-part Bach invention in 1st species"*, or *"orchestrate
this for chip-tune"*:

### Step 1 — pick a Root-line

```
eis_pick_root_line({"length": 8, "cycles": ["E5"], "start_root": "C"})
→ {"roots": ["C", "F", "Bb", "Eb", "Ab", "Db", "Gb", "B"], "cycles": ["E5"]}
```

The cycle id (`E1`..`E6`) controls the bass motion's interval class.
Use `E5` (perfect 4th, circle of 4ths) by default — it's the source
of every standard ii-V-I-style cadence. Use `E4` (major 3rd) for
brighter, more symmetric progressions.

### Step 2 — pick a chord class for each Root

Each Root becomes one chord. `eis_list_chord_classes` shows the menu
(`triad`, `triad-7`, `dom7`, `min7`, `dom7b9`, `min9`, `dom9`,
`dom13`, `4th-3p`, `polytonal`, …). For Bach-style invention:
`triad` + `triad-7`. For a jazz lead-sheet: `min7` for ii, `dom7` for
V, `triad-7` for I. For chip-tune: `triad` + occasional `dom7` keeps
the harmony tight enough for two square waves.

### Step 3 — build each chord

```
eis_build_chord({
  "root": "C", "chord_class": "triad-7",
  "voicing": "open", "base_octave": 4
})
→ {"midi": [55, 60, 64, 71], "pitch_classes": [0, 4, 7, 11], "chord_class": {...}}
```

Use `voicing="open"` (drop-2) for chamber / jazz textures and
`voicing="close"` for chorale / chip-tune.

### Step 4 — voice-lead between chords

For each adjacent pair, instead of stacking the next chord cold, ask
`eis_voice_lead` to re-voice it relative to the previous one:

```
eis_voice_lead({
  "prev_chord": [55, 60, 64, 71],
  "next_pcs":   [5, 9, 0, 4]      # F, A, C, E for F maj7
})
→ {"voiced": [...], "report": {"smoothness": 0.94, ...}}
```

This automatically holds common tones (V-001), moves remaining voices
to the nearest target tones (V-002), and flags any V-014 parallel
octaves before they ship. The `smoothness` field (0..1) is your
quality dial — re-roll the chord-class choice if it falls below ~0.7.

### Step 5 — render to MIDI and grade

```
rolls_to_midi({
  "voices": [[bass_per_beat], [tenor_per_beat], [alto_per_beat], [soprano_per_beat]],
  "programs": [80, 80, 87, 122]   // chip-tune: square/square/triangle/noise
})
→ {"midi_base64": "..."}
```

Then **always** run `evaluate_passage` on the assembled voices and
include the grade in your reply. If the grade is C or worse, attempt
ONE re-voicing pass before giving up and asking the user to relax a
constraint.

## The propose-then-check loop (SkyTNT-driven)

For *"generate something in this style"* requests, the
`skytnt_constrained_generate` tool wraps the whole loop:

```
skytnt_constrained_generate({
  "prompt_midi": "<base64 prompt>",
  "ruleset": "both",
  "max_hard_violations": 0,
  "max_total_cost": 5.0,
  "num_candidates_per_try": 4,
  "max_tries": 4
})
```

It generates `num_candidates_per_try × max_tries` candidates, runs
each through `evaluate_passage`, and returns the lowest-cost one that
satisfies your caps (or the cheapest ever seen if nothing qualifies).
Always show the user the `accepted` count and the returned `report`
so they know whether they got a "perfect" or "best available" result.

**If the call returns `{"status": "skytnt_unavailable"}`**, switch to
symbolic composition. Do not retry — the extras are missing and
nothing will change without `pip install music-rules[skytnt]`.

## Cookbook: common requests

* **"Harmonise this melody with EIS"** — Step 1 with `cycles=["E5"]`,
  Step 2 with `triad` for each Root, Steps 3–5. Add NCT decoration
  via `eis_insert_nct` between any two adjacent chords for stylistic
  flavour (use `"PT"` for stepwise lines, `"Sus"` for hymn-style
  hesitation).
* **"Bach 3-part invention in 1st species"** — Use Fux mode: build a
  cantus firmus melody, set `species=1`, supply two voices, run
  `evaluate_passage` after each candidate counterpoint line. Keep
  iterating until grade ≥ B.
* **"Chip-tune arrangement"** — Build 4 voices with restricted
  voicings (`voicing="close"`, `parts=3` for triads). Render with
  `programs=[80, 80, 87, 122]` (square / square / triangle / noise)
  and pass `voice_ranges="satb"` to `evaluate_passage` to enforce
  realistic NES register limits.
* **"Re-orchestrate this for piano + strings"** — Decode user input
  with `midi_to_rolls`, re-voice each chord with `eis_voice_lead` to
  pull it into the new instrument's range, then `rolls_to_midi` with
  `programs=[0, 48, 48, 48]` (piano + 3× ensemble strings).

## Discoverability never invents things

When the user asks for a chord type, scale, or NCT type you don't
recognise, **never invent the id**. Call the appropriate `_list_*`
tool (`eis_list_chord_classes`, `eis_list_scales`,
`eis_list_nct_types`) first and pick the closest match. The same
goes for rule ids: route through `get_rules` rather than guessing.
