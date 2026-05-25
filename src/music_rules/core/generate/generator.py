"""Top-level orchestrator: :class:`StyleProfile` → MIDI bytes + summary."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from music_rules.core.generate._form import BarSlot, expand_form
from music_rules.core.generate.bass import bass_from_style
from music_rules.core.generate.chords import chord_pad_from_style
from music_rules.core.generate.drums import drums_from_style
from music_rules.core.generate.lead import lead_from_style
from music_rules.core.generate.midi_write import TICKS_PER_BEAT, Track, write_midi
from music_rules.core.generate.style import StyleProfile


@dataclass(frozen=True)
class GenerationResult:
    """The output of one :func:`generate_track` call."""

    midi_bytes: bytes
    tracks: list[Track]
    slots: list[BarSlot]
    summary: dict[str, Any] = field(default_factory=dict)


def generate_track(
    style: StyleProfile,
    *,
    seed: int = 0,
    ticks_per_beat: int = TICKS_PER_BEAT,
) -> GenerationResult:
    """Render a full multi-track piece from ``style``.

    Args:
        style:           A validated :class:`StyleProfile`.
        seed:            Fixed RNG seed; same seed + same style → same MIDI.
        ticks_per_beat:  MIDI PPQN. 480 is GM-friendly; tests may use less.

    Returns:
        A :class:`GenerationResult` whose ``midi_bytes`` field is the
        raw multi-track MIDI suitable for writing to disk or feeding
        back through :mod:`music_rules.core.midi.skytnt_bridge`.
    """
    rng = random.Random(seed)
    slots = expand_form(style)

    # Per-instrument RNGs forked from the master seed so swapping one
    # generator out doesn't perturb the others. (drum jitter does not
    # affect the bass walk, etc.)
    drum_rng = random.Random(rng.random())
    bass_rng = random.Random(rng.random())
    lead_rng = random.Random(rng.random())

    drum_track = drums_from_style(style, slots, ticks_per_beat=ticks_per_beat, rng=drum_rng)
    bass_track = bass_from_style(style, slots, ticks_per_beat=ticks_per_beat, rng=bass_rng)
    lead_track = lead_from_style(style, slots, ticks_per_beat=ticks_per_beat, rng=lead_rng)
    pad_track = chord_pad_from_style(style, slots, ticks_per_beat=ticks_per_beat)
    tracks = [drum_track, bass_track, lead_track, pad_track]

    midi_bytes = write_midi(
        tracks,
        tempo_bpm=style.tempo_bpm,
        meter=style.meter,
        ticks_per_beat=ticks_per_beat,
    )

    summary: dict[str, Any] = {
        "style": style.name,
        "seed": seed,
        "bars": len(slots),
        "events_by_track": {t.name: len(t.events) for t in tracks},
        "tempo_bpm": style.tempo_bpm,
        "meter": style.meter,
    }
    return GenerationResult(midi_bytes=midi_bytes, tracks=tracks, slots=slots, summary=summary)
