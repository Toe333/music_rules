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


class TestEvaluateExplain:
    def test_evaluate_explain_text(self, tmp_path: Path) -> None:
        report = {
            "total_cost": 2.0,
            "hard_violations": [{"rule_id": "P1_1_2v", "position": 1, "voices_involved": [0, 1], "msg": "x"}],
            "soft_violations": [
                {"rule_id": "G4", "position": 1, "cost": 1.5, "msg": "x"},
                {"rule_id": "G4", "position": 2, "cost": 0.5, "msg": "x"},
            ],
            "per_rule_summary": {},
            "grade": "D",
        }
        p = tmp_path / "report.json"
        p.write_text(json.dumps(report), encoding="utf-8")
        result = runner.invoke(cli_module.app, ["evaluate-explain", str(p)])
        assert result.exit_code == 0
        assert "Top hard-rule hits" in result.stdout
        assert "P1_1_2v" in result.stdout
        assert "G4" in result.stdout

    def test_evaluate_explain_json(self, tmp_path: Path) -> None:
        report = {
            "total_cost": 0.0,
            "hard_violations": [],
            "soft_violations": [],
            "per_rule_summary": {},
            "grade": "A",
        }
        p = tmp_path / "report.json"
        p.write_text(json.dumps(report), encoding="utf-8")
        result = runner.invoke(cli_module.app, ["evaluate-explain", str(p), "--json"])
        assert result.exit_code == 0
        summary = json.loads(result.stdout)
        assert summary["grade"] == "A"
        assert summary["hard_count"] == 0

    def test_evaluate_explain_bad_json_exits_2(self, tmp_path: Path) -> None:
        p = tmp_path / "bad-report.json"
        p.write_text("not-json", encoding="utf-8")
        result = runner.invoke(cli_module.app, ["evaluate-explain", str(p)])
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


class TestProgressionRenderCsv:
    def test_render_csv_writes_midi(self, tmp_path: Path) -> None:
        lex = tmp_path / "lex.json"
        prog = tmp_path / "prog.csv"
        out = tmp_path / "out.mid"
        lex.write_text(
            json.dumps(
                {
                    "chords": {
                        "Cmaj7": {"midi": [60, 64, 67, 71]},
                        "Fmaj7": {"midi": [65, 69, 72, 76]},
                    }
                }
            ),
            encoding="utf-8",
        )
        prog.write_text(
            "bar,start_beat,duration_beats,chord_symbol\n"
            "1,0,1,Cmaj7\n"
            "1,1,1,Fmaj7\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            cli_module.app,
            ["progression", "render-csv", str(prog), str(lex), str(out)],
        )
        assert result.exit_code == 0
        assert out.exists()
        assert out.stat().st_size > 0

    def test_render_csv_strict_missing_exits_2(self, tmp_path: Path) -> None:
        lex = tmp_path / "lex.json"
        prog = tmp_path / "prog.csv"
        out = tmp_path / "out.mid"
        lex.write_text(json.dumps({"chords": {"Cmaj7": {"midi": [60, 64, 67, 71]}}}), encoding="utf-8")
        prog.write_text(
            "bar,start_beat,duration_beats,chord_symbol\n"
            "1,0,1,Cmaj7\n"
            "1,1,1,NOPE\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            cli_module.app,
            ["progression", "render-csv", str(prog), str(lex), str(out)],
        )
        assert result.exit_code == 2


class TestProgressionRenderVoicedCsv:
    def test_render_voiced_csv_writes_midi(self, tmp_path: Path) -> None:
        voiced = tmp_path / "voiced.csv"
        out = tmp_path / "voiced.mid"
        voiced.write_text(
            "kind,cycle,bar,root,chord_midis,chord_notes,melody_qn_midis,melody_qn_notes\n"
            "E3,E3,1,C,48|52|55|59,C3|E3|G3|B3,59|60|62|62,B3|C4|D4|D4\n"
            "E3,E3,2,D#,46|51|55|62,Bb2|Eb3|G3|D4,62|61|61|61,D4|C#4|C#4|C#4\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            cli_module.app,
            ["progression", "render-voiced-csv", str(voiced), str(out)],
        )
        assert result.exit_code == 0
        assert out.exists()
        assert out.stat().st_size > 0

    def test_render_voiced_csv_melody_count_mismatch_exits_2(self, tmp_path: Path) -> None:
        voiced = tmp_path / "voiced.csv"
        out = tmp_path / "voiced.mid"
        voiced.write_text(
            "bar,chord_midis,melody_qn_midis\n"
            "1,48|52|55|59,59|60|62\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            cli_module.app,
            ["progression", "render-voiced-csv", str(voiced), str(out)],
        )
        assert result.exit_code == 2


class TestProgressionRenderVoicedBatch:
    def test_render_voiced_batch_writes_multiple_midis(self, tmp_path: Path) -> None:
        a = tmp_path / "eis_e3_harmonized.csv"
        b = tmp_path / "eis_e4_harmonized.csv"
        out_dir = tmp_path / "out"
        payload = (
            "bar,chord_midis,melody_qn_midis\n"
            "1,48|52|55|59,59|60|62|62\n"
            "2,46|51|55|62,62|61|61|61\n"
        )
        a.write_text(payload, encoding="utf-8")
        b.write_text(payload, encoding="utf-8")

        result = runner.invoke(
            cli_module.app,
            [
                "progression",
                "render-voiced-batch",
                str(tmp_path / "eis_*_harmonized.csv"),
                "--out-dir",
                str(out_dir),
            ],
        )
        assert result.exit_code == 0
        assert (out_dir / "eis_e3_harmonized_cli.mid").exists()
        assert (out_dir / "eis_e4_harmonized_cli.mid").exists()

    def test_render_voiced_batch_no_matches_exits_2(self, tmp_path: Path) -> None:
        result = runner.invoke(
            cli_module.app,
            ["progression", "render-voiced-batch", str(tmp_path / "nope_*.csv")],
        )
        assert result.exit_code == 2


class TestProgressionAuditVoicedCsv:
    def test_audit_voiced_csv_prints_summary(self, tmp_path: Path) -> None:
        voiced = tmp_path / "voiced.csv"
        voiced.write_text(
            "bar,chord_midis,melody_qn_midis\n"
            "1,48|52|55|59,59|60|62|62\n"
            "2,46|51|55|62,62|61|61|61\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            cli_module.app,
            ["progression", "audit-voiced-csv", str(voiced), "--ruleset", "EIS"],
        )
        assert result.exit_code == 0
        assert "grade=" in result.stdout

    def test_audit_voiced_csv_report_out_json(self, tmp_path: Path) -> None:
        voiced = tmp_path / "voiced.csv"
        out = tmp_path / "report.json"
        voiced.write_text(
            "bar,chord_midis,melody_qn_midis\n"
            "1,48|52|55|59,59|60|62|62\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            cli_module.app,
            [
                "progression",
                "audit-voiced-csv",
                str(voiced),
                "--ruleset",
                "EIS",
                "--report-out",
                str(out),
                "--json",
            ],
        )
        assert result.exit_code == 0
        assert out.exists()
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert "grade" in payload

    def test_audit_voiced_csv_min_grade_gate_exits_1(self, tmp_path: Path) -> None:
        voiced = tmp_path / "voiced.csv"
        voiced.write_text(
            "bar,chord_midis,melody_qn_midis\n"
            "1,48|52|55|59,59|60|62|62\n"
            "2,46|51|55|62,62|61|61|61\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            cli_module.app,
            ["progression", "audit-voiced-csv", str(voiced), "--ruleset", "EIS", "--min-grade", "A"],
        )
        assert result.exit_code == 1

    def test_audit_voiced_csv_fail_on_rule_exits_1(self, tmp_path: Path) -> None:
        voiced = tmp_path / "voiced.csv"
        voiced.write_text(
            "bar,chord_midis,melody_qn_midis\n"
            "1,48|52|55|59,59|60|62|62\n"
            "2,46|51|55|62,62|61|61|61\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            cli_module.app,
            [
                "progression",
                "audit-voiced-csv",
                str(voiced),
                "--ruleset",
                "EIS",
                "--fail-on-rule",
                "O-004",
            ],
        )
        assert result.exit_code == 1


class TestProgressionAuditVoicedBatch:
    def test_audit_voiced_batch_writes_summary(self, tmp_path: Path) -> None:
        a = tmp_path / "eis_e3_harmonized.csv"
        b = tmp_path / "eis_e4_harmonized.csv"
        summary = tmp_path / "summary.json"
        payload = (
            "bar,chord_midis,melody_qn_midis\n"
            "1,48|52|55|59,59|60|62|62\n"
            "2,46|51|55|62,62|61|61|61\n"
        )
        a.write_text(payload, encoding="utf-8")
        b.write_text(payload, encoding="utf-8")
        result = runner.invoke(
            cli_module.app,
            [
                "progression",
                "audit-voiced-batch",
                str(tmp_path / "eis_*_harmonized.csv"),
                "--ruleset",
                "EIS",
                "--summary-out",
                str(summary),
            ],
        )
        assert result.exit_code == 0
        assert summary.exists()
        bundle = json.loads(summary.read_text(encoding="utf-8"))
        assert len(bundle["items"]) == 2
        assert bundle["ruleset"] == "EIS"
        assert "top_soft_rules" in bundle["items"][0]

    def test_audit_voiced_batch_json_stdout(self, tmp_path: Path) -> None:
        a = tmp_path / "eis_e3_harmonized.csv"
        payload = (
            "bar,chord_midis,melody_qn_midis\n"
            "1,48|52|55|59,59|60|62|62\n"
            "2,46|51|55|62,62|61|61|61\n"
        )
        a.write_text(payload, encoding="utf-8")
        result = runner.invoke(
            cli_module.app,
            [
                "progression",
                "audit-voiced-batch",
                str(tmp_path / "eis_*_harmonized.csv"),
                "--ruleset",
                "EIS",
                "--json",
            ],
        )
        assert result.exit_code == 0
        bundle = json.loads(result.stdout)
        assert bundle["file_count"] == 1

    def test_audit_voiced_batch_quality_failure_sets_exit_1(self, tmp_path: Path) -> None:
        a = tmp_path / "eis_e3_harmonized.csv"
        payload = (
            "bar,chord_midis,melody_qn_midis\n"
            "1,48|52|55|59,59|60|62|62\n"
            "2,46|51|55|62,62|61|61|61\n"
        )
        a.write_text(payload, encoding="utf-8")
        result = runner.invoke(
            cli_module.app,
            [
                "progression",
                "audit-voiced-batch",
                str(tmp_path / "eis_*_harmonized.csv"),
                "--ruleset",
                "EIS",
                "--min-grade",
                "A",
                "--json",
            ],
        )
        assert result.exit_code == 1
        bundle = json.loads(result.stdout)
        assert bundle["quality_failures"] == 1

    def test_audit_voiced_batch_rule_cost_cap_sets_exit_1(self, tmp_path: Path) -> None:
        a = tmp_path / "eis_e3_harmonized.csv"
        payload = (
            "bar,chord_midis,melody_qn_midis\n"
            "1,48|52|55|59,59|60|62|62\n"
            "2,46|51|55|62,62|61|61|61\n"
        )
        a.write_text(payload, encoding="utf-8")
        result = runner.invoke(
            cli_module.app,
            [
                "progression",
                "audit-voiced-batch",
                str(tmp_path / "eis_*_harmonized.csv"),
                "--ruleset",
                "EIS",
                "--max-rule-total-cost",
                "O-004=1.0",
                "--json",
            ],
        )
        assert result.exit_code == 1
        bundle = json.loads(result.stdout)
        assert bundle["quality_failures"] == 1

    def test_audit_voiced_batch_invalid_rule_cost_arg_exits_2(self, tmp_path: Path) -> None:
        a = tmp_path / "eis_e3_harmonized.csv"
        a.write_text("bar,chord_midis,melody_qn_midis\n1,48|52|55|59,59|60|62|62\n", encoding="utf-8")
        result = runner.invoke(
            cli_module.app,
            [
                "progression",
                "audit-voiced-batch",
                str(tmp_path / "eis_*_harmonized.csv"),
                "--max-rule-total-cost",
                "BAD",
            ],
        )
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def test_main_returns_int() -> None:
    code = cli_module.main(["version"])
    assert code == 0


class TestWavRenderHelper:
    def test_try_render_wav_no_backend(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        midi = tmp_path / "x.mid"
        wav = tmp_path / "x.wav"
        midi.write_bytes(b"MThd")
        monkeypatch.setattr(cli_module.shutil, "which", lambda _: None)
        ok, msg = cli_module._try_render_wav(
            out_midi_path=midi,
            out_wav_path=wav,
            soundfont_path=None,
        )
        assert ok is False
        assert "no MIDI synth found" in msg

    def test_try_render_wav_fluidsynth_requires_soundfont(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        midi = tmp_path / "x.mid"
        wav = tmp_path / "x.wav"
        midi.write_bytes(b"MThd")
        monkeypatch.setattr(
            cli_module.shutil,
            "which",
            lambda name: "/usr/bin/fluidsynth" if name == "fluidsynth" else None,
        )
        monkeypatch.setattr(cli_module, "_pick_default_soundfont", lambda: None)
        ok, msg = cli_module._try_render_wav(
            out_midi_path=midi,
            out_wav_path=wav,
            soundfont_path=None,
        )
        assert ok is False
        assert "no soundfont" in msg


class TestFindSoundfonts:
    def test_find_soundfonts_json(self) -> None:
        result = runner.invoke(cli_module.app, ["progression", "find-soundfonts", "--json"])
        assert result.exit_code in (0, 1)
        data = json.loads(result.stdout)
        assert isinstance(data, list)


class TestProgressionPipelineVoicedBatch:
    def test_pipeline_voiced_batch_writes_outputs_and_summary(self, tmp_path: Path) -> None:
        a = tmp_path / "eis_e3_harmonized.csv"
        summary = tmp_path / "pipeline.json"
        payload = (
            "bar,chord_midis,melody_qn_midis\n"
            "1,48|52|55|59,59|60|62|62\n"
            "2,46|51|55|62,62|61|61|61\n"
        )
        a.write_text(payload, encoding="utf-8")
        out_dir = tmp_path / "out"
        result = runner.invoke(
            cli_module.app,
            [
                "progression",
                "pipeline-voiced-batch",
                str(tmp_path / "eis_*_harmonized.csv"),
                "--out-dir",
                str(out_dir),
                "--ruleset",
                "EIS",
                "--summary-out",
                str(summary),
                "--json",
            ],
        )
        assert result.exit_code == 0
        assert (out_dir / "eis_e3_harmonized_cli.mid").exists()
        assert summary.exists()
        bundle = json.loads(summary.read_text(encoding="utf-8"))
        assert bundle["file_count"] == 1

    def test_pipeline_voiced_batch_quality_failure_exit_1(self, tmp_path: Path) -> None:
        a = tmp_path / "eis_e3_harmonized.csv"
        payload = (
            "bar,chord_midis,melody_qn_midis\n"
            "1,48|52|55|59,59|60|62|62\n"
            "2,46|51|55|62,62|61|61|61\n"
        )
        a.write_text(payload, encoding="utf-8")
        result = runner.invoke(
            cli_module.app,
            [
                "progression",
                "pipeline-voiced-batch",
                str(tmp_path / "eis_*_harmonized.csv"),
                "--out-dir",
                str(tmp_path / "out"),
                "--ruleset",
                "EIS",
                "--min-grade",
                "A",
                "--json",
            ],
        )
        assert result.exit_code == 1

    def test_pipeline_voiced_batch_fail_on_rule_exit_1(self, tmp_path: Path) -> None:
        a = tmp_path / "eis_e3_harmonized.csv"
        payload = (
            "bar,chord_midis,melody_qn_midis\n"
            "1,48|52|55|59,59|60|62|62\n"
            "2,46|51|55|62,62|61|61|61\n"
        )
        a.write_text(payload, encoding="utf-8")
        result = runner.invoke(
            cli_module.app,
            [
                "progression",
                "pipeline-voiced-batch",
                str(tmp_path / "eis_*_harmonized.csv"),
                "--out-dir",
                str(tmp_path / "out"),
                "--ruleset",
                "EIS",
                "--fail-on-rule",
                "O-004",
            ],
        )
        assert result.exit_code == 1
