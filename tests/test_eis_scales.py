"""Phase 7 — EIS scale registry tests."""

from __future__ import annotations

import pytest

from music_rules.core.eis import scales


class TestRegistry:
    def test_eighteen_scales_present(self) -> None:
        assert len(scales.SCALES) == 18

    def test_ids_are_zero_padded(self) -> None:
        assert "EIS-18-01" in scales.SCALES
        assert "EIS-18-18" in scales.SCALES

    def test_all_scales_have_required_fields(self) -> None:
        required = {"id", "number", "name", "degrees", "notes", "status"}
        for s in scales.SCALES.values():
            assert required.issubset(set(s.keys()))
            assert s["status"] in ("verified", "inferred", "pending")

    def test_numbers_are_one_through_eighteen(self) -> None:
        nums = sorted(s["number"] for s in scales.SCALES.values())
        assert nums == list(range(1, 19))


class TestVerifiedScales:
    def test_natural_major_is_diatonic(self) -> None:
        s = scales.get_scale("EIS-18-01")
        assert s["status"] == "verified"
        assert s["degrees"] == [0, 2, 4, 5, 7, 9, 11]

    def test_lydian_dominant_is_acoustic(self) -> None:
        s = scales.get_scale("EIS-18-04")
        assert s["status"] == "verified"
        assert s["degrees"] == [0, 2, 4, 6, 7, 9, 10]

    def test_dom7b9_is_half_whole_diminished(self) -> None:
        s = scales.get_scale("EIS-18-10")
        assert s["status"] == "verified"
        # 8-note half-whole diminished
        assert s["degrees"] == [0, 1, 3, 4, 6, 7, 9, 10]


class TestScalePcs:
    def test_natural_major_in_c(self) -> None:
        assert scales.scale_pcs("EIS-18-01", "C") == [0, 2, 4, 5, 7, 9, 11]

    def test_natural_major_in_g(self) -> None:
        # G major: G A B C D E F#  →  7 9 11 0 2 4 6
        assert scales.scale_pcs("EIS-18-01", "G") == [7, 9, 11, 0, 2, 4, 6]

    def test_pending_scale_raises(self) -> None:
        # Phase 8 has no pending scales, but the registry still
        # supports them — verify by injecting a synthetic stub.
        synthetic = scales.Scale(
            id="EIS-TEST", number=99, name="stub",
            degrees=None, notes="test fixture", status="pending",
        )
        scales.SCALES["EIS-TEST"] = synthetic
        try:
            with pytest.raises(ValueError, match="status='pending'"):
                scales.scale_pcs("EIS-TEST", "C")
        finally:
            del scales.SCALES["EIS-TEST"]

    def test_unknown_scale_id_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown scale id"):
            scales.scale_pcs("EIS-18-99", "C")


class TestListAndCount:
    def test_list_all(self) -> None:
        assert len(scales.list_scales()) == 18

    def test_list_verified(self) -> None:
        verified = scales.list_scales(status="verified")
        ids = {s["id"] for s in verified}
        assert ids >= {"EIS-18-01", "EIS-18-04", "EIS-18-10"}

    def test_available_count_sums_to_total(self) -> None:
        c = scales.available_count()
        assert c["total"] == 18
        non_total = sum(v for k, v in c.items() if k != "total")
        assert non_total == 18
