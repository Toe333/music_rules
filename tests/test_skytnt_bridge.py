"""MIDI ↔ piano-roll bridge + SkyTNT generation tests.

We exercise round-trip fidelity (rolls → MIDI bytes → rolls), per-voice
GM programs, and the SkyTNT generation hooks (mocked when the optional
``transformers`` extras are not installed)."""

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
# Per-voice programs (Phase 8.8)
# ---------------------------------------------------------------------------


class TestPerVoicePrograms:
    def test_chip_tune_programs(self) -> None:
        # 4 voices, distinct GM programs (square / square / triangle / noise).
        programs = [80, 80, 87, 122]
        out = bridge.rolls_to_midi(
            [[60, 62, 64, 65]] * 4,
            programs=programs,
        )
        assert isinstance(out, str)
        # Re-parse and verify the program_change events landed.
        import io

        import mido

        midi = mido.MidiFile(file=io.BytesIO(base64.b64decode(out)))
        # Track 0 is meta; tracks 1..4 should each have a program_change.
        seen = []
        for track in midi.tracks[1:]:
            for msg in track:
                if msg.type == "program_change":
                    seen.append(msg.program)
                    break
        assert seen == programs

    def test_program_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="programs has length"):
            bridge.rolls_to_midi(
                [[60, 62], [60, 62]],
                programs=[1, 2, 3],
            )


# ---------------------------------------------------------------------------
# SkyTNT generation (lazy / extras-gated)
# ---------------------------------------------------------------------------


class TestSkytntGeneration:
    def test_generate_raises_unavailable_when_extras_missing(self) -> None:
        # Force-clear the cache and ensure the loader path fires.
        bridge._SKYTNT_MODEL = None
        bridge._SKYTNT_TOKENIZER = None
        bridge._SKYTNT_DEVICE = None
        try:
            import transformers  # noqa: F401
        except ImportError:
            with pytest.raises(bridge.SkyTNTUnavailableError):
                bridge.skytnt_generate()
        else:
            pytest.skip("transformers installed; this test only verifies the no-extras path")

    def test_constrained_generate_returns_dict_when_no_extras(self) -> None:
        # When the extras are missing, _ensure_skytnt() raises and
        # skytnt_constrained_generate() should propagate it.
        try:
            import transformers  # noqa: F401
        except ImportError:
            with pytest.raises(bridge.SkyTNTUnavailableError):
                bridge.skytnt_constrained_generate()
        else:
            pytest.skip("transformers installed; skip extras-missing path")
