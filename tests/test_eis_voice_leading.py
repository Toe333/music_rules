"""Phase 8 — EIS voice-leading tests (V-001..V-015)."""

from __future__ import annotations

import pytest

from music_rules.core.eis import chords
from music_rules.core.eis import voice_leading as vl

# ---------------------------------------------------------------------------
# voice_lead — re-voicing
# ---------------------------------------------------------------------------


class TestVoiceLead:
    def test_c_to_g_smooth_re_voicing(self) -> None:
        # C major triad → G major triad. Smoothest move:
        # C(60) → B(59) or D(62), E(64) → D(62) or G(67), G(67) → G(67).
        c = chords.build_chord("C", "triad", base_octave=4)  # [60, 64, 67]
        g_pcs = chords.pitch_classes("G", "triad")  # [7, 11, 2]
        result = vl.voice_lead(c, g_pcs)
        # G (7) is the closest pc to bass C (0) within an octave (5 st up).
        # So bass should move from 60 to 55 or 67.
        assert len(result) == 3
        # All target pcs must be present.
        assert {p % 12 for p in result} == {7, 11, 2}
        # Voice motion should be small.
        report = vl.check_progression(c, result)
        assert report["total_motion"] <= 12

    def test_held_common_tone_kept(self) -> None:
        # C major → A minor: shared E and C tones.
        c = chords.build_chord("C", "triad", base_octave=4)  # [60, 64, 67]
        a_min_pcs = chords.pitch_classes("A", "triad-min")  # [9, 0, 4]
        result = vl.voice_lead(c, a_min_pcs)
        report = vl.check_progression(c, result)
        # At least one voice should have held its pitch.
        assert report["common_tones"] >= 1

    def test_bracket_style_drops_one_voice(self) -> None:
        c = chords.build_chord("C", "triad-7", base_octave=4)  # 4 voices
        g_pcs = chords.pitch_classes("G", "dom7")
        result = vl.voice_lead(c, g_pcs, style="bracket")
        assert len(result) == 3  # one voice dropped per V-013

    def test_parallel_style_keeps_intervals(self) -> None:
        c = chords.build_chord("C", "triad", base_octave=4)  # [60, 64, 67]
        d_pcs = chords.pitch_classes("D", "triad")  # [2, 6, 9]
        result = vl.voice_lead(c, d_pcs, style="parallel")
        # All voices should have moved by roughly the same amount.
        diffs = sorted({r - cv for r, cv in zip(result, c, strict=True)})
        assert len(diffs) == 1, f"expected uniform shift, got {diffs}"

    def test_empty_inputs_raise(self) -> None:
        with pytest.raises(ValueError, match="prev_chord"):
            vl.voice_lead([], [0, 4, 7])
        with pytest.raises(ValueError, match="next_pcs"):
            vl.voice_lead([60, 64, 67], [])


# ---------------------------------------------------------------------------
# check_progression — scoring an existing move
# ---------------------------------------------------------------------------


class TestCheckProgression:
    def test_held_chord_is_perfectly_smooth(self) -> None:
        c = [60, 64, 67]
        rep = vl.check_progression(c, c)
        assert rep["smoothness"] == 1.0
        assert rep["total_motion"] == 0
        assert rep["common_tones"] == 3
        assert rep["violations"] == []

    def test_parallel_octaves_flagged(self) -> None:
        # Bass C → D up a whole step; treble C → D up a whole step → //8va.
        prev = [48, 60]  # C2 + C4
        nxt = [50, 62]  # D2 + D4
        rep = vl.check_progression(prev, nxt)
        assert any(v["rule_id"] == "V-014" for v in rep["violations"])

    def test_v002_flags_large_jumps(self) -> None:
        prev = [60, 64, 67]
        nxt = [60, 64, 79]  # voice 2 jumps a P8 (12 st)
        rep = vl.check_progression(prev, nxt)
        assert any(v["rule_id"] == "V-002" and 2 in v["voices"] for v in rep["violations"])

    def test_v004_three_tones_together(self) -> None:
        # Three Cs in three different octaves.
        prev = [60, 64, 67]
        nxt = [48, 60, 72]
        rep = vl.check_progression(prev, nxt)
        assert any(v["rule_id"] == "V-004" for v in rep["violations"])

    def test_contrary_motion_counted(self) -> None:
        # Bass goes down, treble voice goes up.
        prev = [60, 64, 67]
        nxt = [55, 65, 69]
        rep = vl.check_progression(prev, nxt)
        assert rep["contrary_motion_pairs"] >= 1

    def test_mismatched_lengths_raise(self) -> None:
        with pytest.raises(ValueError, match="length mismatch"):
            vl.check_progression([60, 64], [60, 64, 67])

    def test_smoothness_decreases_with_motion(self) -> None:
        a = vl.check_progression([60, 64, 67], [60, 64, 67])  # 0 motion
        b = vl.check_progression([60, 64, 67], [62, 66, 69])  # 6 motion
        c = vl.check_progression([60, 64, 67], [55, 60, 64])  # 14 motion
        assert a["smoothness"] > b["smoothness"] > c["smoothness"]


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------


class TestRuleRegistry:
    def test_all_rule_ids_in_registry(self) -> None:
        for rid in ("V-001", "V-002", "V-003", "V-004", "V-006", "V-014"):
            assert rid in vl.VOICE_LEADING_RULES
