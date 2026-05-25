"""Tests for the deterministic rule-based generator (Dre 1990s Gangsta).

Verifies the four invariants that distinguish this generator from a
generic Markov roll-out:

1. **Determinism** — same seed + same style → byte-identical MIDI.
2. **Bass downbeat = chord root** of the current bar (octave-checked).
3. **Chromatic walk-in** — last bass note of every bar is ±1 semitone
   from the next bar's downbeat pitch.
4. **Drum fidelity** — the rendered drum track reproduces the profile
   pattern exactly (no missed or extra hits).
"""

from __future__ import annotations

import io

import mido
import pytest

from music_rules.core.generate import generate_track, load_style
from music_rules.core.generate._form import expand_form
from music_rules.core.generate._theory import parse_chord_symbol
from music_rules.core.generate.bass import BASS_CHANNEL
from music_rules.core.generate.midi_write import DRUM_CHANNEL, TICKS_PER_BEAT


@pytest.fixture(scope="module")
def style():
    return load_style("dre_1990s_gangsta")


@pytest.fixture(scope="module")
def result(style):
    return generate_track(style, seed=1990)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_same_bytes(self, style) -> None:
        a = generate_track(style, seed=7).midi_bytes
        b = generate_track(style, seed=7).midi_bytes
        assert a == b

    def test_different_seed_different_bytes(self, style) -> None:
        a = generate_track(style, seed=1).midi_bytes
        b = generate_track(style, seed=2).midi_bytes
        assert a != b


# ---------------------------------------------------------------------------
# Bass rules
# ---------------------------------------------------------------------------


def _bass_events_by_bar(result, ticks_per_bar):
    """Group bass note events by bar index, sorted by start tick."""
    bass = next(t for t in result.tracks if t.channel == BASS_CHANNEL)
    by_bar: dict[int, list] = {}
    for ev in bass.events:
        bar = ev.start_ticks // ticks_per_bar
        by_bar.setdefault(bar, []).append(ev)
    for events in by_bar.values():
        events.sort(key=lambda e: e.start_ticks)
    return by_bar


class TestBassRules:
    def test_downbeat_is_chord_root(self, style, result) -> None:
        slots = expand_form(style)
        ticks_per_bar = 4 * TICKS_PER_BEAT
        by_bar = _bass_events_by_bar(result, ticks_per_bar)
        for slot in slots:
            events = by_bar[slot.bar_index]
            assert events, f"bar {slot.bar_index} has no bass notes"
            root_pc, _ = parse_chord_symbol(slot.chord_symbol)
            assert events[0].pitch % 12 == root_pc, (
                f"bar {slot.bar_index} ({slot.chord_symbol}): "
                f"downbeat pitch {events[0].pitch} pc={events[0].pitch % 12}, "
                f"expected root pc {root_pc}"
            )

    def test_chromatic_approach_into_next_downbeat(self, style, result) -> None:
        slots = expand_form(style)
        ticks_per_bar = 4 * TICKS_PER_BEAT
        by_bar = _bass_events_by_bar(result, ticks_per_bar)
        for i, slot in enumerate(slots):
            next_slot = slots[(i + 1) % len(slots)]
            last_in_bar = by_bar[slot.bar_index][-1]
            first_of_next = by_bar[next_slot.bar_index][0]
            delta = abs(last_in_bar.pitch - first_of_next.pitch)
            assert delta == 1, (
                f"bar {slot.bar_index} → {next_slot.bar_index}: "
                f"last bass {last_in_bar.pitch} to next downbeat "
                f"{first_of_next.pitch} not a chromatic step (Δ={delta})"
            )


# ---------------------------------------------------------------------------
# Drum fidelity
# ---------------------------------------------------------------------------


class TestDrumFidelity:
    def test_pattern_hit_count_matches_profile(self, style, result) -> None:
        drums = next(t for t in result.tracks if t.channel == DRUM_CHANNEL)
        bars = len(expand_form(style))
        for piece_name, pattern in style.drums.pattern.items():
            midi_note = style.drums.midi_notes[piece_name]
            hits = [e for e in drums.events if e.pitch == midi_note]
            assert len(hits) == sum(pattern) * bars, (
                f"drum {piece_name!r}: rendered {len(hits)} hits, expected {sum(pattern) * bars}"
            )

    def test_drum_velocity_boost_in_B_section(self, style, result) -> None:
        boost = style.form.B_section.drum_velocity_boost
        if boost <= 0:
            pytest.skip("style has no B-section velocity boost")
        slots = expand_form(style)
        ticks_per_bar = 4 * TICKS_PER_BEAT
        drums = next(t for t in result.tracks if t.channel == DRUM_CHANNEL)
        kick_note = style.drums.midi_notes["kick"]
        a_kick_velocities, b_kick_velocities = [], []
        for ev in drums.events:
            if ev.pitch != kick_note:
                continue
            bar = ev.start_ticks // ticks_per_bar
            (b_kick_velocities if slots[bar].section_label == "B" else a_kick_velocities).append(
                ev.velocity
            )
        # Means should differ by ~boost (within humanize jitter).
        assert sum(b_kick_velocities) / len(b_kick_velocities) > sum(a_kick_velocities) / len(
            a_kick_velocities
        )


# ---------------------------------------------------------------------------
# MIDI well-formedness
# ---------------------------------------------------------------------------


class TestMidiRoundTrip:
    def test_mido_can_parse_output(self, result) -> None:
        midi = mido.MidiFile(file=io.BytesIO(result.midi_bytes))
        # 1 meta track + 4 instrument tracks.
        assert len(midi.tracks) == 5
        # Should be playable end to end without exceptions.
        list(midi)
