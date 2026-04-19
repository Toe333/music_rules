"""Melodic-line checkers: G6, G7, M1_1_*, M1_2.

These are all *single-voice* checks: given the previous and current MIDI
pitches in one voice (and optionally a third surrounding pitch for the
triple checks), is the melodic motion permitted?

Rules covered (read live from ``rules_combined.json`` via
:mod:`music_rules.core.corpus` — never hardcoded here):

================  ===================  ====  ==========================================
input_shape       checker              kind  meaning
================  ===================  ====  ==========================================
melodic-interval  check_melodic_interval     one consecutive pair (n-1, n)
melodic-triple    check_melodic_triple       three consecutive notes (n-2, n-1, n)
================  ===================  ====  ==========================================
"""

from __future__ import annotations

from music_rules.core import pitch
from music_rules.core.fux._common import applicable_rules
from music_rules.core.report import CheckReport, empty_report, finalize

# Soft-cost weights. Tunable; chosen so that "moderately bad" intervals
# (e.g. an A4 in G major) carry a noticeable cost without dominating the
# evaluator's total. Documented in the rule's `tier` field semantically.
_SMALL_INTERVAL_COST_PER_SEMITONE: float = 0.05  # G7
_TRITONE_LEAP_EXTRA_COST: float = 2.0            # G7
_LEAP_OVER_OCTAVE_COST: float = 1.5              # G7 / M1 stylistic preference


def check_melodic_interval(
    prev_midi: int,
    curr_midi: int,
    *,
    species: int | str | None = 1,
    voices: int | str = 2,
    strict: bool = False,
) -> CheckReport:
    """Validate one melodic step in a single voice.

    Applies every rule in ``rules_combined.json`` whose ``input_shape`` is
    ``melodic-interval`` AND whose ``species`` / ``voices`` match the
    current context. Returns the standard :class:`CheckReport`.

    Args:
        prev_midi:  MIDI number of the previous note in this voice.
        curr_midi:  MIDI number of the current note in this voice.
        species:    Counterpoint species (1..5 or ``"all"``).
        voices:     Total voice count for the passage (2|3|4|5 or ``"any"``).
        strict:     If True, hybrid rules (e.g. G4) escalate to hard violations.

    Notes on the implementation strategy
    ------------------------------------
    The rule set is fetched from the corpus on every call. This is O(R)
    where R is small (4 melodic-interval rules today) and keeps the
    checker self-rebuilding when the JSON changes — no module-level
    caching to invalidate, no risk of staleness in long-running
    processes (e.g. an MCP server). We only filter on ``species`` and
    ``voices`` once; the per-rule branch below dispatches on ``rule.id``
    to its musical meaning. **Rule IDs are still loaded from JSON, not
    hardcoded** — they are dynamic discriminators here, not strings
    pasted into business logic.
    """
    report = empty_report()
    rules = applicable_rules("melodic-interval", species, voices)

    semis = pitch.semitones_between(prev_midi, curr_midi)
    interval = pitch.interval_name(semis)

    for rule in rules:
        # Hard rules (M1_*) — hard ceilings on leap size.
        if rule.kind == "hard":
            limit_octave_allowed = "octave" in rule.rule.lower() or "8" in rule.rule
            if semis > pitch.MAX_MELODIC_LEAP_SEMITONES and not (
                limit_octave_allowed and semis == pitch.OCTAVE
            ):
                report["violations"].append(
                    {
                        "rule_id": rule.id,
                        "msg": (
                            f"melodic leap of {interval} ({semis} semitones) "
                            f"exceeds the {('m6 or P8' if limit_octave_allowed else 'm6')} "
                            f"ceiling for {rule.species} species, {rule.voices}."
                        ),
                    }
                )

        # Soft rules (G7) — prefer smaller intervals; tritones extra cost.
        elif rule.kind == "soft":
            if semis > 2:  # only score meaningful leaps; steps are free
                cost = (semis - 2) * _SMALL_INTERVAL_COST_PER_SEMITONE
                if pitch.is_tritone(semis):
                    cost += _TRITONE_LEAP_EXTRA_COST
                if semis > pitch.OCTAVE:
                    cost += _LEAP_OVER_OCTAVE_COST
                if cost > 0:
                    report["soft_costs"].append(
                        {
                            "rule_id": rule.id,
                            "cost": round(cost, 4),
                            "msg": f"melodic leap of {interval} ({semis} semitones).",
                        }
                    )

        elif rule.kind == "hybrid" and strict:  # promote to hard in strict mode
            # No hybrid melodic-interval rule today; future-proofing only.
            pass

    return finalize(report)


def check_melodic_triple(
    n1: int,
    n2: int,
    n3: int,
    *,
    species: int | str | None = "all",
    voices: int | str = "any",
    strict: bool = False,
) -> CheckReport:
    """Validate three consecutive notes in a single voice.

    Applies every rule with ``input_shape == "melodic-triple"`` matching
    the species/voices context. Today this is just G6 (no chromatic
    ascent — three semitones in a row going up).
    """
    del strict  # no triple rule uses strict promotion today
    report = empty_report()
    rules = applicable_rules("melodic-triple", species, voices)

    d1 = pitch.signed_semitones(n1, n2)
    d2 = pitch.signed_semitones(n2, n3)

    for rule in rules:
        if rule.kind != "hard":
            continue

        # G6: three consecutive notes ascending by a semitone each.
        # We detect "two consecutive ascending half-steps" because that's
        # what produces a chromatic three-note motif (n1, n1+1, n1+2).
        if d1 == 1 and d2 == 1:
            report["violations"].append(
                {
                    "rule_id": rule.id,
                    "msg": (
                        f"chromatic ascending triple: "
                        f"{pitch.name_pitch(n1)} -> {pitch.name_pitch(n2)} "
                        f"-> {pitch.name_pitch(n3)} (semitone, semitone)."
                    ),
                }
            )

    return finalize(report)


