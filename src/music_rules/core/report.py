"""Standard report shapes returned by every checker.

Every checker function in ``music_rules.core.fux.*`` and
``music_rules.core.eis.*`` returns a :class:`CheckReport` (or its dict
form) so the passage evaluator (Phase 4) can fold them uniformly.
"""

from __future__ import annotations

from typing import TypedDict


class Violation(TypedDict):
    """A hard rule violation. ``msg`` should reference rule context concretely."""

    rule_id: str
    msg: str


class SoftCost(TypedDict):
    """A soft-rule cost entry. ``cost`` is summed by the evaluator."""

    rule_id: str
    cost: float
    msg: str


class CheckReport(TypedDict):
    """The standard shape returned by every checker.

    * ``ok`` is true iff ``violations`` is empty (soft costs do not
      affect ``ok``; they only contribute to the aggregated total cost).
    * ``violations`` lists hard rule failures. Each entry's ``rule_id``
      MUST come from ``rules_combined.json`` — never invent IDs.
    * ``soft_costs`` lists soft-rule costs incurred by this fragment.
    """

    ok: bool
    violations: list[Violation]
    soft_costs: list[SoftCost]


def empty_report() -> CheckReport:
    """An ok report with no violations or costs. Useful as an accumulator."""
    return {"ok": True, "violations": [], "soft_costs": []}


def merge_reports(*reports: CheckReport) -> CheckReport:
    """Merge multiple checker outputs into one combined report."""
    out: CheckReport = empty_report()
    for r in reports:
        out["violations"].extend(r["violations"])
        out["soft_costs"].extend(r["soft_costs"])
    out["ok"] = not out["violations"]
    return out


def finalize(report: CheckReport) -> CheckReport:
    """Set ``ok`` correctly based on ``violations``. Mutates and returns."""
    report["ok"] = not report["violations"]
    return report
