"""Phase 6 — OpenAI function-calling adapter tests.

Verifies:

1. The schema has one entry per registered MCP tool.
2. Every entry conforms to OpenAI's function-calling top-level shape.
3. Type-annotation → JSON Schema conversion handles every annotation
   the tool surface uses today (primitives, lists, dicts, unions,
   ``None``, ``Literal``).
4. ``required`` is computed correctly from default-less parameters.
5. ``dispatch`` round-trips through to the MCP tool registry.
6. The schemas validate as parseable JSON Schema (we use ``jsonschema``
   to verify each parameters block is itself a valid Draft 2020-12
   schema).
"""

from __future__ import annotations

import json
from typing import Any, Literal

import jsonschema
import pytest

from music_rules.adapters import mcp as mcp_adapter
from music_rules.adapters import openai as openai_adapter

# ---------------------------------------------------------------------------
# Catalogue completeness
# ---------------------------------------------------------------------------


class TestSchemaCatalogue:
    def test_one_schema_per_mcp_tool(self) -> None:
        schemas = openai_adapter.get_tools_schema()
        names_from_schema = [s["function"]["name"] for s in schemas]
        assert names_from_schema == mcp_adapter.list_tool_names()

    def test_every_schema_has_required_top_level_keys(self) -> None:
        for s in openai_adapter.get_tools_schema():
            assert s["type"] == "function"
            assert "function" in s
            f = s["function"]
            assert {"name", "description", "parameters"} <= f.keys()
            assert isinstance(f["name"], str) and f["name"]
            assert f["parameters"]["type"] == "object"
            assert "properties" in f["parameters"]

    def test_descriptions_are_nonempty_for_real_tools(self) -> None:
        # Every Phase-3/4/5 tool has a docstring; stubs do too.
        for s in openai_adapter.get_tools_schema():
            assert s["function"]["description"], (
                f"empty description for tool {s['function']['name']!r}"
            )

    def test_schemas_are_json_serializable(self) -> None:
        json.dumps(openai_adapter.get_tools_schema())

    def test_schema_parameters_are_valid_jsonschema(self) -> None:
        # Every parameters block should itself parse as a Draft 2020-12
        # JSON Schema. Catches typos like "tpe" instead of "type".
        validator_cls = jsonschema.validators.Draft202012Validator
        for s in openai_adapter.get_tools_schema():
            params = s["function"]["parameters"]
            try:
                validator_cls.check_schema(params)
            except jsonschema.exceptions.SchemaError as exc:
                pytest.fail(f"invalid schema for tool {s['function']['name']!r}: {exc.message}")


# ---------------------------------------------------------------------------
# get_tool_schema (single tool)
# ---------------------------------------------------------------------------


class TestSingleSchema:
    def test_known_tool(self) -> None:
        s = openai_adapter.get_tool_schema("evaluate_passage")
        assert s["function"]["name"] == "evaluate_passage"
        # `piece` is a required dict argument.
        params = s["function"]["parameters"]
        assert "piece" in params["properties"]
        assert "piece" in params.get("required", [])

    def test_unknown_tool_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown tool"):
            openai_adapter.get_tool_schema("nope")


# ---------------------------------------------------------------------------
# Specific schema correctness for representative tools
# ---------------------------------------------------------------------------


class TestRepresentativeSchemas:
    def test_check_motion_pair_schema(self) -> None:
        s = openai_adapter.get_tool_schema("check_motion_pair")
        params = s["function"]["parameters"]
        props = params["properties"]
        assert props["prev_pair"]["type"] == "object"
        assert props["curr_pair"]["type"] == "object"
        # species and voices accept int OR string → union.
        species_schema = props["species"]
        assert species_schema.get("default") == 1
        # The type is either a list ["integer", "string"] or anyOf.
        assert (
            species_schema.get("type")
            in (
                ["integer", "string"],
                "integer",
                "string",
            )
            or "anyOf" in species_schema
        )
        # `strict` is an optional bool default False.
        assert props["strict"]["type"] == "boolean"
        assert props["strict"]["default"] is False
        # No required params (all have defaults except prev_pair / curr_pair).
        required = set(params.get("required", []))
        assert {"prev_pair", "curr_pair"} <= required
        assert "strict" not in required
        assert "species" not in required

    def test_check_melodic_interval_schema(self) -> None:
        s = openai_adapter.get_tool_schema("check_melodic_interval")
        params = s["function"]["parameters"]
        assert params["properties"]["prev_midi"]["type"] == "integer"
        assert params["properties"]["curr_midi"]["type"] == "integer"
        assert "prev_midi" in params["required"]
        assert "curr_midi" in params["required"]

    def test_get_rules_schema_has_optional_filters(self) -> None:
        s = openai_adapter.get_tool_schema("get_rules")
        params = s["function"]["parameters"]
        # `system` accepts string | None
        sys_schema = params["properties"]["system"]
        assert sys_schema.get("default") is None
        # All filters are optional → required should be empty or omitted.
        assert not params.get("required")

    def test_evaluate_passage_includes_list_filters(self) -> None:
        s = openai_adapter.get_tool_schema("evaluate_passage")
        props = s["function"]["parameters"]["properties"]
        for k in ("piece", "ruleset", "strict", "include", "exclude"):
            assert k in props
        # include/exclude default to None and accept list[str] | None.
        assert props["include"].get("default") is None
        # Should describe a list type somewhere in its schema.
        assert props["include"].get("type") == "array" or any(
            "array" in str(t) for t in props["include"].get("anyOf", [])
        )

    def test_list_rule_systems_takes_no_args(self) -> None:
        s = openai_adapter.get_tool_schema("list_rule_systems")
        params = s["function"]["parameters"]
        assert params["properties"] == {}
        assert not params.get("required")


# ---------------------------------------------------------------------------
# Type-annotation → JSON Schema converter (white-box)
# ---------------------------------------------------------------------------


class TestAnnotationConverter:
    def test_int(self) -> None:
        assert openai_adapter._annotation_to_jsonschema(int) == {"type": "integer"}

    def test_str(self) -> None:
        assert openai_adapter._annotation_to_jsonschema(str) == {"type": "string"}

    def test_optional_int(self) -> None:
        out = openai_adapter._annotation_to_jsonschema(int | None)
        assert out == {"type": ["integer", "null"]}

    def test_union_int_str(self) -> None:
        out = openai_adapter._annotation_to_jsonschema(int | str)
        assert out == {"type": ["integer", "string"]}

    def test_list_of_int(self) -> None:
        out = openai_adapter._annotation_to_jsonschema(list[int])
        assert out == {"type": "array", "items": {"type": "integer"}}

    def test_dict_str_int(self) -> None:
        out = openai_adapter._annotation_to_jsonschema(dict[str, int])
        assert out == {
            "type": "object",
            "additionalProperties": {"type": "integer"},
        }

    def test_literal_strings(self) -> None:
        out = openai_adapter._annotation_to_jsonschema(Literal["Fux", "EIS", "both"])
        assert out["type"] == "string"
        assert sorted(out["enum"]) == ["EIS", "Fux", "both"]

    def test_any_returns_empty(self) -> None:
        assert openai_adapter._annotation_to_jsonschema(Any) == {}


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_dispatch_routes_through_mcp_registry(self) -> None:
        out = openai_adapter.dispatch("list_rule_systems")
        assert "Fux" in out and "EIS" in out

    def test_dispatch_with_arguments(self) -> None:
        out = openai_adapter.dispatch(
            "check_motion_pair",
            {
                "prev_pair": {"cf": 60, "cp": 67},
                "curr_pair": {"cf": 62, "cp": 69},
                "species": 1,
                "voices": 2,
            },
        )
        assert out["ok"] is False  # parallel 5ths

    def test_dispatch_unknown_tool_raises_keyerror(self) -> None:
        with pytest.raises(KeyError, match="Unknown MCP tool"):
            openai_adapter.dispatch("not_a_tool")

    def test_dispatch_bad_args_raises_typeerror(self) -> None:
        with pytest.raises(TypeError):
            openai_adapter.dispatch("check_melodic_interval", {"WRONG": 60})

    def test_dispatch_evaluate_passage_returns_full_report(self) -> None:
        out = openai_adapter.dispatch(
            "evaluate_passage",
            {
                "piece": {
                    "voices": [[60, 62], [67, 69]],
                    "species": 1,
                    "cantus_firmus_voice": 0,
                }
            },
        )
        assert {
            "total_cost",
            "hard_violations",
            "soft_violations",
            "per_rule_summary",
            "grade",
        } == set(out.keys())


# ---------------------------------------------------------------------------
# list_tool_names mirror
# ---------------------------------------------------------------------------


def test_list_tool_names_mirrors_mcp() -> None:
    assert openai_adapter.list_tool_names() == mcp_adapter.list_tool_names()
