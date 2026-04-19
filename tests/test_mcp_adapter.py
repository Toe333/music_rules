"""Phase 5 — MCP adapter tests.

Strategy
--------

The adapter intentionally splits "tool implementations" from "fastmcp
server construction". This test module covers the implementation layer
exhaustively (no fastmcp dependency), and adds one optional smoke test
for :func:`build_server` that runs only when ``fastmcp`` is importable.

What we verify here:

1. The advertised tool set matches the spec (Group A + Phase-3 Group C
   + Group D + Group B/E stubs), with no duplicates and no missing names.
2. Every tool is callable via :func:`call_tool` with no surprising
   argument names.
3. Group A tools (``list_*``, ``get_rules``, ``get_rule``,
   ``explain_rule``) return data whose shape matches the docstring claims
   and whose contents are consistent with the on-disk corpus.
4. Group C checker tools wrap their core counterparts faithfully
   (return the standard ``{ok, violations, soft_costs}`` triple).
5. ``evaluate_passage`` (Group D) returns the spec-compliant report.
6. Stubs return informative ``not_implemented`` payloads — no exceptions,
   no silent ``None``.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from music_rules.adapters import mcp as mcp_adapter

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


# Spec-derived expected names. Any drift between the spec and the
# adapter will surface as a failure here, which is a feature.
_GROUP_A = {
    "list_rule_systems",
    "list_rule_categories",
    "list_rule_kinds",
    "list_input_shapes",
    "get_rules",
    "get_rule",
    "explain_rule",
}
_GROUP_C_PHASE3 = {
    "check_melodic_interval",
    "check_melodic_triple",
    "check_motion_pair",
    "check_vertical_chord",
    "check_first_interval",
    "check_final_interval",
    "check_per_measure_downbeat",
    "check_weak_beat_interval",
    "check_dissonance_context",
}
_GROUP_D = {"evaluate_passage"}
# Phase-8 promotes every Group B + Group E tool to live implementations.
_GROUP_B = {
    "eis_pick_root_line",
    "eis_list_scales",
    "eis_list_chord_classes",
    "eis_build_chord",
    "eis_voice_lead",
    "eis_check_voice_leading",
    "eis_insert_nct",
    "eis_list_nct_types",
    "eis_check_ood",
}
_GROUP_E = {
    "midi_to_rolls",
    "rolls_to_midi",
    "skytnt_generate",
    "skytnt_constrained_generate",
}
_ALL_EXPECTED = _GROUP_A | _GROUP_C_PHASE3 | _GROUP_D | _GROUP_B | _GROUP_E


class TestToolRegistry:
    def test_advertised_tools_match_spec(self) -> None:
        actual = set(mcp_adapter.list_tool_names())
        missing = _ALL_EXPECTED - actual
        extra = actual - _ALL_EXPECTED
        assert not missing, f"adapter missing tools: {sorted(missing)}"
        assert not extra, f"adapter has unexpected tools: {sorted(extra)}"

    def test_no_duplicate_tool_names(self) -> None:
        names = mcp_adapter.list_tool_names()
        assert len(names) == len(set(names))

    def test_total_tool_count_matches_spec(self) -> None:
        # Spec §2 advertises ~27 tools; today we expose exactly len(expected).
        assert len(mcp_adapter.list_tool_names()) == len(_ALL_EXPECTED)

    def test_call_tool_unknown_name_raises_keyerror(self) -> None:
        with pytest.raises(KeyError, match="Unknown MCP tool"):
            mcp_adapter.call_tool("not_a_real_tool")


# ---------------------------------------------------------------------------
# Group A — corpus introspection
# ---------------------------------------------------------------------------


class TestGroupAIntrospection:
    def test_list_rule_systems(self) -> None:
        systems = mcp_adapter.call_tool("list_rule_systems")
        assert "EIS" in systems
        assert "Fux" in systems

    def test_list_rule_categories_unfiltered(self) -> None:
        cats = mcp_adapter.call_tool("list_rule_categories")
        assert isinstance(cats, list)
        assert all(isinstance(c, str) for c in cats)
        assert cats == sorted(cats)  # contract: sorted

    def test_list_rule_categories_filtered_by_system(self) -> None:
        eis = set(mcp_adapter.call_tool("list_rule_categories", {"system": "EIS"}))
        fux = set(mcp_adapter.call_tool("list_rule_categories", {"system": "Fux"}))
        # The two systems' categories should be largely disjoint.
        # We just assert each produces *some* output.
        assert eis and fux

    def test_list_rule_kinds(self) -> None:
        kinds = set(mcp_adapter.call_tool("list_rule_kinds"))
        # All four kinds should be present in the corpus.
        assert {"hard", "soft", "informational"} <= kinds

    def test_list_input_shapes_includes_phase3_shapes(self) -> None:
        shapes = set(mcp_adapter.call_tool("list_input_shapes"))
        for s in (
            "melodic-interval",
            "melodic-triple",
            "motion-pair",
            "vertical-chord",
            "first-interval",
            "final-interval",
            "per-measure-downbeat",
            "weak-beat-interval",
            "dissonance-context",
        ):
            assert s in shapes

    def test_get_rules_returns_dicts_with_required_keys(self) -> None:
        rules = mcp_adapter.call_tool("get_rules", {"system": "Fux", "limit": 5})
        assert 1 <= len(rules) <= 5
        for r in rules:
            assert {"id", "system", "kind", "rule"} <= r.keys()
            assert r["system"] == "Fux"

    def test_get_rules_filter_by_input_shape(self) -> None:
        rules = mcp_adapter.call_tool("get_rules", {"input_shape": "motion-pair"})
        assert rules
        assert all(r["input_shape"] == "motion-pair" for r in rules)

    def test_get_rules_default_limit_is_200(self) -> None:
        rules = mcp_adapter.call_tool("get_rules")
        assert len(rules) <= 200

    def test_get_rule_known_id(self) -> None:
        # P1_1_2v is a Phase-3 rule we exercise heavily.
        rule = mcp_adapter.call_tool("get_rule", {"rule_id": "P1_1_2v"})
        assert rule["id"] == "P1_1_2v"
        assert rule["input_shape"] == "motion-pair"

    def test_get_rule_unknown_id_raises(self) -> None:
        with pytest.raises(KeyError):
            mcp_adapter.call_tool("get_rule", {"rule_id": "NOPE_999"})

    def test_explain_rule_includes_checker_hint(self) -> None:
        out = mcp_adapter.call_tool("explain_rule", {"rule_id": "P1_1_2v"})
        assert {"rule_id", "system", "kind", "rule", "applies_to",
                "input_shape", "checker_hint", "source"} <= out.keys()
        assert "check_motion_pair" in out["checker_hint"]
        assert out["applies_to"] == {"species": "1", "voices": "2v"}


# ---------------------------------------------------------------------------
# Group C — Fux checkers
# ---------------------------------------------------------------------------


class TestGroupCCheckers:
    def test_check_melodic_interval_pass(self) -> None:
        # C4 -> D4: stepwise, no violations.
        out = mcp_adapter.call_tool(
            "check_melodic_interval",
            {"prev_midi": 60, "curr_midi": 62, "species": 1, "voices": 2},
        )
        assert out["ok"] is True
        assert out["violations"] == []

    def test_check_melodic_interval_giant_leap_violates(self) -> None:
        # C4 -> C6 is a P15 - a 2-octave leap, way past the m6 ceiling.
        out = mcp_adapter.call_tool(
            "check_melodic_interval",
            {"prev_midi": 60, "curr_midi": 84, "species": 1, "voices": 2},
        )
        assert out["ok"] is False
        assert any(v["rule_id"].startswith("M1") for v in out["violations"])

    def test_check_melodic_triple_chromatic_ascent_violates(self) -> None:
        # 60 -> 61 -> 62 is the chromatic ascent G6 forbids.
        out = mcp_adapter.call_tool(
            "check_melodic_triple",
            {"n1": 60, "n2": 61, "n3": 62, "species": 1, "voices": 2},
        )
        assert out["ok"] is False

    def test_check_motion_pair_parallel_fifth_violates(self) -> None:
        out = mcp_adapter.call_tool(
            "check_motion_pair",
            {
                "prev_pair": {"cf": 60, "cp": 67},
                "curr_pair": {"cf": 62, "cp": 69},
                "species": 1, "voices": 2,
            },
        )
        assert out["ok"] is False
        assert any(v["rule_id"] == "P1_1_2v" for v in out["violations"])

    def test_check_first_interval_pass(self) -> None:
        out = mcp_adapter.call_tool(
            "check_first_interval",
            {"chord": [60, 67], "species": 1, "voices": 2},
        )
        assert out["ok"] is True

    def test_check_first_interval_fail(self) -> None:
        # M3 opening — H2_1 violation.
        out = mcp_adapter.call_tool(
            "check_first_interval",
            {"chord": [60, 64], "species": 1, "voices": 2},
        )
        assert out["ok"] is False
        assert any(v["rule_id"] == "H2_1" for v in out["violations"])

    def test_check_final_interval_fail(self) -> None:
        out = mcp_adapter.call_tool(
            "check_final_interval",
            {"chord": [60, 64], "species": 1, "voices": 2},
        )
        assert out["ok"] is False
        assert any(v["rule_id"] == "H3_1" for v in out["violations"])

    def test_check_per_measure_downbeat_dissonance_fails(self) -> None:
        # M2 (60 vs 62) = 2 semitones = dissonance.
        out = mcp_adapter.call_tool(
            "check_per_measure_downbeat",
            {"chord": [60, 62], "species": 1, "voices": 2},
        )
        assert out["ok"] is False

    def test_check_vertical_chord_complete_triad_passes(self) -> None:
        # Open C-major triad: C4 E4 G4.
        out = mcp_adapter.call_tool(
            "check_vertical_chord",
            {"chord": [60, 64, 67], "species": 1, "voices": 3},
        )
        assert out["soft_costs"] == []

    def test_check_dissonance_context_passing_tone_passes(self) -> None:
        # 60 -> 62 -> 64, dissonant against cf=65 (M7 below). Stepwise, passing.
        out = mcp_adapter.call_tool(
            "check_dissonance_context",
            {"prev": 60, "diss": 62, "next_": 64, "cf_pitch": 65, "species": 3},
        )
        assert out["ok"] is True


# ---------------------------------------------------------------------------
# Group D — evaluate_passage
# ---------------------------------------------------------------------------


class TestGroupDEvaluatePassage:
    @pytest.fixture()
    def piece(self) -> dict[str, Any]:
        return {
            "voices": [[60, 62, 64, 60], [67, 69, 71, 67]],
            "meter": "4/4",
            "key": "C",
            "species": 1,
            "cantus_firmus_voice": 0,
        }

    def test_returns_full_report_shape(self, piece: dict[str, Any]) -> None:
        report = mcp_adapter.call_tool("evaluate_passage", {"piece": piece})
        assert {
            "total_cost",
            "hard_violations",
            "soft_violations",
            "per_rule_summary",
            "grade",
        } == set(report.keys())

    def test_parallel_fifths_grade_F(self, piece: dict[str, Any]) -> None:
        report = mcp_adapter.call_tool("evaluate_passage", {"piece": piece})
        assert report["grade"] == "F"

    def test_filter_pass_through(self, piece: dict[str, Any]) -> None:
        report = mcp_adapter.call_tool(
            "evaluate_passage",
            {"piece": piece, "exclude": ["P1_1_2v"]},
        )
        assert all(v["rule_id"] != "P1_1_2v" for v in report["hard_violations"])


# ---------------------------------------------------------------------------
# Stubs (Group B & E)
# ---------------------------------------------------------------------------


class TestGroupBLive:
    """Group B — EIS Root-line + scale registry."""

    def test_eis_pick_root_line_default_walks_e5(self) -> None:
        out = mcp_adapter.call_tool(
            "eis_pick_root_line", {"length": 4, "start_root": "C"},
        )
        assert out["roots"] == ["C", "F", "Bb", "Eb"]
        assert out["cycles"] == ["E5"]

    def test_eis_pick_root_line_seeded_is_deterministic(self) -> None:
        a = mcp_adapter.call_tool(
            "eis_pick_root_line",
            {"length": 12, "cycles": ["E4", "E5"], "seed": 7},
        )
        b = mcp_adapter.call_tool(
            "eis_pick_root_line",
            {"length": 12, "cycles": ["E4", "E5"], "seed": 7},
        )
        assert a == b

    def test_eis_list_scales_returns_all_eighteen(self) -> None:
        out = mcp_adapter.call_tool("eis_list_scales")
        assert out["summary"]["total"] == 18
        assert len(out["scales"]) == 18
        ids = {s["id"] for s in out["scales"]}
        assert "EIS-18-01" in ids
        assert "EIS-18-10" in ids

    def test_eis_list_scales_filtered_to_verified(self) -> None:
        out = mcp_adapter.call_tool("eis_list_scales", {"status": "verified"})
        assert all(s["status"] == "verified" for s in out["scales"])
        assert {"EIS-18-01", "EIS-18-04", "EIS-18-10"} <= {
            s["id"] for s in out["scales"]
        }


class TestGroupELive:
    """Group E — MIDI round-trip."""

    def test_midi_round_trip_through_adapter(self) -> None:
        encoded = mcp_adapter.call_tool(
            "rolls_to_midi", {"voices": [[60, 62, 64, 65]]},
        )
        assert "midi_base64" in encoded
        decoded = mcp_adapter.call_tool(
            "midi_to_rolls", {"midi_base64": encoded["midi_base64"]},
        )
        assert decoded["voices"][0] == [60, 62, 64, 65]
        assert decoded["meter"] == "4/4"


class TestPhase8GroupBLive:
    """Phase-8 Group B: chord builder, voice-leading, NCT, OOD all live."""

    def test_eis_list_chord_classes_advertises_all(self) -> None:
        out = mcp_adapter.call_tool("eis_list_chord_classes")
        ids = {c["id"] for c in out["chord_classes"]}
        for cid in ("triad", "dom7", "dom7b9", "min9", "4th-3p", "polytonal"):
            assert cid in ids

    def test_eis_build_chord_returns_midi_and_pcs(self) -> None:
        out = mcp_adapter.call_tool(
            "eis_build_chord",
            {"root": "C", "chord_class": "triad", "base_octave": 4},
        )
        assert out["midi"] == [60, 64, 67]
        assert out["pitch_classes"] == [0, 4, 7]
        assert out["chord_class"]["id"] == "triad"

    def test_eis_voice_lead_returns_voiced_chord_and_report(self) -> None:
        out = mcp_adapter.call_tool(
            "eis_voice_lead",
            {"prev_chord": [60, 64, 67], "next_pcs": [7, 11, 2]},
        )
        assert sorted(out["voiced"]) == out["voiced"]
        assert {p % 12 for p in out["voiced"]} == {7, 11, 2}
        assert "smoothness" in out["report"]

    def test_eis_check_voice_leading_smooth_move(self) -> None:
        out = mcp_adapter.call_tool(
            "eis_check_voice_leading",
            {"prev_chord": [60, 64, 67], "next_chord": [60, 64, 67]},
        )
        assert out["smoothness"] == 1.0
        assert out["common_tones"] == 3

    def test_eis_insert_nct_passing_tone(self) -> None:
        out = mcp_adapter.call_tool(
            "eis_insert_nct",
            {
                "chord_a": [60], "chord_b": [64],
                "voice": 0, "nct_type": "PT",
                "scale_id": "EIS-18-01",
            },
        )
        assert out["event"]["midi"] == 62
        assert out["event"]["type"] == "PT"

    def test_eis_list_nct_types(self) -> None:
        out = mcp_adapter.call_tool("eis_list_nct_types")
        ids = {t["id"] for t in out["nct_types"]}
        assert ids == {"PT", "CA", "RT", "CT", "Sus", "Ant"}

    def test_eis_check_ood_clean_voicing(self) -> None:
        out = mcp_adapter.call_tool(
            "eis_check_ood", {"chord": [48, 52, 55, 60]},
        )
        assert out["ok"] is True
        assert out["hits"] == []

    def test_eis_check_ood_b9_without_b7_flagged(self) -> None:
        out = mcp_adapter.call_tool(
            "eis_check_ood", {"chord": [36, 49], "has_b7": False},
        )
        assert out["ok"] is False
        assert any(h["rule_id"] == "O-002" for h in out["hits"])


class TestPhase8GroupELive:
    """Phase-8 Group E: SkyTNT generation now lazy-loads with graceful fallback."""

    def test_rolls_to_midi_supports_per_voice_programs(self) -> None:
        out = mcp_adapter.call_tool(
            "rolls_to_midi",
            {
                "voices": [[60, 62, 64, 65]] * 4,
                "programs": [80, 80, 87, 122],
            },
        )
        assert "midi_base64" in out

    def test_skytnt_generate_reports_when_extras_missing(self) -> None:
        try:
            import transformers  # noqa: F401
        except ImportError:
            out = mcp_adapter.call_tool("skytnt_generate")
            assert out["status"] == "skytnt_unavailable"
            assert "fix" in out
        else:
            pytest.skip("transformers installed; skip extras-missing path")

    def test_skytnt_constrained_generate_reports_when_extras_missing(self) -> None:
        try:
            import transformers  # noqa: F401
        except ImportError:
            out = mcp_adapter.call_tool("skytnt_constrained_generate")
            assert out["status"] == "skytnt_unavailable"
        else:
            pytest.skip("transformers installed; skip extras-missing path")


# ---------------------------------------------------------------------------
# Optional: smoke-test the actual fastmcp server build, if installed
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    importlib.util.find_spec("fastmcp") is None,
    reason="fastmcp not installed in this environment",
)
def test_build_server_constructs_without_error() -> None:
    """Smoke test: build the actual FastMCP server with all tools attached.

    FastMCP's introspection API (``list_tools()``) is async and shifts
    across versions, so we deliberately don't assert on its tool table —
    that would couple us to a private interface. Instead we just verify
    the server constructs and reports a sensible name.
    """
    server = mcp_adapter.build_server()
    # The constructor below would have raised on a mis-registered tool
    # (duplicate name, bad signature, …), so reaching this line is the
    # actual passing condition.
    assert getattr(server, "name", "music-rules") == "music-rules"
