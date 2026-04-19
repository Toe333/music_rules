"""Phase 8 — EIS chord builder tests."""

from __future__ import annotations

import pytest

from music_rules.core.eis import chords

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestChordClassRegistry:
    def test_basic_classes_present(self) -> None:
        for cid in (
            "triad", "triad-min", "triad-7", "triad-min-7", "9", "6",
            "dom7", "min7", "min7b5", "min9", "dom7b9", "dom9", "dom13",
            "dom11", "4th-3p", "4th-4p", "polytonal",
        ):
            assert cid in chords.CHORD_CLASSES

    def test_each_class_has_required_fields(self) -> None:
        required = {"id", "parts", "intervals", "implied_scale",
                    "quality", "rule_ref", "description"}
        for cls in chords.CHORD_CLASSES.values():
            assert required.issubset(set(cls.keys()))
            assert cls["parts"], "parts list must not be empty"
            assert cls["intervals"], "intervals list must not be empty"

    def test_list_chord_classes(self) -> None:
        assert len(chords.list_chord_classes()) == len(chords.CHORD_CLASSES)


# ---------------------------------------------------------------------------
# Pitch-class derivation
# ---------------------------------------------------------------------------


class TestPitchClasses:
    def test_c_major_triad(self) -> None:
        assert chords.pitch_classes("C", "triad") == [0, 4, 7]

    def test_c_minor_triad(self) -> None:
        assert chords.pitch_classes("C", "triad-min") == [0, 3, 7]

    def test_c_natural_seventh(self) -> None:
        assert chords.pitch_classes("C", "triad-7") == [0, 4, 7, 11]

    def test_c_dom7(self) -> None:
        assert chords.pitch_classes("C", "dom7") == [0, 4, 7, 10]

    def test_c_min7(self) -> None:
        assert chords.pitch_classes("C", "min7") == [0, 3, 7, 10]

    def test_c_min7b5(self) -> None:
        assert chords.pitch_classes("C", "min7b5") == [0, 3, 6, 10]

    def test_c_dom7b9(self) -> None:
        # C E G Bb Db → 0, 4, 7, 10, 1.
        assert chords.pitch_classes("C", "dom7b9") == [0, 4, 7, 10, 1]

    def test_c_dom9(self) -> None:
        # C E G Bb D → 0, 4, 7, 10, 2.
        assert chords.pitch_classes("C", "dom9") == [0, 4, 7, 10, 2]

    def test_g_dom7(self) -> None:
        assert chords.pitch_classes("G", "dom7") == [7, 11, 2, 5]

    def test_unknown_class_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown chord_class"):
            chords.pitch_classes("C", "nope")

    def test_unknown_scale_id_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown scale id"):
            chords.pitch_classes("C", "triad", scale_id="EIS-18-99")

    def test_pending_scale_does_not_raise(self) -> None:
        # Pending scales are OK as advisory hints.
        out = chords.pitch_classes("C", "triad", scale_id="EIS-18-02")
        assert out == [0, 4, 7]


# ---------------------------------------------------------------------------
# build_chord
# ---------------------------------------------------------------------------


class TestBuildChord:
    def test_close_c_major_triad_in_octave_4(self) -> None:
        midi = chords.build_chord("C", "triad", voicing="close", base_octave=4)
        assert midi == [60, 64, 67]

    def test_close_c_maj7_in_octave_4(self) -> None:
        # C maj7 = C E G B = 60, 64, 67, 71.
        midi = chords.build_chord("C", "triad-7", voicing="close", base_octave=4)
        assert midi == [60, 64, 67, 71]

    def test_open_voicing_drop2_on_4_part(self) -> None:
        # Drop-2 on C maj7: G (67) drops to G3 (55). Result sorted.
        opened = chords.build_chord(
            "C", "triad-7", voicing="open", base_octave=4,
        )
        assert opened == [55, 60, 64, 71]

    def test_inversion_rotates_bass(self) -> None:
        # 1st inversion of C triad = E in bass = E G C → 64, 67, 72.
        m1 = chords.build_chord("C", "triad", inversion=1, base_octave=4)
        assert m1 == [64, 67, 72]
        # 2nd inversion: G C E → 67, 72, 76.
        m2 = chords.build_chord("C", "triad", inversion=2, base_octave=4)
        assert m2 == [67, 72, 76]

    def test_default_parts_picks_smallest_supported(self) -> None:
        midi = chords.build_chord("C", "dom9")
        assert len(midi) == chords.CHORD_CLASSES["dom9"]["parts"][0]

    def test_dom9_4p_drops_the_fifth(self) -> None:
        # 4P dom9 should drop the 5th: C E Bb D (no G).
        midi = chords.build_chord("C", "dom9", parts=4, base_octave=4)
        # 60=C, 64=E, 70=Bb, 74=D. No 67 (G).
        assert 67 not in midi
        assert {p % 12 for p in midi} == {0, 4, 10, 2}

    def test_dom9_5p_keeps_everything(self) -> None:
        midi = chords.build_chord("C", "dom9", parts=5, base_octave=4)
        assert {p % 12 for p in midi} == {0, 4, 7, 10, 2}

    def test_invalid_parts_raises(self) -> None:
        with pytest.raises(ValueError, match="supports parts="):
            chords.build_chord("C", "triad", parts=2)

    def test_invalid_inversion_raises(self) -> None:
        with pytest.raises(ValueError, match="inversion must be"):
            chords.build_chord("C", "triad", inversion=5)

    def test_output_is_sorted_low_to_high(self) -> None:
        for cid in ("triad", "triad-min", "dom7", "min7",
                    "triad-7", "min9", "dom7b9", "4th-3p", "4th-4p"):
            midi = chords.build_chord("C", cid)
            assert midi == sorted(midi)

    def test_4th_chord_3p_quartal_stack(self) -> None:
        # 4th-3p = root + P4 + ♭7 → C, F, B♭ → 60, 65, 70.
        midi = chords.build_chord("C", "4th-3p", base_octave=4)
        assert midi == [60, 65, 70]

    def test_4th_chord_4p_quartal_stack(self) -> None:
        # 4th-4p = root + P4 + ♭7 + 4-on-top (15 semis) → C, F, B♭, E♭.
        midi = chords.build_chord("C", "4th-4p", base_octave=4)
        # 60=C, 65=F, 70=Bb, 75=Eb.
        assert midi == [60, 65, 70, 75]

    def test_base_octave_affects_register(self) -> None:
        low = chords.build_chord("C", "triad", base_octave=3)
        high = chords.build_chord("C", "triad", base_octave=5)
        assert all(h == low_n + 24 for h, low_n in zip(high, low, strict=True))

    def test_polytonal_two_triad_stack(self) -> None:
        midi = chords.build_chord("C", "polytonal", parts=5, base_octave=3)
        # All MIDI numbers ascending and span > one octave.
        assert midi == sorted(midi)
        assert midi[-1] - midi[0] >= 12
