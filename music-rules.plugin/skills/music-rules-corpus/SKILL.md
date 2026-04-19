---
name: music-rules-corpus
description: Browse and filter the music-rules rule corpus (EIS + Fux, 158 rules) before authoring music or evaluating a passage. Use this skill whenever the user asks about specific rule IDs, asks "what rule covers X", asks to enumerate rules by system / category / kind / input shape, or wants to know which checkers exist before running them.
allowed-tools: mcp__plugin-music-rules-music-rules__list_rule_systems, mcp__plugin-music-rules-music-rules__list_rule_categories, mcp__plugin-music-rules-music-rules__list_rule_kinds, mcp__plugin-music-rules-music-rules__list_input_shapes, mcp__plugin-music-rules-music-rules__get_rules, mcp__plugin-music-rules-music-rules__get_rule, mcp__plugin-music-rules-music-rules__explain_rule
license: MIT
metadata:
  author: Tony Bove
  version: "0.1.0"
---

# Browsing the music-rules corpus

The corpus splits into two systems:

- **`EIS`** — Spud Murphy's *Equal Interval System*, a polytonal /
  4th-chord harmonic language. Rule families: H-, V-, RS-, C-, S-,
  NCT-, OOD-, GEN-.
- **`Fux`** — *Gradus ad Parnassum*–style species counterpoint (1..5,
  2..4 voices). Rule families: M (melodic), P (parallels / motion), H
  (harmonic openings/closings/downbeats), G (general).

## Rule kinds

Always pay attention to `kind`:

- **`hard`** — must not occur. A single hit fails the passage and
  caps the grade at F.
- **`soft`** — costs `weight` points; many small hits are tolerable
  but they grade you down.
- **`informational`** — surfaced as guidance, never gates a grade.

## Input shapes (what each rule applies to)

`input_shape` tells you which checker tool consumes that rule. The
nine shapes used today are:

| Shape                  | Checker tool                  |
|------------------------|-------------------------------|
| `melodic-interval`     | `check_melodic_interval`      |
| `melodic-triple`       | `check_melodic_triple`        |
| `motion-pair`          | `check_motion_pair`           |
| `vertical-chord`       | `check_vertical_chord`        |
| `first-interval`       | `check_first_interval`        |
| `final-interval`       | `check_final_interval`        |
| `per-measure-downbeat` | `check_per_measure_downbeat`  |
| `weak-beat-interval`   | `check_weak_beat_interval`    |
| `dissonance-context`   | `check_dissonance_context`    |

## Recommended browsing flow

1. `list_rule_systems` → confirm `["EIS", "Fux"]`.
2. `list_rule_kinds` → see what tiers exist.
3. `list_input_shapes` → see what checkers are wired up.
4. `get_rules({"system": "Fux", "input_shape": "motion-pair"})` →
   narrow down before pulling individual rules.
5. `get_rule({"rule_id": "P1_1_2v"})` → fetch a single rule's full
   definition.
6. `explain_rule({"rule_id": "P1_1_2v"})` → get the human-readable
   summary plus a `checker_hint` field that names the exact tool to
   call. Always prefer `explain_rule` when you're about to write code
   against a rule.

## Anti-patterns

- **Don't invent rule IDs.** If you can't find a rule via `get_rules`
  filters, it does not exist. Tell the user.
- **Don't assume a rule applies universally.** Always check
  `applies_to.species` and `applies_to.voices` before reporting a
  violation — many rules are species-1 / 2-voice only.
- **Don't conflate hard and soft hits when summarising.** `evaluate_passage`
  reports them in separate arrays; preserve that distinction in your
  reply.
