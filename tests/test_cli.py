"""Phase 6 — Typer CLI tests.

Uses Typer's :class:`CliRunner` (Click's test client under the hood)
to invoke the ``music-rules`` app in-process and assert on exit code +
captured stdout.

Coverage:

* ``music-rules version``                       — smoke
* ``music-rules rules list``                    — table & JSON modes, filters
* ``music-rules rules show <id>``               — known + unknown IDs
* ``music-rules rules search <text>``           — substring matching
* ``music-rules evaluate <piece.json>``         — passing + failing pieces
* ``music-rules tools list`` / ``tools schema`` — registry mirror
* Exit-code semantics (1 for hard violations, 2 for user errors)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from music_rules.adapters import cli as cli_module

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def clean_piece(tmp_path: Path) -> Path:
    """A 7-note 2v 1st-species clean passage (the one from fux_passages.py)."""
    piece = {
        "voices": [
            [60, 62, 64, 65, 64, 62, 60],
            [67, 65, 67, 69, 67, 65, 67],
        ],
        "meter": "4/4",
        "key": "C",
        "species": 1,
        "cantus_firmus_voice": 0,
    }
    p = tmp_path / "clean.json"
    p.write_text(json.dumps(piece))
    return p


@pytest.fixture()
def parallel_fifths_piece(tmp_path: Path) -> Path:
    """The textbook parallel-fifths failure fixture."""
    piece = {
        "voices": [
            [60, 62, 64, 60, 62, 60],
            [67, 69, 71, 67, 69, 67],
        ],
        "species": 1,
        "cantus_firmus_voice": 0,
    }
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(piece))
    return p


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


class TestVersion:
    def test_version_prints_and_exits_zero(self) -> None:
        result = runner.invoke(cli_module.app, ["version"])
        assert result.exit_code == 0
        assert result.stdout.strip()  # some non-empty version string


# ---------------------------------------------------------------------------
# rules list / show / search
# ---------------------------------------------------------------------------


class TestRulesList:
    def test_table_mode_shows_some_rules(self) -> None:
        result = runner.invoke(cli_module.app, ["rules", "list", "--limit", "5"])
        assert result.exit_code == 0
        assert "ID" in result.stdout
        assert "rule(s) shown" in result.stdout

    def test_filter_by_system(self) -> None:
        result = runner.invoke(
            cli_module.app, ["rules", "list", "--system", "Fux", "--limit", "10"]
        )
        assert result.exit_code == 0
        # All listed rules should be Fux.
        for line in result.stdout.splitlines():
            if line and not line.startswith(("ID", "-", "\n")) and "rule(s) shown" not in line:
                # crude: look for " Fux " in the row
                if " Fux " in line or line.endswith("Fux"):
                    continue
        # Easier: re-run with --json and check.
        result = runner.invoke(
            cli_module.app, ["rules", "list", "--system", "Fux", "--limit", "10", "--json"]
        )
        rules = json.loads(result.stdout)
        assert all(r["system"] == "Fux" for r in rules)

    def test_json_mode_produces_valid_json(self) -> None:
        result = runner.invoke(cli_module.app, ["rules", "list", "--limit", "3", "--json"])
        assert result.exit_code == 0
        rules = json.loads(result.stdout)
        assert isinstance(rules, list)
        assert len(rules) <= 3
        assert {"id", "system", "kind"} <= rules[0].keys()

    def test_no_matches_message(self) -> None:
        # No rules use this exotic combination today.
        result = runner.invoke(cli_module.app, ["rules", "list", "--input-shape", "no-such-shape"])
        assert result.exit_code == 0
        assert "No rules matched" in result.stdout


class TestRulesShow:
    def test_known_rule(self) -> None:
        result = runner.invoke(cli_module.app, ["rules", "show", "P1_1_2v"])
        assert result.exit_code == 0
        assert "P1_1_2v" in result.stdout
        assert "Fux" in result.stdout

    def test_unknown_rule_exits_2(self) -> None:
        result = runner.invoke(cli_module.app, ["rules", "show", "DOES_NOT_EXIST"])
        assert result.exit_code == 2
        assert "Unknown rule" in result.stderr or "Unknown rule" in result.output

    def test_json_mode(self) -> None:
        result = runner.invoke(cli_module.app, ["rules", "show", "P1_1_2v", "--json"])
        assert result.exit_code == 0
        rule = json.loads(result.stdout)
        assert rule["id"] == "P1_1_2v"
        assert rule["input_shape"] == "motion-pair"


class TestRulesSearch:
    def test_finds_matches(self) -> None:
        result = runner.invoke(cli_module.app, ["rules", "search", "parallel"])
        assert result.exit_code == 0
        # P1_* rules contain "parallel" in their statements.
        assert "matched" in result.stdout

    def test_no_matches(self) -> None:
        result = runner.invoke(cli_module.app, ["rules", "search", "zzzzz_no_such_text"])
        assert result.exit_code == 0
        assert "No rules contain" in result.stdout


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


class TestEvaluate:
    def test_clean_piece_exit_zero(self, clean_piece: Path) -> None:
        result = runner.invoke(cli_module.app, ["evaluate", str(clean_piece)])
        assert result.exit_code == 0
        assert "grade:" in result.stdout
        # No HARD section header since hard_violations is empty.
        assert "HARD violations" not in result.stdout

    def test_failing_piece_exit_one_and_lists_violations(self, parallel_fifths_piece: Path) -> None:
        result = runner.invoke(cli_module.app, ["evaluate", str(parallel_fifths_piece)])
        assert result.exit_code == 1
        assert "HARD violations" in result.stdout
        assert "P1_1_2v" in result.stdout
        assert "F" in result.stdout

    def test_json_mode_returns_full_report(self, parallel_fifths_piece: Path) -> None:
        result = runner.invoke(cli_module.app, ["evaluate", str(parallel_fifths_piece), "--json"])
        # Even with hard violations, --json should still emit JSON to stdout.
        # We may exit 1 (because of violations) but stdout must parse.
        assert result.exit_code in (0, 1)
        report = json.loads(result.stdout)
        assert {"total_cost", "hard_violations", "grade"} <= report.keys()

    def test_exclude_filter(self, parallel_fifths_piece: Path) -> None:
        result = runner.invoke(
            cli_module.app,
            [
                "evaluate",
                str(parallel_fifths_piece),
                "--exclude",
                "P1_1_2v",
                "--json",
            ],
        )
        report = json.loads(result.stdout)
        assert all(v["rule_id"] != "P1_1_2v" for v in report["hard_violations"])

    def test_missing_file_exits_2(self, tmp_path: Path) -> None:
        result = runner.invoke(cli_module.app, ["evaluate", str(tmp_path / "nope.json")])
        assert result.exit_code == 2

    def test_invalid_json_exits_2(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not json {")
        result = runner.invoke(cli_module.app, ["evaluate", str(bad)])
        assert result.exit_code == 2

    def test_invalid_piece_shape_exits_2(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad-piece.json"
        bad.write_text(json.dumps({"voices": [[60, 62, 64], [67, 69]]}))
        result = runner.invoke(cli_module.app, ["evaluate", str(bad)])
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# tools list / schema
# ---------------------------------------------------------------------------


class TestToolsCommands:
    def test_tools_list(self) -> None:
        result = runner.invoke(cli_module.app, ["tools", "list"])
        assert result.exit_code == 0
        assert "evaluate_passage" in result.stdout
        assert "list_rule_systems" in result.stdout

    def test_tools_list_json(self) -> None:
        result = runner.invoke(cli_module.app, ["tools", "list", "--json"])
        names = json.loads(result.stdout)
        assert "evaluate_passage" in names

    def test_tools_schema_full(self) -> None:
        result = runner.invoke(cli_module.app, ["tools", "schema"])
        assert result.exit_code == 0
        schemas = json.loads(result.stdout)
        assert isinstance(schemas, list)
        assert all(s["type"] == "function" for s in schemas)

    def test_tools_schema_single(self) -> None:
        result = runner.invoke(cli_module.app, ["tools", "schema", "--name", "evaluate_passage"])
        assert result.exit_code == 0
        s = json.loads(result.stdout)
        assert s["function"]["name"] == "evaluate_passage"

    def test_tools_schema_unknown(self) -> None:
        result = runner.invoke(cli_module.app, ["tools", "schema", "--name", "nope"])
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def test_main_returns_int() -> None:
    code = cli_module.main(["version"])
    assert code == 0
