"""Phase 4 — passage evaluator tests.

Exercises ``evaluate_passage`` end-to-end on:

1. The clean 7-note 2v 1st-species fixture — must produce zero hard
   violations and an A or B grade.
2. The parallel-fifths fixture — must produce multiple P1_1_2v hard
   violations and an F grade.
3. The wrong-opening / wrong-closing fixtures — single-rule isolation.
4. A constructed 4-bar piece — verifies the report shape exactly
   matches the MCP spec §2 Group D.
5. include / exclude rule-ID filters.
6. Per-rule summary aggregation.
"""

from __future__ import annotations

from typing import Any

import pytest

from music_rules import evaluate_passage

from .fixtures.fux_passages import (
    CLEAN_2V_1S_C_MAJOR,
    PARALLEL_FIFTHS_FAIL,
    WRONG_CLOSING_INTERVAL_FAIL,
    WRONG_OPENING_INTERVAL_FAIL,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _piece(fixture: dict[str, Any]) -> dict[str, Any]:
    """Translate a FuxPassage fixture into the evaluator's input shape."""
    return {
        "voices": [fixture["cf"], fixture["cp"]],
        "meter": "4/4",
        "key": "C",
        "species": fixture["species"],
        "cantus_firmus_voice": 0,
    }


def _rule_ids_in(report: dict[str, Any], section: str) -> set[str]:
    return {item["rule_id"] for item in report[section]}


# ---------------------------------------------------------------------------
# Report shape — verifies exact spec compliance (§2 Group D)
# ---------------------------------------------------------------------------


class TestReportShape:
    def test_keys_match_spec_exactly(self) -> None:
        report = evaluate_passage(_piece(CLEAN_2V_1S_C_MAJOR))
        assert set(report.keys()) == {
            "total_cost",
            "hard_violations",
            "soft_violations",
            "per_rule_summary",
            "grade",
        }

    def test_hard_violation_entries_have_required_keys(self) -> None:
        report = evaluate_passage(_piece(PARALLEL_FIFTHS_FAIL))
        assert report["hard_violations"], "expected at least one hard violation"
        for v in report["hard_violations"]:
            assert {"rule_id", "position", "voices_involved", "msg"} <= v.keys()
            assert isinstance(v["voices_involved"], list)
            assert v["position"] >= 0

    def test_soft_violation_entries_have_required_keys(self) -> None:
        # G7 (small-interval preference) fires soft costs on any leap.
        # Build a piece whose CP has a P5 leap to guarantee at least one.
        piece = {
            "voices": [
                [60, 60, 60, 60],   # CF: held C
                [67, 60, 67, 60],   # CP: G C G C — P5 leap each step
            ],
            "species": 1,
            "cantus_firmus_voice": 0,
        }
        report = evaluate_passage(piece)
        assert report["soft_violations"]
        for c in report["soft_violations"]:
            assert {"rule_id", "position", "cost", "msg"} <= c.keys()
            assert c["cost"] > 0

    def test_grade_is_a_letter(self) -> None:
        report = evaluate_passage(_piece(CLEAN_2V_1S_C_MAJOR))
        assert report["grade"] in {"A", "B", "C", "D", "F"}


# ---------------------------------------------------------------------------
# Clean fixture should pass cleanly
# ---------------------------------------------------------------------------


class TestCleanFixturePasses:
    def test_no_hard_violations(self) -> None:
        report = evaluate_passage(_piece(CLEAN_2V_1S_C_MAJOR))
        assert report["hard_violations"] == [], (
            f"Unexpected hard violations on clean fixture: {report['hard_violations']}"
        )

    def test_grade_is_a_or_b(self) -> None:
        report = evaluate_passage(_piece(CLEAN_2V_1S_C_MAJOR))
        # Stepwise + all-consonant should grade A or B (small G7 step costs).
        assert report["grade"] in {"A", "B"}, (
            f"Expected A or B grade for clean fixture; got {report['grade']} "
            f"with cost {report['total_cost']}"
        )

    def test_total_cost_is_low(self) -> None:
        report = evaluate_passage(_piece(CLEAN_2V_1S_C_MAJOR))
        assert report["total_cost"] < 5.0


# ---------------------------------------------------------------------------
# Failing fixtures should fail at the right rules
# ---------------------------------------------------------------------------


class TestParallelFifthsFixtureFails:
    def test_multiple_P1_1_2v_violations(self) -> None:
        report = evaluate_passage(_piece(PARALLEL_FIFTHS_FAIL))
        p1_violations = [
            v for v in report["hard_violations"] if v["rule_id"] == "P1_1_2v"
        ]
        assert len(p1_violations) >= 2, (
            f"Expected multiple parallel-5ths violations; got {p1_violations}"
        )

    def test_grade_is_F(self) -> None:
        report = evaluate_passage(_piece(PARALLEL_FIFTHS_FAIL))
        assert report["grade"] == "F"

    def test_per_rule_summary_counts_correctly(self) -> None:
        report = evaluate_passage(_piece(PARALLEL_FIFTHS_FAIL))
        p1_summary = report["per_rule_summary"].get("P1_1_2v")
        assert p1_summary is not None
        assert p1_summary["count"] == sum(
            1 for v in report["hard_violations"] if v["rule_id"] == "P1_1_2v"
        )
        assert p1_summary["total_cost"] is None  # hard rule, no soft cost


class TestWrongOpeningFixtureFails:
    def test_H2_1_only_violation(self) -> None:
        report = evaluate_passage(_piece(WRONG_OPENING_INTERVAL_FAIL))
        assert "H2_1" in _rule_ids_in(report, "hard_violations")


class TestWrongClosingFixtureFails:
    def test_H3_1_only_violation(self) -> None:
        report = evaluate_passage(_piece(WRONG_CLOSING_INTERVAL_FAIL))
        assert "H3_1" in _rule_ids_in(report, "hard_violations")


# ---------------------------------------------------------------------------
# 4-bar canonical evaluation (the spec calls this out explicitly)
# ---------------------------------------------------------------------------


class TestFourBarPassage:
    """The spec asks for a 4-bar test specifically. Each beat is one quarter
    note in 4/4, so 16 events total. We use a 16-event 1st-species 2v passage
    in C major where every check should pass."""

    @pytest.fixture()
    def piece(self) -> dict[str, Any]:
        # 4 bars * 4 beats = 16 notes per voice.
        # CF: a slow whole-note ascent and descent (repeated within bar).
        # CP: contrary-motion smooth steps.
        cf = [
            60, 60, 60, 60,   # bar 1: C
            62, 62, 62, 62,   # bar 2: D
            64, 64, 64, 64,   # bar 3: E
            60, 60, 60, 60,   # bar 4: C
        ]
        cp = [
            67, 67, 67, 67,   # bar 1: G  (P5 above C)
            65, 65, 65, 65,   # bar 2: F  (m3 above D)
            64, 64, 64, 64,   # bar 3: E  (P1 unison E)
            67, 67, 67, 67,   # bar 4: G  (P5 above C)
        ]
        return {
            "voices": [cf, cp],
            "meter": "4/4",
            "key": "C",
            "species": 1,
            "cantus_firmus_voice": 0,
        }

    def test_no_hard_violations(self, piece: dict[str, Any]) -> None:
        report = evaluate_passage(piece)
        # Same-pitch repeats may trigger M2_2_2v ("two consecutive notes same"),
        # but that rule is not in the Phase-3 set we run today.
        # Motion check should be all oblique → no P1_ violations.
        # Opening/closing both P5 → H2_1 / H3_1 satisfied.
        assert report["hard_violations"] == [], (
            f"Expected zero hard violations on the 4-bar fixture; "
            f"got: {report['hard_violations']}"
        )

    def test_grade_high(self, piece: dict[str, Any]) -> None:
        report = evaluate_passage(piece)
        assert report["grade"] in {"A", "B"}


# ---------------------------------------------------------------------------
# include / exclude filters
# ---------------------------------------------------------------------------


class TestRuleFilters:
    def test_exclude_drops_specific_rule(self) -> None:
        unfiltered = evaluate_passage(_piece(PARALLEL_FIFTHS_FAIL))
        filtered = evaluate_passage(_piece(PARALLEL_FIFTHS_FAIL), exclude=["P1_1_2v"])
        assert "P1_1_2v" in _rule_ids_in(unfiltered, "hard_violations")
        assert "P1_1_2v" not in _rule_ids_in(filtered, "hard_violations")

    def test_include_keeps_only_listed_rule(self) -> None:
        report = evaluate_passage(
            _piece(PARALLEL_FIFTHS_FAIL), include=["P1_1_2v"]
        )
        assert _rule_ids_in(report, "hard_violations") == {"P1_1_2v"}

    def test_include_with_no_matches_yields_empty(self) -> None:
        report = evaluate_passage(
            _piece(PARALLEL_FIFTHS_FAIL), include=["NOPE_999"]
        )
        assert report["hard_violations"] == []
        assert report["soft_violations"] == []


# ---------------------------------------------------------------------------
# Ruleset switching
# ---------------------------------------------------------------------------


class TestRulesetSwitching:
    def test_eis_ruleset_runs_eis_only(self) -> None:
        # ruleset="EIS" should skip Fux checkers entirely — even the
        # parallel-fifths failure fixture should not produce P1_1_2v hits.
        piece = _piece(PARALLEL_FIFTHS_FAIL)
        piece["check_ood"] = False  # silence OOD pass for this assertion
        report = evaluate_passage(piece, ruleset="EIS")
        assert report["hard_violations"] == []
        assert report["soft_violations"] == []

    def test_both_ruleset_matches_fux_for_hard_violations(self) -> None:
        # Hard hits come from Fux; Fux-only and "both" should agree on those.
        fux_report = evaluate_passage(_piece(PARALLEL_FIFTHS_FAIL), ruleset="Fux")
        both_report = evaluate_passage(_piece(PARALLEL_FIFTHS_FAIL), ruleset="both")
        assert _rule_ids_in(fux_report, "hard_violations") == _rule_ids_in(
            both_report, "hard_violations"
        )


# ---------------------------------------------------------------------------
# Voice-range constraints (Phase 8.7)
# ---------------------------------------------------------------------------


class TestVoiceRanges:
    def test_satb_preset_passes_when_in_range(self) -> None:
        piece = {
            "voices": [[40, 43, 45, 40], [60, 64, 65, 60]],
            "voice_ranges": "satb",
        }
        report = evaluate_passage(piece, ruleset="Fux")
        rg_hits = [h for h in report["hard_violations"]
                   if h["rule_id"] == "RG-001"]
        assert rg_hits == []

    def test_satb_preset_flags_out_of_range_pitch(self) -> None:
        # Bass voice (index 0) gets a high B5 (83) — way above bass top (60).
        piece = {
            "voices": [[40, 83, 45, 40], [60, 64, 65, 60]],
            "voice_ranges": "satb",
        }
        report = evaluate_passage(piece, ruleset="Fux")
        rg_hits = [h for h in report["hard_violations"]
                   if h["rule_id"] == "RG-001"]
        assert len(rg_hits) == 1
        assert rg_hits[0]["position"] == 1
        assert rg_hits[0]["voices_involved"] == [0]

    def test_explicit_per_voice_ranges(self) -> None:
        piece = {
            "voices": [[60, 62, 64, 60], [72, 74, 76, 72]],
            "voice_ranges": [[55, 65], [70, 79]],
        }
        report = evaluate_passage(piece, ruleset="Fux")
        rg_hits = [h for h in report["hard_violations"]
                   if h["rule_id"] == "RG-001"]
        assert rg_hits == []

    def test_unknown_preset_raises(self) -> None:
        with pytest.raises(ValueError, match="voice_ranges preset"):
            evaluate_passage({
                "voices": [[60, 62], [67, 69]],
                "voice_ranges": "wat",
            })

    def test_wrong_length_raises(self) -> None:
        with pytest.raises(ValueError, match="voice_ranges must be"):
            evaluate_passage({
                "voices": [[60, 62], [67, 69]],
                "voice_ranges": [[40, 60]],   # only 1 entry for 2 voices
            })


# ---------------------------------------------------------------------------
# EIS pass — OOD soft hits
# ---------------------------------------------------------------------------


class TestEISPass:
    def test_ood_pass_can_be_disabled(self) -> None:
        # A clean passage with check_ood=False should produce no soft hits
        # from O-* rules.
        piece = _piece(CLEAN_2V_1S_C_MAJOR)
        piece["check_ood"] = False
        report = evaluate_passage(piece, ruleset="both")
        ood_hits = [s for s in report["soft_violations"]
                    if s["rule_id"].startswith("O-")]
        assert ood_hits == []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestPieceValidation:
    def test_missing_voices_raises(self) -> None:
        with pytest.raises(ValueError, match="must contain 'voices'"):
            evaluate_passage({})  # type: ignore[arg-type]

    def test_unequal_voice_lengths_raises(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            evaluate_passage({"voices": [[60, 62, 64], [67, 69]]})

    def test_out_of_range_cf_index_raises(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            evaluate_passage(
                {"voices": [[60, 62], [67, 69]], "cantus_firmus_voice": 5}
            )
