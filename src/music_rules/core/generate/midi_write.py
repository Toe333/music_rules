"""Event-based multi-track MIDI writer for the generator pipeline.

Unlike :func:`music_rules.core.midi.skytnt_bridge.rolls_to_midi`, this
writer takes explicit note events (pitch, start tick, duration ticks,
channel, velocity) instead of a held-pitch piano roll. That matters
because drum hits on consecutive grid steps must remain *separate*
short notes; the held-pitch encoder would merge them into one long
sustained note.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass

import mido

TICKS_PER_BEAT = 480
DRUM_CHANNEL = 9  # mido is 0-indexed; this is "channel 10" in GM nomenclature.


@dataclass(frozen=True)
class NoteEvent:
    """A single playable note. Ticks are absolute from the start of the piece."""

    pitch: int
    start_ticks: int
    duration_ticks: int
    channel: int
    velocity: int


@dataclass(frozen=True)
class Track:
    """One MIDI track: a GM program on a channel, plus its note events."""

    name: str
    channel: int
    program: int
    events: list[NoteEvent]


def write_midi(
    tracks: list[Track],
    *,
    tempo_bpm: int,
    meter: str = "4/4",
    ticks_per_beat: int = TICKS_PER_BEAT,
) -> bytes:
    """Encode ``tracks`` to raw MIDI bytes (GM, multi-track, type 1)."""
    if not tracks:
        raise ValueError("write_midi requires at least one track")

    midi = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)

    meta = mido.MidiTrack()
    midi.tracks.append(meta)
    tempo_us = int(60_000_000 / tempo_bpm)
    meta.append(mido.MetaMessage("set_tempo", tempo=tempo_us, time=0))
    num, den = (int(p) for p in meter.split("/"))
    meta.append(mido.MetaMessage("time_signature", numerator=num, denominator=den, time=0))

    for track in tracks:
        midi_track = mido.MidiTrack()
        midi.tracks.append(midi_track)
        midi_track.append(mido.MetaMessage("track_name", name=track.name, time=0))
        if track.channel != DRUM_CHANNEL:
            midi_track.append(
                mido.Message("program_change", channel=track.channel, program=track.program, time=0)
            )
        _emit_events_to_track(track.events, midi_track, track.channel)

    buf = io.BytesIO()
    midi.save(file=buf)
    return buf.getvalue()


def write_midi_base64(
    tracks: list[Track],
    *,
    tempo_bpm: int,
    meter: str = "4/4",
    ticks_per_beat: int = TICKS_PER_BEAT,
) -> str:
    """Convenience wrapper: :func:`write_midi` output, base64-encoded."""
    return base64.b64encode(
        write_midi(tracks, tempo_bpm=tempo_bpm, meter=meter, ticks_per_beat=ticks_per_beat)
    ).decode("ascii")


def _emit_events_to_track(
    events: list[NoteEvent],
    midi_track: mido.MidiTrack,
    channel: int,
) -> None:
    """Convert absolute-tick events to delta-time note_on / note_off messages."""
    messages: list[tuple[int, mido.Message]] = []
    for event in events:
        messages.append(
            (
                event.start_ticks,
                mido.Message(
                    "note_on",
                    channel=channel,
                    note=event.pitch,
                    velocity=event.velocity,
                    time=0,
                ),
            )
        )
        messages.append(
            (
                event.start_ticks + event.duration_ticks,
                mido.Message(
                    "note_off",
                    channel=channel,
                    note=event.pitch,
                    velocity=0,
                    time=0,
                ),
            )
        )

    # Sort by absolute tick; ties: note_off before note_on so back-to-back
    # same-pitch hits don't accidentally cancel each other.
    messages.sort(key=lambda m: (m[0], 0 if m[1].type == "note_off" else 1))

    cursor = 0
    for abs_tick, msg in messages:
        delta = abs_tick - cursor
        if delta < 0:
            raise RuntimeError("event ordering invariant violated")
        msg.time = delta
        midi_track.append(msg)
        cursor = abs_tick
