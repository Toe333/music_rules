"""Tests for passage-report summarization helpers."""

from __future__ import annotations

from music_rules.core.reporting import (
    build_summary_diff,
    build_summary_history,
    format_batch_summary_markdown,
    format_passage_report_summary,
    format_summary_diff_markdown,
    format_summary_history_markdown,
    sort_batch_summary_items,
    summarize_passage_report,
)


def test_summarize_passage_report_aggregates_and_sorts() -> None:
    report = {
        "grade": "D",
        "total_cost": 3.5,
        "hard_violations": [
            {"rule_id": "P1_1_2v", "position": 1, "voices_involved": [0, 1], "msg": "x"},
            {"rule_id": "P1_1_2v", "position": 2, "voices_involved": [0, 1], "msg": "x"},
            {"rule_id": "H2_1", "position": 0, "voices_involved": [0, 1], "msg": "x"},
        ],
        "soft_violations": [
            {"rule_id": "G4", "position": 1, "cost": 1.5, "msg": "x"},
            {"rule_id": "G4", "position": 2, "cost": 1.0, "msg": "x"},
            {"rule_id": "M1_1_2v", "position": 3, "cost": 1.0, "msg": "x"},
        ],
    }
    summary = summarize_passage_report(report, top_n=2)
    assert summary["grade"] == "D"
    assert summary["hard_count"] == 3
    assert summary["soft_count"] == 3
    assert summary["top_hard_rules"][0] == {"rule_id": "P1_1_2v", "count": 2}
    assert summary["top_soft_rules"][0]["rule_id"] == "G4"
    assert summary["top_soft_rules"][0]["total_cost"] == 2.5


def test_format_passage_report_summary_handles_empty() -> None:
    report = {
        "grade": "A",
        "total_cost": 0.0,
        "hard_violations": [],
        "soft_violations": [],
    }
    text = format_passage_report_summary(report)
    assert "grade=A" in text
    assert "Top hard-rule hits:" in text
    assert "none" in text


def test_build_summary_diff_classifies_regression_and_improvement() -> None:
    baseline = {
        "items": [
            {"file": "examples/a.csv", "grade": "B", "hard_count": 0, "soft_count": 3, "total_cost": 2.0},
            {"file": "examples/b.csv", "grade": "C", "hard_count": 1, "soft_count": 7, "total_cost": 6.0},
        ]
    }
    candidate = {
        "items": [
            {"file": "examples/a.csv", "grade": "C", "hard_count": 1, "soft_count": 5, "total_cost": 3.0},
            {"file": "examples/b.csv", "grade": "B", "hard_count": 0, "soft_count": 4, "total_cost": 3.0},
        ]
    }
    diff = build_summary_diff(baseline_payload=baseline, candidate_payload=candidate)
    assert diff["regressions"] == 1
    assert diff["improvements"] == 1
    items = {row["file"]: row for row in diff["items"]}
    assert items["examples/a.csv"]["status"] == "regression"
    assert items["examples/b.csv"]["status"] == "improvement"


def test_format_summary_diff_markdown_handles_added_removed() -> None:
    payload = {
        "compared_files": 2,
        "regressions": 0,
        "improvements": 0,
        "unchanged": 2,
        "items": [
            {"file": "examples/a.csv", "status": "added"},
            {"file": "examples/b.csv", "status": "removed"},
        ],
    }
    text = format_summary_diff_markdown(payload)
    assert "Progression Summary Diff" in text
    assert "| a.csv | added | - | - | - | - |" in text
    assert "| b.csv | removed | - | - | - | - |" in text


def test_format_summary_diff_markdown_only_regressions_filters_rows() -> None:
    payload = {
        "compared_files": 2,
        "regressions": 1,
        "improvements": 1,
        "unchanged": 0,
        "items": [
            {"file": "examples/a.csv", "status": "regression", "cost_delta": 1.0},
            {"file": "examples/b.csv", "status": "improvement", "cost_delta": -1.0},
        ],
    }
    text = format_summary_diff_markdown(payload, only_regressions=True)
    assert "shown_rows: `1`" in text
    assert "a.csv" in text
    assert "b.csv" not in text


def test_format_batch_summary_markdown_includes_table_rows() -> None:
    payload = {
        "ruleset": "EIS",
        "hard_failures": 0,
        "parse_failures": 0,
        "quality_failures": 0,
        "items": [
            {
                "file": "examples/a.csv",
                "ok": True,
                "grade": "A",
                "hard_count": 0,
                "soft_count": 1,
                "total_cost": 0.5,
                "quality_warnings": ["rule O-004 has 1 hit(s)"],
                "top_soft_rules": [{"rule_id": "O-004", "total_cost": 0.5}],
            }
        ],
    }
    text = format_batch_summary_markdown(payload)
    assert "Progression Batch Summary" in text
    assert "| a.csv | yes | A | 0 | 1 | 0.5 |" in text


def test_build_summary_history_aggregates_regressions() -> None:
    runs = [
        {
            "path": "run1.json",
            "file_count": 1,
            "hard_failures": 0,
            "parse_failures": 0,
            "quality_failures": 0,
            "wav_failures": 0,
            "payload": {
                "items": [
                    {
                        "file": "examples/a.csv",
                        "grade": "B",
                        "hard_count": 0,
                        "soft_count": 3,
                        "total_cost": 2.0,
                    }
                ]
            },
        },
        {
            "path": "run2.json",
            "file_count": 1,
            "hard_failures": 1,
            "parse_failures": 0,
            "quality_failures": 1,
            "wav_failures": 0,
            "payload": {
                "items": [
                    {
                        "file": "examples/a.csv",
                        "grade": "C",
                        "hard_count": 1,
                        "soft_count": 5,
                        "total_cost": 3.0,
                    }
                ]
            },
        },
    ]
    history = build_summary_history(runs)
    assert history["run_count"] == 2
    assert history["total_regressions"] == 1
    assert history["runs"][1]["regressions_vs_prev"] == 1
    assert history["latest_regression_files"] == ["examples/a.csv"]
    assert len(history["latest_regression_items"]) == 1
    assert history["latest_regression_items"][0]["status"] == "regression"


def test_format_summary_history_markdown_handles_empty() -> None:
    text = format_summary_history_markdown({"run_count": 0, "runs": []})
    assert "Progression Summary History" in text
    assert "Latest run regressions:" in text
    assert "| _none_ | - | - | - | - | - | - | - |" in text


def test_format_summary_history_markdown_shows_deltas() -> None:
    payload = {
        "run_count": 2,
        "total_regressions": 1,
        "total_improvements": 0,
        "runs": [],
        "latest_regression_items": [
            {
                "file": "examples/a.csv",
                "status": "regression",
                "cost_delta": 1.5,
                "hard_delta": 1,
                "grade_delta": -1,
            }
        ],
        "latest_improvement_items": [],
    }
    text = format_summary_history_markdown(payload, top_n_latest=5)
    assert "`a.csv` cost_delta=+1.5 hard_delta=+1 grade_delta=-1" in text


def test_sort_batch_summary_items_by_cost_desc() -> None:
    rows = [
        {"file": "a.csv", "total_cost": 1.0},
        {"file": "b.csv", "total_cost": 3.0},
        {"file": "c.csv", "total_cost": 2.0},
    ]
    ordered = sort_batch_summary_items(rows, sort_by="cost", descending=True)
    assert [row["file"] for row in ordered] == ["b.csv", "c.csv", "a.csv"]


def test_sort_batch_summary_items_invalid_key_raises() -> None:
    try:
        sort_batch_summary_items([], sort_by="nope", descending=False)
    except ValueError as exc:
        assert "invalid --sort-by" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError")
