"""Drum-roll renderer: a boolean step pattern + GM drum kit → note events.

The pattern is interpreted as an N-step grid covering one bar (8 steps
for ``"8th"`` resolution, 16 for ``"16th"``). Drum hits are short
discrete notes on the GM drum channel; they do not sustain.
"""

from __future__ import annotations

import random

from music_rules.core.generate._form import BarSlot
from music_rules.core.generate.midi_write import DRUM_CHANNEL, NoteEvent, Track
from music_rules.core.generate.style import StyleProfile

_BEATS_PER_BAR = 4  # All bundled styles use 4/4 meter.
_DRUM_HIT_DURATION_TICKS = 60  # short, percussive; full note in ~1/8 of a beat.


def drums_from_style(
    style: StyleProfile,
    slots: list[BarSlot],
    *,
    ticks_per_beat: int,
    rng: random.Random,
) -> Track:
    """Render the drum part across every bar in ``slots``."""
    res = style.drums.pattern_resolution
    steps_per_bar = 8 if res == "8th" else 16
    step_ticks = (_BEATS_PER_BAR * ticks_per_beat) // steps_per_bar

    for piece_name, pattern in style.drums.pattern.items():
        if len(pattern) != steps_per_bar:
            raise ValueError(
                f"drum pattern {piece_name!r} has {len(pattern)} steps; "
                f"expected {steps_per_bar} for resolution {res!r}"
            )

    boost = style.form.B_section.drum_velocity_boost
    humanize = style.drums.humanize_velocity

    events: list[NoteEvent] = []
    for slot in slots:
        bar_tick = slot.bar_index * _BEATS_PER_BAR * ticks_per_beat
        velocity_boost = boost if slot.section_label == "B" else 0
        for piece_name, pattern in style.drums.pattern.items():
            base_velocity = style.drums.velocity[piece_name] + velocity_boost
            midi_note = style.drums.midi_notes[piece_name]
            for step, on in enumerate(pattern):
                if not on:
                    continue
                # Pulse the velocity slightly so the loop doesn't feel mechanical.
                jitter = rng.randint(-humanize, humanize) if humanize else 0
                velocity = max(1, min(127, base_velocity + jitter))
                events.append(
                    NoteEvent(
                        pitch=midi_note,
                        start_ticks=bar_tick + step * step_ticks,
                        duration_ticks=_DRUM_HIT_DURATION_TICKS,
                        channel=DRUM_CHANNEL,
                        velocity=velocity,
                    )
                )

    return Track(name="drums", channel=DRUM_CHANNEL, program=0, events=events)
