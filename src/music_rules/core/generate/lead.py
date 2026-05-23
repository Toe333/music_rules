"""Lead-line renderer (Moog-style monophonic synth).

The lead is sparse: it only plays on bars that the style's
``active_on_bars_in_phrase`` permits (with an opt-in override for the
B section), and even on active bars a configurable rest probability
can keep it silent. On long-duration slots the renderer biases toward
the configured "blue note" — for the bundled Dre style that is
``Eb``, the ♭5 against A minor, which is where the menacing whine
comes from.
"""

from __future__ import annotations

import random

from music_rules.core.generate._form import BarSlot
from music_rules.core.generate._theory import midi_in_octave, note_to_pc, snap_pc_near
from music_rules.core.generate.midi_write import NoteEvent, Track
from music_rules.core.generate.style import StyleProfile

LEAD_CHANNEL = 1
_BEATS_PER_BAR = 4
_LONG_NOTE_BEATS = 1.5


def lead_from_style(
    style: StyleProfile,
    slots: list[BarSlot],
    *,
    ticks_per_beat: int,
    rng: random.Random,
) -> Track:
    """Render the lead line across every active bar in ``slots``."""
    lead = style.lead
    rules = lead.rules
    octave = lead.octave
    bars_per_section = style.form.bars_per_section
    b_always_on = style.form.B_section.lead_active_on_all_bars

    scale_pcs_list = [note_to_pc(n) for n in lead.scale_pool]
    blue_pc = note_to_pc(rules.emphasize_blue_note) if rules.emphasize_blue_note else None
    reference_midi = midi_in_octave(scale_pcs_list[0], octave)

    events: list[NoteEvent] = []
    for slot in slots:
        bar_in_section_one_indexed = (slot.bar_index % bars_per_section) + 1
        active_by_phrase = bar_in_section_one_indexed in rules.active_on_bars_in_phrase
        active_by_b_override = slot.section_label == "B" and b_always_on
        if not (active_by_phrase or active_by_b_override):
            continue
        if rng.random() < rules.rest_probability_per_bar:
            continue

        cell = rng.choice(lead.rhythm_cells_beats)
        cursor_beat = float(slot.bar_index * _BEATS_PER_BAR)
        prev_midi = reference_midi
        for dur in cell:
            if blue_pc is not None and dur >= _LONG_NOTE_BEATS and rng.random() < 0.7:
                pc = blue_pc
            else:
                pc = rng.choice(scale_pcs_list)
            candidate = snap_pc_near(pc, prev_midi)
            if abs(candidate - prev_midi) > rules.max_leap_semitones:
                # Pull it back toward prev_midi by an octave if needed.
                candidate = snap_pc_near(pc, prev_midi)
                while candidate - prev_midi > rules.max_leap_semitones:
                    candidate -= 12
                while prev_midi - candidate > rules.max_leap_semitones:
                    candidate += 12
            start = int(cursor_beat * ticks_per_beat)
            dur_ticks = max(40, int(dur * ticks_per_beat * 0.95))
            events.append(
                NoteEvent(
                    pitch=candidate,
                    start_ticks=start,
                    duration_ticks=dur_ticks,
                    channel=LEAD_CHANNEL,
                    velocity=lead.velocity,
                )
            )
            prev_midi = candidate
            cursor_beat += dur
        reference_midi = prev_midi

    return Track(name="lead", channel=LEAD_CHANNEL, program=lead.program, events=events)
