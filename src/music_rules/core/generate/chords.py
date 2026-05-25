"""Chord-pad renderer.

Holds the configured voicing for the full duration of each chord
(across every bar that chord occupies). One soft, sustained pad layer
behind the drum/bass/lead — the canonical G-funk Rhodes/strings bed.
"""

from __future__ import annotations

from music_rules.core.generate._form import BarSlot
from music_rules.core.generate.midi_write import NoteEvent, Track
from music_rules.core.generate.style import StyleProfile

PAD_CHANNEL = 2
_BEATS_PER_BAR = 4


def chord_pad_from_style(
    style: StyleProfile,
    slots: list[BarSlot],
    *,
    ticks_per_beat: int,
) -> Track:
    """Render the sustained chord pad across every bar in ``slots``."""
    pad = style.chord_pad
    events: list[NoteEvent] = []

    # Group consecutive bars sharing the same chord into single held voicings.
    if not slots:
        return Track(name="chord_pad", channel=PAD_CHANNEL, program=pad.program, events=events)

    group_start_bar = slots[0].bar_index
    group_chord = slots[0].chord_symbol
    for i in range(1, len(slots) + 1):
        ended = i == len(slots) or slots[i].chord_symbol != group_chord
        if ended:
            bars_held = (slots[i - 1].bar_index - group_start_bar) + 1
            start_tick = group_start_bar * _BEATS_PER_BAR * ticks_per_beat
            dur_ticks = bars_held * _BEATS_PER_BAR * ticks_per_beat - 20
            voicing = style.harmony.voicing.get(group_chord, [])
            for pitch in voicing:
                events.append(
                    NoteEvent(
                        pitch=pitch + 12 * pad.octave_offset,
                        start_ticks=start_tick,
                        duration_ticks=dur_ticks,
                        channel=PAD_CHANNEL,
                        velocity=pad.velocity,
                    )
                )
            if i < len(slots):
                group_start_bar = slots[i].bar_index
                group_chord = slots[i].chord_symbol

    return Track(name="chord_pad", channel=PAD_CHANNEL, program=pad.program, events=events)
