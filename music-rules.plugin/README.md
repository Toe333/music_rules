# music-rules — Cursor / Cowork plugin

This plugin packages the [`music-rules`](https://github.com/tonybove/music-rules)
MCP server plus three skills that teach the agent how to use it.

## What you get

When this plugin is enabled, the agent can:

- **Inspect the rule corpus** — 158 rules from Spud Murphy's *Equal Interval
  System* (EIS) and Fux's *Gradus ad Parnassum*, filtered by system,
  category, kind (hard/soft/informational), or input shape.
- **Check fragments** — 9 Fuxian checkers for melodic intervals, motion
  pairs, vertical chords, openings/closings, downbeat dissonance, and
  weak-beat passing tones.
- **Evaluate full passages** — `evaluate_passage` walks every position in
  a piece, returns a graded report (A–F) with hard violations, soft
  costs, and a per-rule summary.
- **Generate EIS Root-lines** — walk through E1..E6 cycles with
  optional elision (`eis_pick_root_line`), browse all 18 EIS scales
  (`eis_list_scales`).
- **Build EIS chords and progressions** — `eis_build_chord` for any
  chord class (triads, 7ths, 9ths, polytonal stacks, 4th-chords),
  `eis_voice_lead` for smooth voice-leading between chords,
  `eis_check_voice_leading` to score an existing move, `eis_insert_nct`
  to add Passing Tones / Suspensions / Anticipations / etc., and
  `eis_check_ood` for outside-octave dissonance.
- **Round-trip MIDI with per-voice instruments** —
  `midi_to_rolls` / `rolls_to_midi` (now with a `programs` parameter
  for chip-tune / mixed orchestrations), wired to accept SkyTNT's
  `midi-model` output directly.
- **Generate constrained MIDI** — `skytnt_generate` (raw) and
  `skytnt_constrained_generate` (propose-then-check loop that filters
  candidates against `evaluate_passage`). Requires the optional
  `[skytnt]` extras; otherwise the tools return a clear
  `skytnt_unavailable` payload.

## Installation

### Prerequisite: install the `music-rules` Python package

```bash
pip install music-rules
# or:
pipx install music-rules
# or for development:
git clone https://github.com/tonybove/music-rules.git && cd music-rules && pip install -e .
```

This puts `music-rules-mcp` on your `$PATH`. The plugin's `mcp.json` calls
that command — no other configuration needed.

### Install the plugin

In Cursor / Cowork:

1. Settings → Plugins → Install from local
2. Pick this directory (`music-rules.plugin`)
3. Reload — the `plugin-music-rules-music-rules` MCP server should
   appear in the agent's tool list.

## Verify

Ask the agent:

> List the available music-rules tools.

You should see ~34 tools beginning with `list_rule_systems`,
`get_rules`, `check_motion_pair`, `evaluate_passage`,
`eis_pick_root_line`, `eis_build_chord`, `eis_voice_lead`,
`skytnt_constrained_generate`, etc.

Then try:

> Use music-rules to check whether the soprano line `[60, 67, 64, 65,
> 65, 69, 65, 64]` and the cantus firmus `[60, 62, 64, 65, 67, 69, 71,
> 72]` would pass first-species two-voice counterpoint.

The agent should call `evaluate_passage` and report any hard violations
(parallel fifths, etc.) plus an A–F grade.

## Skills

The plugin ships four skills that proactively guide the agent:

- **`music-rules-setup`** — first-time check that the MCP server is
  installed; provides install instructions if not.
- **`music-rules-corpus`** — pattern for browsing and filtering rules
  before authoring or evaluating music.
- **`music-rules-evaluate`** — pattern for assembling a `piece` payload
  from voice lists and calling `evaluate_passage` correctly.
- **`music-rules-compose`** — the headline "generate music" skill:
  five-step symbolic composition (Root-line → chord class → build →
  voice-lead → render+grade) plus the SkyTNT propose-then-check loop.
  Triggered by requests like "harmonise this melody with EIS",
  "write a 3-part Bach invention", or "orchestrate this for chip-tune".

## License

MIT (matches the upstream `music-rules` package).
