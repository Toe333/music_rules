"""Phase 8 — NCT insertion tests."""

from __future__ import annotations

import pytest

from music_rules.core.eis import nct


class TestNCTRegistry:
    def test_six_types_registered(self) -> None:
        assert set(nct.NCT_TYPES) == {"PT", "CA", "RT", "CT", "Sus", "Ant"}

    def test_each_type_has_rule_ref(self) -> None:
        for spec in nct.NCT_TYPES.values():
            assert spec["rule_ref"].startswith("N-")

    def test_list_nct_types(self) -> None:
        assert len(nct.list_nct_types()) == 6


class TestPassingTone:
    def test_pt_between_third(self) -> None:
        # Voice 0: C(60) → E(64). PT in C major scale = D(62).
        ev = nct.insert_nct(
            [60], [64], voice=0, nct_type="PT",
            scale_id="EIS-18-01",
        )
        assert ev["midi"] == 62
        assert ev["beat"] == 0.5
        assert ev["type"] == "PT"
        assert ev["rule_ref"] == "N-002"

    def test_pt_rejects_unison(self) -> None:
        with pytest.raises(ValueError, match="Passing tone"):
            nct.insert_nct([60], [60], voice=0, nct_type="PT")

    def test_pt_rejects_too_wide(self) -> None:
        with pytest.raises(ValueError, match="Passing tone"):
            nct.insert_nct([60], [72], voice=0, nct_type="PT")


class TestChromaticAlteration:
    def test_ca_one_semitone_toward_target(self) -> None:
        # 60 → 64: CA = 61 (chromatic step up).
        ev = nct.insert_nct([60], [64], voice=0, nct_type="CA")
        assert ev["midi"] == 61
        assert ev["type"] == "CA"


class TestReturningTone:
    def test_rt_upper_neighbour_in_c_major(self) -> None:
        ev = nct.insert_nct([60], [60], voice=0, nct_type="RT",
                             direction="up")
        # D is the next scale tone above C in C major.
        assert ev["midi"] == 62

    def test_rt_lower_neighbour_in_c_major(self) -> None:
        ev = nct.insert_nct([60], [60], voice=0, nct_type="RT",
                             direction="down")
        # B is the next scale tone below C.
        assert ev["midi"] == 59


class TestChordToneNCT:
    def test_ct_picks_closest_b_chord_tone(self) -> None:
        # Voice 0 sits at 60; chord_b = [55, 60, 64]. Closest = 60.
        ev = nct.insert_nct([60], [55], voice=0, nct_type="CT")
        assert ev["midi"] == 55


class TestSuspension:
    def test_sus_holds_a_into_b(self) -> None:
        ev = nct.insert_nct([60], [62], voice=0, nct_type="Sus")
        assert ev["midi"] == 60   # A's tone held over the bar
        assert ev["beat"] == 0.0


class TestAnticipation:
    def test_ant_sounds_b_early(self) -> None:
        ev = nct.insert_nct([60], [62], voice=0, nct_type="Ant")
        assert ev["midi"] == 62
        assert ev["beat"] == 0.75


class TestInputValidation:
    def test_unknown_nct_type(self) -> None:
        with pytest.raises(KeyError, match="Unknown nct_type"):
            nct.insert_nct([60], [62], voice=0, nct_type="XX")  # type: ignore[arg-type]

    def test_voice_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="voice"):
            nct.insert_nct([60], [62], voice=5, nct_type="PT")

    def test_chord_length_mismatch(self) -> None:
        with pytest.raises(ValueError, match="length mismatch"):
            nct.insert_nct([60, 64], [62], voice=0, nct_type="PT")
