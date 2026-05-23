# music-rules MCP Server — Showcase Report

## 1. Rule Counts

| System | Rules |
|--------|-------|
| **EIS** (Equal Interval System, Spud Murphy / Ted Greene) | 119 |
| **Fux** (Fuxian species counterpoint) | 39 |
| **Total** | **158** |

### Selected Fux Rule: **P1_1_2v**

> **"No direct (similar) motion into a perfect consonance (2v, 1st-species variant)."**

In two-voice first-species counterpoint, if both voices move in the *same* direction into a perfect 5th or octave, the result sounds hollow and structurally weak — contrary or oblique motion is preferred when landing on a perfect consonance.

---

## 2. Jazz Turnaround Progression

8-bar turnaround in C major, extending a Cmaj7–Am7–Dm7–G7 loop with a iii–VI7alt–ii9–subV–I resolution:

```
Bar 1:  Cmaj7     (I)
Bar 2:  Am7       (vi)
Bar 3:  Dm7       (ii)
Bar 4:  G7        (V)
Bar 5:  Em7       (iii)
Bar 6:  A7alt     (VI7alt)
Bar 7:  Dm9       (ii9)
Bar 8a: Db13#11   (tritone sub of V — ♭II7)
Bar 8b: Cmaj9#11  (I with #11 colour)
```

All chord symbols verified against `data/chord_tables/chord_lexicon.json`.

**CSV**: `examples/showcase_progression.csv`

---

## 3. MIDI Render Stats

| Property | Value |
|----------|-------|
| **Voices** | 7 (block root-position voicing per chord) |
| **Total steps** | 64 (8 bars × 4 beats × 2 steps/beat) |
| **Steps per beat** | 2 |
| **Tempo** | 120 BPM (500,000 µs/beat) |
| **Meter** | 4/4 |
| **File** | `examples/showcase.mid` |
| **File size** | 531 bytes |

---

## 4. Voice-Leading Verdict

### Fux Species Counterpoint Evaluation — Grade: **F** (cost 6.55)

| Rule | Violations | Description |
|------|-----------|-------------|
| **H1_1** | 8 | Downbeat sonorities contain dissonant intervals (7ths, 2nds, tritones) — expected for jazz 7th chords against Fux rules |
| **M1_1_2v** | 1 | Bass leap of M6 (9 semitones) exceeds 1st-species m6 ceiling |
| **H2_1** | 1 | Opening interval C3→G4 is M7, not a perfect consonance |
| **H3_1** | 1 | Closing interval C3→F#4 is a tritone, not a perfect consonance |

This is *expected* — Fux 1st-species rules require only consonant intervals (thirds, sixths, perfects), whereas jazz harmony is built on 7th chords stacked in thirds.

### EIS Voice-Leading Evaluation

| Transition | Smoothness | Total Motion | Violations |
|-----------|-----------|-------------|------------|
| Cmaj7 → Am7 | 0.0 | 30 | **3× V-002** — all voices jump > P5 |
| Am7 → Dm7 | 0.0 | 28 | None (but 0 common tones) |
| Dm7 → G7 | 0.25 | 21 | None |
| G7 → Em7 | **0.536** | 13 | None *(best pair)* |
| Em7 → A7alt | — | — | Voice count mismatch (4→6) |
| Dm9 → Db13#11 | — | — | Voice count mismatch (5→7) |
| Db13#11 → Cmaj9#11 | — | — | Voice count mismatch (7→6) |

### 🚩 Single Biggest Issue

**Cmaj7 → Am7 in root-position block chords.** All four voices jump 8–9 semitones with zero common tones, violating EIS rule **V-002** ("Move remaining tones to the nearest tones in the new chord").

**Why it happens:** Root-position voicing puts Cmaj7 as C3–E3–G3–B3 and Am7 as A3–C4–E4–G4. Every tone in Am7 lies a 3rd or 4th above its Cmaj7 counterpart — no shared pitches, no half-step moves.

**How to fix:** Voice Am7 to share common tones with Cmaj7. For example:

```
Cmaj7:  C3  E3  G3  B3
Am7:    C3  E3  G3  A3     (hold C, E, G; move B→A, a 2-semitone step)
```

This gives V-001 (3 common tones) + V-002 (1 voice moves 2 semitones) — a compliant EIS voice lead.

---

## Summary

The `music-rules` MCP server provides **158 rules** across two systems (119 EIS + 39 Fux), a chord lexicon with hundreds of voicings, automated progression-to-MIDI rendering, and multi-system voice-leading evaluation. This showcase built a Cmaj9#11 jazz turnaround, rendered a 7-voice, 64-step, 531-byte MIDI, and diagnosed that root-position block chords between Cmaj7 and Am7 cause V-002 voice-leading violations — fixable by holding common tones in an inversion.
