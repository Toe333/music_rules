"""Bass-line renderer.

Hard rules enforced (style-driven):

* First note of each bar is the chord root in the configured bass octave.
* Last note of each bar is a chromatic neighbour (root ± 1 semitone)
  of *next* bar's downbeat pitch — this is the "chromatic walk-in"
  that gives 90s G-funk bass its menacing half-step character.
* No melodic leap exceeds ``max_leap_semitones`` between adjacent
  played notes.

Soft probabilities (seeded RNG):

* Middle notes are sampled 60% from chord tones, 30% from the scale
  pool, 10% chromatic, then snapped to the nearest octave register.
* ``rest_probability`` drops middle notes (never the first or last).
"""

from __future__ import annotations

import random

from music_rules.core.generate._form import BarSlot
from music_rules.core.generate._theory import (
    chord_tone_pcs,
    midi_in_octave,
    parse_chord_symbol,
    scale_pcs,
    snap_pc_near,
)
from music_rules.core.generate.midi_write import NoteEvent, Track
from music_rules.core.generate.style import StyleProfile

BASS_CHANNEL = 0
_BEATS_PER_BAR = 4
_DIRECTION_OFFSETS: dict[str, tuple[int, ...]] = {
    "below": (-1,),
    "above": (+1,),
    "below_or_above": (-1, +1),
}


def bass_from_style(
    style: StyleProfile,
    slots: list[BarSlot],
    *,
    ticks_per_beat: int,
    rng: random.Random,
) -> Track:
    """Render the bass part across every bar in ``slots``."""
    bass = style.bass
    rules = bass.rules
    octave = bass.octave
    scale = scale_pcs(bass.scale_pool)
    direction_offsets = _DIRECTION_OFFSETS[rules.chromatic_approach_direction]
    max_leap = rules.max_leap_semitones

    events: list[NoteEvent] = []
    for i, slot in enumerate(slots):
        chord_root_pc, _ = parse_chord_symbol(slot.chord_symbol)
        next_slot = slots[i + 1] if i + 1 < len(slots) else slots[0]
        next_root_pc, _ = parse_chord_symbol(next_slot.chord_symbol)

        cell = rng.choice(bass.rhythm_cells_beats)
        n = len(cell)
        if n < 1:
            raise ValueError("rhythm cell must contain at least one duration")

        pitches: list[int] = [0] * n
        pitches[0] = midi_in_octave(chord_root_pc, octave)

        if n >= 2 and rules.approach_downbeat_with_chromatic_step:
            target_midi = midi_in_octave(next_root_pc, octave)
            offset = rng.choice(direction_offsets)
            approach_pc = (next_root_pc + offset) % 12
            pitches[-1] = snap_pc_near(approach_pc, target_midi)

        chord_pcs = chord_tone_pcs(slot.chord_symbol)
        for j in range(1, n - 1):
            roll = rng.random()
            if roll < 0.6:
                candidate_pcs: set[int] = chord_pcs
            elif roll < 0.9:
                candidate_pcs = scale
            else:
                candidate_pcs = set(range(12))
            prev = pitches[j - 1]
            options = [
                snap_pc_near(pc, prev)
                for pc in candidate_pcs
                if abs(snap_pc_near(pc, prev) - prev) <= max_leap
            ]
            pitches[j] = rng.choice(sorted(options)) if options else prev

        rest_mask = [False] * n
        for j in range(1, n - 1):
            if rng.random() < rules.rest_probability:
                rest_mask[j] = True

        cursor_beat = float(slot.bar_index * _BEATS_PER_BAR)
        for dur, pitch, rested in zip(cell, pitches, rest_mask, strict=True):
            if not rested:
                start = int(cursor_beat * ticks_per_beat)
                dur_ticks = max(40, int(dur * ticks_per_beat * 0.9))
                events.append(
                    NoteEvent(
                        pitch=pitch,
                        start_ticks=start,
                        duration_ticks=dur_ticks,
                        channel=BASS_CHANNEL,
                        velocity=bass.velocity,
                    )
                )
            cursor_beat += dur

    return Track(name="bass", channel=BASS_CHANNEL, program=bass.program, events=events)
