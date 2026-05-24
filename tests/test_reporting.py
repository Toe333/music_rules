"""Tests for passage-report summarization helpers."""

from __future__ import annotations

from music_rules.core.reporting import format_passage_report_summary, summarize_passage_report


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
