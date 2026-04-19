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
from collections.abc import Iterator
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
_GROUP_B_STUBS = {
    "eis_pick_root_line",
    "eis_list_scales",
    "eis_build_chord",
    "eis_voice_lead",
    "eis_insert_nct",
    "eis_check_ood",
}
_GROUP_E_STUBS = {
    "skytnt_generate",
    "skytnt_constrained_generate",
    "midi_to_rolls",
    "rolls_to_midi",
}
_ALL_EXPECTED = _GROUP_A | _GROUP_C_PHASE3 | _GROUP_D | _GROUP_B_STUBS | _GROUP_E_STUBS


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


class TestPhase7Stubs:
    @pytest.fixture(params=sorted(_GROUP_B_STUBS | _GROUP_E_STUBS))
    def stub_call(self, request: pytest.FixtureRequest) -> Iterator[tuple[str, dict]]:
        # Minimum viable args per stub so we can call them all uniformly.
        # All keyword-only; the stubs don't actually use the values.
        sample_args: dict[str, dict[str, Any]] = {
            "eis_pick_root_line": {"length": 8, "cycles": ["E5"]},
            "eis_list_scales": {},
            "eis_build_chord": {
                "root": "C", "scale_id": "EIS-18-03",
                "chord_class": "triad-close", "parts": 4,
            },
            "eis_voice_lead": {"prev_chord": [60, 64, 67], "next_chord": [62, 65, 69]},
            "eis_insert_nct": {"voice": [60, 62, 64], "nct_type": "PT", "beat": 0.5},
            "eis_check_ood": {"chord": [60, 64, 67]},
            "skytnt_generate": {},
            "skytnt_constrained_generate": {},
            "midi_to_rolls": {"midi_base64": "TVRoZA=="},
            "rolls_to_midi": {"voices": [[60, 62, 64]]},
        }
        yield request.param, sample_args[request.param]

    def test_stub_returns_not_implemented_payload(
        self, stub_call: tuple[str, dict[str, Any]]
    ) -> None:
        name, args = stub_call
        out = mcp_adapter.call_tool(name, args)
        assert out["status"] == "not_implemented"
        assert out["tool"] == name
        assert "Phase 7" in out["available_in"]


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
