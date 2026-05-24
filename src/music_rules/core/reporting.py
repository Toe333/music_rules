"""Helpers for summarizing passage-evaluator reports.

The evaluator already returns machine-friendly JSON. This module provides
small utilities that condense that JSON into "what should I fix first?"
summaries for CLI or scripting workflows.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def summarize_passage_report(report: dict[str, Any], *, top_n: int = 5) -> dict[str, Any]:
    """Build an actionable summary from an ``evaluate_passage`` report.

    Args:
        report: ``evaluate_passage`` output payload.
        top_n: max number of rule buckets to include in each top-list.

    Returns:
        A compact dict containing:
        - grade / total_cost
        - hard+soft counts
        - top hard rules by hit count
        - top soft rules by accumulated cost
    """
    hard = report.get("hard_violations", []) or []
    soft = report.get("soft_violations", []) or []

    hard_by_rule: dict[str, int] = defaultdict(int)
    for row in hard:
        hard_by_rule[str(row.get("rule_id", "UNKNOWN"))] += 1

    soft_by_rule_count: dict[str, int] = defaultdict(int)
    soft_by_rule_cost: dict[str, float] = defaultdict(float)
    for row in soft:
        rid = str(row.get("rule_id", "UNKNOWN"))
        soft_by_rule_count[rid] += 1
        soft_by_rule_cost[rid] += float(row.get("cost", 0.0))

    top_hard = [
        {"rule_id": rid, "count": count}
        for rid, count in sorted(hard_by_rule.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
    ]
    top_soft = [
        {
            "rule_id": rid,
            "count": soft_by_rule_count[rid],
            "total_cost": round(cost, 4),
        }
        for rid, cost in sorted(soft_by_rule_cost.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
    ]

    return {
        "grade": report.get("grade", "?"),
        "total_cost": float(report.get("total_cost", 0.0)),
        "hard_count": len(hard),
        "soft_count": len(soft),
        "top_hard_rules": top_hard,
        "top_soft_rules": top_soft,
    }


def format_passage_report_summary(report: dict[str, Any], *, top_n: int = 5) -> str:
    """Render :func:`summarize_passage_report` as a terminal-friendly block."""
    s = summarize_passage_report(report, top_n=top_n)
    lines = [
        f"grade={s['grade']} total_cost={s['total_cost']:.4g} "
        f"hard={s['hard_count']} soft={s['soft_count']}",
        "",
        "Top hard-rule hits:",
    ]
    if s["top_hard_rules"]:
        lines.extend(f"  - {row['rule_id']}: {row['count']}" for row in s["top_hard_rules"])
    else:
        lines.append("  - none")

    lines.append("")
    lines.append("Top soft-rule costs:")
    if s["top_soft_rules"]:
        lines.extend(
            f"  - {row['rule_id']}: cost={row['total_cost']:.4g} (count={row['count']})"
            for row in s["top_soft_rules"]
        )
    else:
        lines.append("  - none")
    return "\n".join(lines)
