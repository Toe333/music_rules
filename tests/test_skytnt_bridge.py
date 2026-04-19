"""Phase 7 — MIDI <-> piano-roll bridge tests.

We exercise round-trip fidelity (rolls → MIDI bytes → rolls) and the
Phase-8 generation stubs.
"""

from __future__ import annotations

import base64

import pytest

pytest.importorskip("mido")

from music_rules.core.midi import skytnt_bridge as bridge  # noqa: I001


# ---------------------------------------------------------------------------
# rolls_to_midi
# ---------------------------------------------------------------------------


class TestRollsToMidi:
    def test_returns_base64_string(self) -> None:
        out = bridge.rolls_to_midi([[60, 62, 64, 65]])
        assert isinstance(out, str)
        # Decoding must succeed and produce a valid MIDI header.
        raw = base64.b64decode(out)
        assert raw[:4] == b"MThd"

    def test_empty_voices_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty voice"):
            bridge.rolls_to_midi([])
        with pytest.raises(ValueError, match="non-empty voice"):
            bridge.rolls_to_midi([[]])

    def test_meter_parses(self) -> None:
        # Should not raise even for non-4/4 meters.
        out = bridge.rolls_to_midi([[60, 62]], meter="3/4")
        assert isinstance(out, str)


# ---------------------------------------------------------------------------
# midi_to_rolls
# ---------------------------------------------------------------------------


class TestMidiToRolls:
    def test_round_trip_simple_line(self) -> None:
        original = [60, 62, 64, 65, 67]
        midi_b64 = bridge.rolls_to_midi([original])
        bundle = bridge.midi_to_rolls(midi_b64)
        assert len(bundle["voices"]) == 1
        assert bundle["voices"][0] == original

    def test_round_trip_with_rests(self) -> None:
        original = [60, -1, 60, -1, 67]
        midi_b64 = bridge.rolls_to_midi([original])
        bundle = bridge.midi_to_rolls(midi_b64)
        assert bundle["voices"][0] == original

    def test_round_trip_repeated_notes(self) -> None:
        original = [60, 60, 60, 64]
        midi_b64 = bridge.rolls_to_midi([original])
        bundle = bridge.midi_to_rolls(midi_b64)
        assert bundle["voices"][0] == original

    def test_round_trip_two_voices_padded(self) -> None:
        midi_b64 = bridge.rolls_to_midi([[60, 62, 64, 65], [48, 50, 52, 53]])
        bundle = bridge.midi_to_rolls(midi_b64)
        assert len(bundle["voices"]) == 2
        assert bundle["voices"][0] == [60, 62, 64, 65]
        assert bundle["voices"][1] == [48, 50, 52, 53]

    def test_meta_extraction(self) -> None:
        midi_b64 = bridge.rolls_to_midi([[60, 62]], meter="3/4", tempo=400_000)
        bundle = bridge.midi_to_rolls(midi_b64)
        assert bundle["meter"] == "3/4"
        assert bundle["tempo"] == 400_000
        assert bundle["ticks_per_beat"] == 480
        # No key signature was set, so key_guess stays None.
        assert bundle["key_guess"] is None

    def test_invalid_input_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="neither an existing file"):
            bridge.midi_to_rolls("this is not a valid midi blob ###")

    def test_bytes_input_works(self) -> None:
        midi_b64 = bridge.rolls_to_midi([[60, 62, 64]])
        raw = base64.b64decode(midi_b64)
        bundle = bridge.midi_to_rolls(raw)
        assert bundle["voices"][0] == [60, 62, 64]


# ---------------------------------------------------------------------------
# Phase-8 stubs
# ---------------------------------------------------------------------------


class TestSkytntStubs:
    def test_generate_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="phase 8"):
            bridge.skytnt_generate()

    def test_constrained_generate_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="phase 8"):
            bridge.skytnt_constrained_generate()
