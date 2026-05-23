"""Phase 7 — EIS Root-tone (E-cycle) tests.

Verifies:

* All 6 cycles have the documented step + length.
* Cycle generation matches the canonical examples in the master rules
  doc §4 (e.g. E5 from C → F → B♭ → E♭ → … 12 distinct pitch classes).
* ``pick_root_line`` is deterministic given a seed, never raises on
  legal inputs, always returns the requested length.
* Multi-cycle walks switch cycles correctly.
* ``is_valid_progression`` accepts both the canonical step and its
  inversion (P4 == P5 inverted in E5).
"""

from __future__ import annotations

import pytest

from music_rules.core.eis import roots

# ---------------------------------------------------------------------------
# Cycle definitions
# ---------------------------------------------------------------------------


class TestCycleConstants:
    def test_all_six_cycles_present(self) -> None:
        assert set(roots.E_CYCLES) == {"E1", "E2", "E3", "E4", "E5", "E6"}

    @pytest.mark.parametrize(
        ("cid", "step", "length"),
        [
            ("E1", 1, 12),
            ("E2", 2, 6),
            ("E3", 3, 4),
            ("E4", 4, 3),
            ("E5", 5, 12),
            ("E6", 6, 2),
        ],
    )
    def test_step_and_length(self, cid: str, step: int, length: int) -> None:
        assert roots.E_CYCLES[cid] == step
        assert roots.CYCLE_LENGTHS[cid] == length


# ---------------------------------------------------------------------------
# cycle_root_pcs / cycle_root_names
# ---------------------------------------------------------------------------


class TestCycleGeneration:
    def test_e5_from_c_is_circle_of_fourths(self) -> None:
        # C → F → Bb → Eb → Ab → Db → Gb → B → E → A → D → G
        names = roots.cycle_root_names("E5", "C")
        assert names == ["C", "F", "Bb", "Eb", "Ab", "Db", "Gb", "B", "E", "A", "D", "G"]

    def test_e2_from_c_whole_tone(self) -> None:
        names = roots.cycle_root_names("E2", "C")
        assert names == ["C", "D", "E", "F#", "G#", "A#"]

    def test_e3_from_c_minor_third_cycle(self) -> None:
        # 4-tone diminished ring.
        pcs = roots.cycle_root_pcs("E3", "C")
        assert pcs == [0, 3, 6, 9]

    def test_e4_from_c_major_third_cycle(self) -> None:
        pcs = roots.cycle_root_pcs("E4", "C")
        assert pcs == [0, 4, 8]

    def test_e6_from_c_tritone_pair(self) -> None:
        names = roots.cycle_root_names("E6", "C")
        assert names == ["C", "F#"]

    def test_e1_from_c_chromatic(self) -> None:
        pcs = roots.cycle_root_pcs("E1", "C")
        assert pcs == list(range(12))

    def test_pitch_class_input_works(self) -> None:
        names_from_str = roots.cycle_root_names("E4", "C")
        names_from_pc = roots.cycle_root_names("E4", 0)
        assert names_from_str == names_from_pc


# ---------------------------------------------------------------------------
# pick_root_line
# ---------------------------------------------------------------------------


class TestPickRootLine:
    def test_default_returns_e5_walk(self) -> None:
        line = roots.pick_root_line(length=4, start_root="C")
        # First four E5 steps from C.
        assert line == ["C", "F", "Bb", "Eb"]

    def test_length_one_works(self) -> None:
        assert roots.pick_root_line(length=1) == ["C"]

    @pytest.mark.parametrize("length", [2, 5, 8, 16, 32])
    def test_returned_length_always_matches(self, length: int) -> None:
        line = roots.pick_root_line(length=length)
        assert len(line) == length

    def test_zero_length_raises(self) -> None:
        with pytest.raises(ValueError, match="length must be"):
            roots.pick_root_line(length=0)

    def test_unknown_cycle_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown cycle"):
            roots.pick_root_line(length=4, cycles=["E99"])  # type: ignore[list-item]

    def test_seed_makes_elision_deterministic(self) -> None:
        a = roots.pick_root_line(
            length=20,
            cycles=["E4", "E5"],
            seed=42,
            allow_elision=True,
        )
        b = roots.pick_root_line(
            length=20,
            cycles=["E4", "E5"],
            seed=42,
            allow_elision=True,
        )
        assert a == b

    def test_e6_only_repeats_after_two_steps(self) -> None:
        # E6 has only two pitch classes; a 6-step request should still
        # produce 6 entries, repeating the pair.
        line = roots.pick_root_line(length=6, cycles=["E6"])
        assert len(line) == 6
        assert set(line) == {"C", "F#"}

    def test_multi_cycle_switches_when_first_completes(self) -> None:
        # Start in E4 (length 3), then E5 picks up.
        line = roots.pick_root_line(
            length=10,
            cycles=["E4", "E5"],
            seed=0,
            allow_elision=False,
        )
        assert len(line) == 10
        # First three should be the E4 walk from C.
        assert line[:3] == ["C", "E", "G#"]


# ---------------------------------------------------------------------------
# is_valid_progression
# ---------------------------------------------------------------------------


class TestIsValidProgression:
    def test_circle_of_fourths_is_e5(self) -> None:
        assert roots.is_valid_progression(["C", "F", "Bb"], allowed_cycles=["E5"])

    def test_circle_of_fifths_also_in_e5_via_inversion(self) -> None:
        # C → G is +7 = -5 mod 12, the inversion of P4. Same cycle.
        assert roots.is_valid_progression(["C", "G", "D"], allowed_cycles=["E5"])

    def test_chromatic_not_in_e5(self) -> None:
        assert not roots.is_valid_progression(["C", "C#", "D"], allowed_cycles=["E5"])

    def test_chromatic_is_e1(self) -> None:
        assert roots.is_valid_progression(["C", "C#", "D"], allowed_cycles=["E1"])

    def test_single_root_always_valid(self) -> None:
        assert roots.is_valid_progression(["C"])

    def test_empty_always_valid(self) -> None:
        assert roots.is_valid_progression([])

    def test_default_allowed_cycles_accepts_anything_consistent(self) -> None:
        # E2 step (D) should pass when we don't restrict cycles.
        assert roots.is_valid_progression(["C", "D"])
