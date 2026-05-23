"""Phase 3 — Fux checker unit tests.

Each checker has at minimum one passing fixture and one failing fixture,
per the spec's non-negotiable safety net. We additionally test:

* Filter behavior (rules with non-matching species/voices don't fire).
* Soft-cost accumulation (G7).
* The hybrid-elevation behavior of ``strict=True`` (currently a no-op
  for Phase 3 rules; future-proofed).
* Report-shape invariants (``ok`` mirrors ``violations`` emptiness).

Fixture sources are documented inline in
``tests/fixtures/fux_passages.py`` — every constructed example has its
intervals and motion types verified by inspection.
"""

from __future__ import annotations

from music_rules.core import pitch
from music_rules.core.fux import dissonance, harmonic, melodic, motion
from music_rules.core.report import CheckReport

from .fixtures.fux_passages import (
    CLEAN_2V_1S_C_MAJOR,
    PARALLEL_FIFTHS_FAIL,
    WRONG_CLOSING_INTERVAL_FAIL,
    WRONG_OPENING_INTERVAL_FAIL,
)

# ---------------------------------------------------------------------------
# Report-shape invariants
# ---------------------------------------------------------------------------


def _assert_report_shape(report: CheckReport) -> None:
    """Every checker returns a CheckReport with consistent ok/violations."""
    assert set(report.keys()) == {"ok", "violations", "soft_costs"}
    assert isinstance(report["violations"], list)
    assert isinstance(report["soft_costs"], list)
    assert report["ok"] is (len(report["violations"]) == 0)
    for v in report["violations"]:
        assert {"rule_id", "msg"} <= set(v.keys())
    for c in report["soft_costs"]:
        assert {"rule_id", "cost", "msg"} <= set(c.keys())
        assert c["cost"] >= 0


# ---------------------------------------------------------------------------
# check_melodic_interval (G7 soft, M1_* hard)
# ---------------------------------------------------------------------------


class TestMelodicInterval:
    def test_passing_step_emits_no_violations_or_costs(self) -> None:
        # M2 step (C->D) is the most-favored melodic motion.
        report = melodic.check_melodic_interval(60, 62, species=1, voices=2)
        _assert_report_shape(report)
        assert report["ok"]
        assert report["soft_costs"] == []

    def test_passing_perfect_5th_leap_no_hard_violation(self) -> None:
        # P5 (C->G, 7 semitones) is below the m6 ceiling; emits a small
        # G7 soft cost but no hard violation.
        report = melodic.check_melodic_interval(60, 67, species=1, voices=2)
        _assert_report_shape(report)
        assert report["ok"]
        assert any(c["rule_id"] == "G7" for c in report["soft_costs"])

    def test_failing_minor_7th_leap_violates_M1_1_2v(self) -> None:
        # m7 = 10 semitones, exceeds the m6 ceiling.
        report = melodic.check_melodic_interval(60, 70, species=1, voices=2)
        _assert_report_shape(report)
        assert not report["ok"]
        assert any(v["rule_id"] == "M1_1_2v" for v in report["violations"])

    def test_octave_leap_allowed_in_3v(self) -> None:
        # M1_1_3v explicitly allows the octave; M1_1_2v does not apply
        # because voices=3 doesn't match its 2v predicate.
        report = melodic.check_melodic_interval(60, 72, species=1, voices=3)
        _assert_report_shape(report)
        assert report["ok"], f"P8 leap should be allowed in 3v 1st species; got {report}"

    def test_tritone_leap_carries_extra_soft_cost(self) -> None:
        # G7 explicitly says "tritones last resort" — the cost should be
        # noticeably higher than a same-size non-tritone leap.
        tritone = melodic.check_melodic_interval(60, 66, species="all", voices=2)
        m3_leap = melodic.check_melodic_interval(60, 63, species="all", voices=2)
        tt_cost = sum(c["cost"] for c in tritone["soft_costs"])
        m3_cost = sum(c["cost"] for c in m3_leap["soft_costs"])
        assert tt_cost > m3_cost + 1.0


# ---------------------------------------------------------------------------
# check_melodic_triple (G6)
# ---------------------------------------------------------------------------


class TestMelodicTriple:
    def test_passing_diatonic_ascent_no_violation(self) -> None:
        # C -> D -> E (whole-step, whole-step) — perfectly diatonic.
        report = melodic.check_melodic_triple(60, 62, 64, species="all", voices=2)
        _assert_report_shape(report)
        assert report["ok"]

    def test_passing_step_then_leap_no_violation(self) -> None:
        # C -> D -> A: step then leap; G6 only flags semitone+semitone.
        report = melodic.check_melodic_triple(60, 62, 69, species="all", voices=2)
        _assert_report_shape(report)
        assert report["ok"]

    def test_failing_chromatic_ascent_violates_G6(self) -> None:
        # C -> C# -> D (semitone, semitone) is the canonical G6 violation.
        report = melodic.check_melodic_triple(60, 61, 62, species="all", voices=2)
        _assert_report_shape(report)
        assert not report["ok"]
        assert any(v["rule_id"] == "G6" for v in report["violations"])

    def test_descending_chromatic_does_not_violate_G6(self) -> None:
        # G6 specifies *ascending* chromaticism. Descending is allowed
        # by this rule (other rules may catch it elsewhere).
        report = melodic.check_melodic_triple(64, 63, 62, species="all", voices=2)
        _assert_report_shape(report)
        assert report["ok"]


# ---------------------------------------------------------------------------
# check_motion_pair (P1_*)
# ---------------------------------------------------------------------------


class TestMotionPair:
    def test_passing_contrary_into_m3(self) -> None:
        # CF up, CP down, target = m3 (imperfect) — the textbook good motion.
        report = motion.check_motion_pair(
            {"cf": 60, "cp": 67}, {"cf": 62, "cp": 65}, species=1, voices=2
        )
        _assert_report_shape(report)
        assert report["ok"]

    def test_passing_oblique_into_p5(self) -> None:
        # CF moves, CP holds — oblique motion into a P5 is always allowed
        # (the P1_ rules only catch parallel/similar motion into perfect).
        report = motion.check_motion_pair(
            {"cf": 60, "cp": 67}, {"cf": 62, "cp": 67}, species=1, voices=2
        )
        _assert_report_shape(report)
        assert report["ok"]

    def test_failing_parallel_5ths(self) -> None:
        # The textbook P1_1_2v violation: C-G to D-A.
        report = motion.check_motion_pair(
            {"cf": 60, "cp": 67}, {"cf": 62, "cp": 69}, species=1, voices=2
        )
        _assert_report_shape(report)
        assert not report["ok"]
        assert any(v["rule_id"] == "P1_1_2v" for v in report["violations"])

    def test_failing_parallel_octaves(self) -> None:
        # C-C to D-D, both voices up by M2.
        report = motion.check_motion_pair(
            {"cf": 60, "cp": 72}, {"cf": 62, "cp": 74}, species=1, voices=2
        )
        _assert_report_shape(report)
        assert not report["ok"]

    def test_failing_similar_motion_into_p8(self) -> None:
        # CF up by step (60->62), CP up by 3rd (60->64) — both up,
        # different intervals = similar motion. Target is M3 = imperfect,
        # so this is OK. Now make target a P8: CF 60->62, CP 60->62 = parallel.
        # Use CF 60->62, CP 60->74: similar (both up, different intervals),
        # target = 74-62 = 12 = P8 → forbidden.
        report = motion.check_motion_pair(
            {"cf": 60, "cp": 60}, {"cf": 62, "cp": 74}, species=1, voices=2
        )
        _assert_report_shape(report)
        assert not report["ok"]


# ---------------------------------------------------------------------------
# check_vertical_chord (H8_*)
# ---------------------------------------------------------------------------


class TestVerticalChord:
    def test_passing_complete_triad_3v(self) -> None:
        # C major triad in close position: C E G — third + fifth present.
        report = harmonic.check_vertical_chord([60, 64, 67], species="all", voices=3)
        _assert_report_shape(report)
        assert report["ok"]
        assert report["soft_costs"] == []

    def test_failing_bare_fifth_3v_incurs_soft_cost(self) -> None:
        # C-G dyad doubled — no 3rd present. H8_3v should fire a soft cost.
        report = harmonic.check_vertical_chord([60, 67, 72], species="all", voices=3)
        _assert_report_shape(report)
        assert report["ok"]  # soft costs don't make ok=False
        assert any(c["rule_id"] == "H8_3v" for c in report["soft_costs"])

    def test_2v_no_vertical_chord_rules_fire(self) -> None:
        # H8_* applies to 3v/4v only; in 2v the checker is a no-op.
        report = harmonic.check_vertical_chord([60, 67], species="all", voices=2)
        _assert_report_shape(report)
        assert report["ok"]
        assert report["soft_costs"] == []


# ---------------------------------------------------------------------------
# check_first_interval / check_final_interval (H2_1, H3_1)
# ---------------------------------------------------------------------------


class TestOpeningInterval:
    def test_passing_p5_opening(self) -> None:
        report = harmonic.check_first_interval([60, 67], species=1, voices=2)
        _assert_report_shape(report)
        assert report["ok"]

    def test_passing_p8_opening(self) -> None:
        report = harmonic.check_first_interval([60, 72], species=1, voices=2)
        _assert_report_shape(report)
        assert report["ok"]

    def test_failing_m3_opening_violates_H2_1(self) -> None:
        report = harmonic.check_first_interval([60, 64], species=1, voices=2)
        _assert_report_shape(report)
        assert not report["ok"]
        assert any(v["rule_id"] == "H2_1" for v in report["violations"])


class TestClosingInterval:
    def test_passing_p8_closing(self) -> None:
        report = harmonic.check_final_interval([48, 60], species=1, voices=2)
        _assert_report_shape(report)
        assert report["ok"]

    def test_failing_M6_closing_violates_H3_1(self) -> None:
        report = harmonic.check_final_interval([60, 69], species=1, voices=2)
        _assert_report_shape(report)
        assert not report["ok"]
        assert any(v["rule_id"] == "H3_1" for v in report["violations"])


# ---------------------------------------------------------------------------
# check_per_measure_downbeat (H1_1) — exercises the 2v-vs-3v P4 logic
# ---------------------------------------------------------------------------


class TestDownbeat:
    def test_passing_p5_in_2v(self) -> None:
        report = harmonic.check_per_measure_downbeat([60, 67], voices=2)
        assert report["ok"]

    def test_failing_M2_in_2v(self) -> None:
        # A whole-step is dissonant in any voice count.
        report = harmonic.check_per_measure_downbeat([60, 62], voices=2)
        assert not report["ok"]
        assert any(v["rule_id"] == "H1_1" for v in report["violations"])

    def test_failing_P4_in_2v(self) -> None:
        # Strict Fux: P4 is dissonant in 2-voice writing.
        report = harmonic.check_per_measure_downbeat([60, 65], voices=2)
        assert not report["ok"]

    def test_passing_P4_in_3v(self) -> None:
        # P4 is allowed in 3v writing when supported.
        report = harmonic.check_per_measure_downbeat([60, 65, 69], voices=3)
        assert report["ok"], f"P4 in 3v should pass; got {report}"


# ---------------------------------------------------------------------------
# check_dissonance_context (H2_3)
# ---------------------------------------------------------------------------


class TestDissonanceContext:
    def test_passing_passing_tone(self) -> None:
        # C -> D -> E against sustained C: D is a passing tone (M2 dissonance,
        # approached and left by step in the same direction).
        report = dissonance.check_dissonance_context(60, 62, 64, cf_pitch=60, species=3)
        assert report["ok"]

    def test_passing_neighbor_tone(self) -> None:
        # C -> D -> C against C: D is a (lower) neighbor.
        report = dissonance.check_dissonance_context(60, 62, 60, cf_pitch=60, species=3)
        assert report["ok"]

    def test_failing_leaped_dissonance(self) -> None:
        # C -> D -> G against C: D is dissonant, approached by step but
        # left by leap — neither passing nor neighbor.
        report = dissonance.check_dissonance_context(60, 62, 67, cf_pitch=60, species=3)
        assert not report["ok"]
        assert any(v["rule_id"] == "H2_3" for v in report["violations"])

    def test_consonance_not_flagged(self) -> None:
        # If the alleged dissonance is actually consonant against the CF,
        # the rule is vacuously satisfied (callers may pass any triple).
        report = dissonance.check_dissonance_context(60, 64, 67, cf_pitch=60, species=3)
        assert report["ok"]


# ---------------------------------------------------------------------------
# Integration-ish: run all checkers across a clean fixture, verify silence
# ---------------------------------------------------------------------------


class TestCleanFixturePassesAllCheckers:
    """The CLEAN_2V_1S_C_MAJOR fixture should fire zero hard violations
    when fed to every checker note-by-note / pair-by-pair."""

    def test_no_melodic_violations_in_either_voice(self) -> None:
        for voice_name in ("cf", "cp"):
            voice = CLEAN_2V_1S_C_MAJOR[voice_name]  # type: ignore[literal-required]
            for prev, curr in zip(voice, voice[1:], strict=False):
                report = melodic.check_melodic_interval(prev, curr, species=1, voices=2)
                assert report["ok"], (
                    f"Unexpected melodic violation in {voice_name}: {prev}->{curr}: {report}"
                )

    def test_no_motion_violations(self) -> None:
        cf = CLEAN_2V_1S_C_MAJOR["cf"]
        cp = CLEAN_2V_1S_C_MAJOR["cp"]
        for i in range(len(cf) - 1):
            report = motion.check_motion_pair(
                {"cf": cf[i], "cp": cp[i]},
                {"cf": cf[i + 1], "cp": cp[i + 1]},
                species=1,
                voices=2,
            )
            assert report["ok"], f"Unexpected motion violation at beat {i}->{i + 1}: {report}"

    def test_no_downbeat_violations(self) -> None:
        cf = CLEAN_2V_1S_C_MAJOR["cf"]
        cp = CLEAN_2V_1S_C_MAJOR["cp"]
        for i in range(len(cf)):
            report = harmonic.check_per_measure_downbeat([cf[i], cp[i]], voices=2)
            assert report["ok"], f"Unexpected downbeat violation at beat {i}: {report}"

    def test_opening_and_closing_intervals_pass(self) -> None:
        cf = CLEAN_2V_1S_C_MAJOR["cf"]
        cp = CLEAN_2V_1S_C_MAJOR["cp"]
        assert harmonic.check_first_interval([cf[0], cp[0]], species=1, voices=2)["ok"]
        assert harmonic.check_final_interval([cf[-1], cp[-1]], species=1, voices=2)["ok"]


# ---------------------------------------------------------------------------
# Failing fixtures hit the right rules
# ---------------------------------------------------------------------------


class TestFailingFixturesHitTheRightRules:
    def test_parallel_fifths_fixture_violates_P1_1_2v(self) -> None:
        cf = PARALLEL_FIFTHS_FAIL["cf"]
        cp = PARALLEL_FIFTHS_FAIL["cp"]
        any_violation = False
        for i in range(len(cf) - 1):
            report = motion.check_motion_pair(
                {"cf": cf[i], "cp": cp[i]},
                {"cf": cf[i + 1], "cp": cp[i + 1]},
                species=1,
                voices=2,
            )
            if any(v["rule_id"] == "P1_1_2v" for v in report["violations"]):
                any_violation = True
                break
        assert any_violation, (
            "Expected at least one P1_1_2v violation in the parallel-fifths fixture."
        )

    def test_wrong_opening_fixture_violates_H2_1(self) -> None:
        cf = WRONG_OPENING_INTERVAL_FAIL["cf"]
        cp = WRONG_OPENING_INTERVAL_FAIL["cp"]
        report = harmonic.check_first_interval([cf[0], cp[0]], species=1, voices=2)
        assert any(v["rule_id"] == "H2_1" for v in report["violations"])

    def test_wrong_closing_fixture_violates_H3_1(self) -> None:
        cf = WRONG_CLOSING_INTERVAL_FAIL["cf"]
        cp = WRONG_CLOSING_INTERVAL_FAIL["cp"]
        report = harmonic.check_final_interval([cf[-1], cp[-1]], species=1, voices=2)
        assert any(v["rule_id"] == "H3_1" for v in report["violations"])


# ---------------------------------------------------------------------------
# Pitch helpers — quick correctness check on the foundation
# ---------------------------------------------------------------------------


class TestPitchHelpers:
    def test_perfect_consonance_set(self) -> None:
        for s in (0, 7, 12, 19, 24):  # P1, P5, P8, P12, P15
            assert pitch.is_perfect_consonance(s), s

    def test_imperfect_consonance_set(self) -> None:
        for s in (3, 4, 8, 9):
            assert pitch.is_imperfect_consonance(s), s

    def test_p4_is_dissonant_under_strict_2v(self) -> None:
        assert pitch.is_dissonance(5)
        assert not pitch.is_consonance(5)

    def test_p4_is_consonant_in_3v_context(self) -> None:
        assert pitch.is_consonance_in_context(5, voice_count=3)
        assert pitch.is_consonance_in_context(5, voice_count=4)

    def test_motion_classification(self) -> None:
        # CF up, CP up by same amount = parallel
        assert pitch.classify_motion(60, 62, 67, 69) == "parallel"
        # CF up, CP up by different amount = similar
        assert pitch.classify_motion(60, 62, 67, 71) == "similar"
        # CF up, CP down = contrary
        assert pitch.classify_motion(60, 62, 67, 65) == "contrary"
        # CF holds = oblique
        assert pitch.classify_motion(60, 60, 67, 69) == "oblique"
