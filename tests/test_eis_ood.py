"""Phase 8 — Outside-Octave-Dissonance checker tests."""

from __future__ import annotations

from music_rules.core.eis import ood


class TestSingleVoicing:
    def test_close_voicing_no_ood(self) -> None:
        # All voices within an octave of the bass.
        assert ood.check_voicing([48, 52, 55, 60]) == []

    def test_clean_open_voicing_no_ood(self) -> None:
        # C E G B in open voicing — major 7th IS within an octave above
        # the bass, so no OOD.
        assert ood.check_voicing([48, 52, 55, 59]) == []

    def test_perfect_eleventh_no_ood_4_plus_10(self) -> None:
        # Bass C2 (36), upper Bb3 (58 = bass + 22 = 4 + 10 + 8 wait).
        # The "4 & 10 are fine" exception (O-005). 4+10 = 14? Actually
        # in the master rules, "4 & 10" means the perfect 4th (5 st) and
        # 10th degree. Test a benign perfect 11th interval.
        # Bass C2 (36), upper F4 (53) → interval 17 (P11), pc above = 5 = perfect 4th.
        # 5 is not in dissonant set, no hit.
        assert ood.check_voicing([36, 53]) == []

    def test_3_and_11_outside_octave_flagged(self) -> None:
        # Bass C2 (36), upper E4 (52 = +16). pc above = 4. interval >= 16.
        hits = ood.check_voicing([36, 52])
        assert any(h["rule_id"] == "O-004" for h in hits)

    def test_b9_without_b7_flagged(self) -> None:
        # Bass C2 (36), upper Db4 (49 = +13). pc above = 1. No ♭7.
        hits = ood.check_voicing([36, 49], has_b7=False)
        assert any(h["rule_id"] == "O-002" for h in hits)

    def test_b9_with_b7_allowed(self) -> None:
        # Same chord but ♭7 declared present.
        hits = ood.check_voicing([36, 49], has_b7=True)
        assert hits == []

    def test_b2_over_pedal_allowed(self) -> None:
        hits = ood.check_voicing([36, 49], pedal=True)
        assert hits == []

    def test_generic_ood_dissonance(self) -> None:
        # Bass C2 (36), upper B4 (71 = +35). pc above = 11 (M7).
        hits = ood.check_voicing([36, 71])
        assert any(h["rule_id"] == "O-001" for h in hits)


class TestPassageSweep:
    def test_passage_aggregates_per_chord(self) -> None:
        chord1 = [48, 52, 55, 60]                # clean
        chord2 = [36, 49]                        # ♭9 OOD
        hits = ood.check_passage([chord1, chord2])
        assert len(hits) == 1
        assert hits[0]["rule_id"] == "O-002"

    def test_passage_respects_per_chord_b7_pedal_lists(self) -> None:
        chord1 = [36, 49]
        chord2 = [36, 49]
        hits = ood.check_passage(
            [chord1, chord2], has_b7=[True, False],
        )
        assert len(hits) == 1                    # only chord 2 violates
