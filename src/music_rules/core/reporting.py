"""Helpers for summarizing passage-evaluator reports.

The evaluator already returns machine-friendly JSON. This module provides
small utilities that condense that JSON into "what should I fix first?"
summaries for CLI or scripting workflows.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

_GRADE_ORDER: dict[str, int] = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}


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


def build_summary_diff(
    *, baseline_payload: dict[str, Any], candidate_payload: dict[str, Any]
) -> dict[str, Any]:
    """Compare two batch summary payloads and classify per-file changes."""
    baseline_items = baseline_payload.get("items", []) or []
    candidate_items = candidate_payload.get("items", []) or []
    baseline_by_file = {str(item.get("file", "")): item for item in baseline_items}
    candidate_by_file = {str(item.get("file", "")): item for item in candidate_items}
    files = sorted(set(baseline_by_file) | set(candidate_by_file))

    rows: list[dict[str, Any]] = []
    regressions = 0
    improvements = 0
    unchanged = 0

    for file_name in files:
        base = baseline_by_file.get(file_name)
        cand = candidate_by_file.get(file_name)
        if base is None:
            rows.append({"file": file_name, "status": "added"})
            unchanged += 1
            continue
        if cand is None:
            rows.append({"file": file_name, "status": "removed"})
            unchanged += 1
            continue

        base_grade = str(base.get("grade", "F")).upper()
        cand_grade = str(cand.get("grade", "F")).upper()
        base_hard = int(base.get("hard_count", 0))
        cand_hard = int(cand.get("hard_count", 0))
        base_soft = int(base.get("soft_count", 0))
        cand_soft = int(cand.get("soft_count", 0))
        base_cost = float(base.get("total_cost", 0.0))
        cand_cost = float(cand.get("total_cost", 0.0))

        grade_delta = _GRADE_ORDER.get(cand_grade, 0) - _GRADE_ORDER.get(base_grade, 0)
        hard_delta = cand_hard - base_hard
        soft_delta = cand_soft - base_soft
        cost_delta = cand_cost - base_cost

        if grade_delta < 0 or hard_delta > 0 or cost_delta > 0:
            status = "regression"
            regressions += 1
        elif grade_delta > 0 or hard_delta < 0 or cost_delta < 0:
            status = "improvement"
            improvements += 1
        else:
            status = "unchanged"
            unchanged += 1

        rows.append(
            {
                "file": file_name,
                "status": status,
                "baseline_grade": base_grade,
                "candidate_grade": cand_grade,
                "grade_delta": grade_delta,
                "hard_delta": hard_delta,
                "soft_delta": soft_delta,
                "cost_delta": cost_delta,
            }
        )

    return {
        "baseline_file_count": len(baseline_items),
        "candidate_file_count": len(candidate_items),
        "compared_files": len(files),
        "regressions": regressions,
        "improvements": improvements,
        "unchanged": unchanged,
        "items": rows,
    }


def build_summary_history(
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build trend/regression metadata from ordered summary runs."""
    if not runs:
        return {
            "run_count": 0,
            "total_regressions": 0,
            "total_improvements": 0,
            "latest_regression_files": [],
            "latest_improvement_files": [],
            "latest_regression_items": [],
            "latest_improvement_items": [],
            "runs": [],
        }

    ordered_runs = list(runs)
    annotated: list[dict[str, Any]] = []
    total_regressions = 0
    total_improvements = 0

    for idx, run in enumerate(ordered_runs):
        row = dict(run)
        if idx == 0:
            row["regressions_vs_prev"] = 0
            row["improvements_vs_prev"] = 0
            row["compared_vs_prev"] = 0
            row["regression_files_vs_prev"] = []
            row["improvement_files_vs_prev"] = []
            row["regression_items_vs_prev"] = []
            row["improvement_items_vs_prev"] = []
        else:
            prev = ordered_runs[idx - 1]
            diff = build_summary_diff(
                baseline_payload=prev.get("payload", {}),
                candidate_payload=run.get("payload", {}),
            )
            reg = int(diff.get("regressions", 0))
            imp = int(diff.get("improvements", 0))
            regression_items = [
                dict(item)
                for item in diff.get("items", [])
                if str(item.get("status", "")) == "regression"
            ]
            improvement_items = [
                dict(item)
                for item in diff.get("items", [])
                if str(item.get("status", "")) == "improvement"
            ]
            regression_files = [str(item.get("file", "")) for item in regression_items]
            improvement_files = [str(item.get("file", "")) for item in improvement_items]
            row["regressions_vs_prev"] = reg
            row["improvements_vs_prev"] = imp
            row["compared_vs_prev"] = int(diff.get("compared_files", 0))
            row["regression_files_vs_prev"] = regression_files
            row["improvement_files_vs_prev"] = improvement_files
            row["regression_items_vs_prev"] = regression_items
            row["improvement_items_vs_prev"] = improvement_items
            total_regressions += reg
            total_improvements += imp
        annotated.append(row)

    latest = annotated[-1] if annotated else {}
    return {
        "run_count": len(annotated),
        "total_regressions": total_regressions,
        "total_improvements": total_improvements,
        "latest_regression_files": latest.get("regression_files_vs_prev", []),
        "latest_improvement_files": latest.get("improvement_files_vs_prev", []),
        "latest_regression_items": latest.get("regression_items_vs_prev", []),
        "latest_improvement_items": latest.get("improvement_items_vs_prev", []),
        "runs": annotated,
    }


def format_summary_diff_markdown(
    payload: dict[str, Any], *, only_regressions: bool = False
) -> str:
    """Render :func:`build_summary_diff` output as markdown."""
    items = payload.get("items", []) or []
    if only_regressions:
        items = [item for item in items if str(item.get("status", "")) == "regression"]
    lines = [
        "# Progression Summary Diff",
        "",
        f"- compared_files: `{int(payload.get('compared_files', 0))}`",
        f"- regressions: `{int(payload.get('regressions', 0))}`",
        f"- improvements: `{int(payload.get('improvements', 0))}`",
        f"- unchanged: `{int(payload.get('unchanged', 0))}`",
        f"- shown_rows: `{len(items)}`",
        "",
        "| File | Status | Grade Δ | Hard Δ | Soft Δ | Cost Δ |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for item in items:
        file_name = Path(str(item.get("file", ""))).name or str(item.get("file", ""))
        status = str(item.get("status", ""))
        if status in {"added", "removed"}:
            lines.append(f"| {file_name} | {status} | - | - | - | - |")
            continue
        lines.append(
            f"| {file_name} | {status} | {int(item.get('grade_delta', 0)):+d} | "
            f"{int(item.get('hard_delta', 0)):+d} | {int(item.get('soft_delta', 0)):+d} | "
            f"{float(item.get('cost_delta', 0.0)):+.4g} |"
        )
    if not items:
        lines.append("| _none_ | - | - | - | - | - |")
    return "\n".join(lines) + "\n"


def format_summary_history_markdown(payload: dict[str, Any], *, top_n_latest: int = 10) -> str:
    """Render :func:`build_summary_history` output as markdown."""
    runs = payload.get("runs", []) or []
    lines = [
        "# Progression Summary History",
        "",
        f"- runs: `{int(payload.get('run_count', len(runs)))}`",
        f"- total_regressions: `{int(payload.get('total_regressions', 0))}`",
        f"- total_improvements: `{int(payload.get('total_improvements', 0))}`",
        f"- latest_regressions: `{len(payload.get('latest_regression_files', []) or [])}`",
        f"- latest_improvements: `{len(payload.get('latest_improvement_files', []) or [])}`",
        "",
        "| Run | Files | Hard | Parse | Quality | WAV | Regressions vs Prev | Improvements vs Prev |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for run in runs:
        label = Path(str(run.get("path", ""))).name or str(run.get("path", ""))
        lines.append(
            f"| {label} | {int(run.get('file_count', 0))} | {int(run.get('hard_failures', 0))} | "
            f"{int(run.get('parse_failures', 0))} | {int(run.get('quality_failures', 0))} | "
            f"{int(run.get('wav_failures', 0))} | {int(run.get('regressions_vs_prev', 0))} | "
            f"{int(run.get('improvements_vs_prev', 0))} |"
        )
    latest_regression_items = payload.get("latest_regression_items", []) or []
    latest_improvement_items = payload.get("latest_improvement_items", []) or []
    lines.append("")
    lines.append("Latest run regressions:")
    if latest_regression_items:
        ordered_regressions = sorted(
            latest_regression_items,
            key=lambda item: float(item.get("cost_delta", 0.0)),
            reverse=True,
        )
        for item in ordered_regressions[:top_n_latest]:
            file_name = Path(str(item.get("file", ""))).name or str(item.get("file", ""))
            lines.append(
                f"- `{file_name}` cost_delta={float(item.get('cost_delta', 0.0)):+.4g} "
                f"hard_delta={int(item.get('hard_delta', 0)):+d} "
                f"grade_delta={int(item.get('grade_delta', 0)):+d}"
            )
    else:
        lines.append("- none")
    lines.append("")
    lines.append("Latest run improvements:")
    if latest_improvement_items:
        ordered_improvements = sorted(
            latest_improvement_items,
            key=lambda item: float(item.get("cost_delta", 0.0)),
        )
        for item in ordered_improvements[:top_n_latest]:
            file_name = Path(str(item.get("file", ""))).name or str(item.get("file", ""))
            lines.append(
                f"- `{file_name}` cost_delta={float(item.get('cost_delta', 0.0)):+.4g} "
                f"hard_delta={int(item.get('hard_delta', 0)):+d} "
                f"grade_delta={int(item.get('grade_delta', 0)):+d}"
            )
    else:
        lines.append("- none")
    if not runs:
        lines.append("| _none_ | - | - | - | - | - | - | - |")
    return "\n".join(lines) + "\n"


def sort_batch_summary_items(
    items: list[dict[str, Any]],
    *,
    sort_by: str,
    descending: bool,
) -> list[dict[str, Any]]:
    """Sort batch summary rows for reporting views."""
    key_name = sort_by.lower()

    def _key_cost(item: dict[str, Any]) -> float:
        return float(item.get("total_cost", 0.0))

    def _key_grade(item: dict[str, Any]) -> int:
        return _GRADE_ORDER.get(str(item.get("grade", "F")).upper(), 0)

    def _key_hard(item: dict[str, Any]) -> int:
        return int(item.get("hard_count", 0))

    def _key_soft(item: dict[str, Any]) -> int:
        return int(item.get("soft_count", 0))

    def _key_file(item: dict[str, Any]) -> str:
        return str(item.get("file", ""))

    if key_name == "cost":
        key_fn = _key_cost
    elif key_name == "grade":
        key_fn = _key_grade
    elif key_name == "hard":
        key_fn = _key_hard
    elif key_name == "soft":
        key_fn = _key_soft
    elif key_name == "file":
        key_fn = _key_file
    else:
        raise ValueError("invalid --sort-by (expected cost|grade|hard|soft|file)")
    return sorted(items, key=key_fn, reverse=descending)


def format_batch_summary_markdown(payload: dict[str, Any]) -> str:
    """Render audit/pipeline batch summary payload as markdown."""
    items = payload.get("items", []) or []
    hard_failures = int(payload.get("hard_failures", 0))
    parse_failures = int(payload.get("parse_failures", 0))
    quality_failures = int(payload.get("quality_failures", 0))
    wav_failures = int(payload.get("wav_failures", 0))
    ruleset = payload.get("ruleset", "unknown")

    lines = [
        "# Progression Batch Summary",
        "",
        f"- ruleset: `{ruleset}`",
        f"- files: `{len(items)}`",
        f"- hard_failures: `{hard_failures}`",
        f"- parse_failures: `{parse_failures}`",
        f"- quality_failures: `{quality_failures}`",
        f"- wav_failures: `{wav_failures}`",
        "",
        "| File | OK | Grade | Hard | Soft | Cost | Gate Error | Warnings | WAV | Top Soft Rules |",
        "|---|---:|---:|---:|---:|---:|---|---|---|---|",
    ]
    for item in items:
        name = Path(str(item.get("file", ""))).name or str(item.get("file", ""))
        ok = "yes" if bool(item.get("ok", False)) else "no"
        grade = str(item.get("grade", "-"))
        hard = int(item.get("hard_count", 0))
        soft = int(item.get("soft_count", 0))
        cost = float(item.get("total_cost", 0.0))
        gate_error = str(item.get("quality_gate_error", "") or "")
        warnings = item.get("quality_warnings", []) or []
        warning_text = "; ".join(str(w) for w in warnings[:2])
        wav = "ok" if item.get("wav_out") else ("warn" if item.get("wav_warning") else "-")
        soft_rules = item.get("top_soft_rules", []) or []
        soft_text = ", ".join(
            f"{r.get('rule_id', '?')}:{r.get('total_cost', 0)}" for r in soft_rules[:3]
        )
        lines.append(
            f"| {name} | {ok} | {grade} | {hard} | {soft} | {cost:.4g} | "
            f"{gate_error} | {warning_text} | {wav} | {soft_text} |"
        )
    if not items:
        lines.append("| _none_ | - | - | - | - | - | - | - | - | - |")
    return "\n".join(lines) + "\n"
