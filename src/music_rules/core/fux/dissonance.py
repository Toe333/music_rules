"""Dissonance-treatment checker: H2_3 (3rd-species passing & neighbor figures).

A "dissonance context" is a triple of (prev, dissonant_note, next) in a
single voice, evaluated against a sustained or moving cantus-firmus
voice. In Fuxian 3rd species, every dissonance must be either:

* a **passing tone** — approached and left by step in the same direction
  (n-1 → n by step, n → n+1 by step, both in the same direction); or
* a **neighbor tone** — approached and left by step in opposite directions
  (returns to the same pitch as ``prev``).

Anything else is forbidden. We deliberately do NOT report unprepared
suspensions here — those have a different ``input_shape`` (``figure``,
covered by H3_3 in 3rd species).
"""

from __future__ import annotations

from music_rules.core import pitch
from music_rules.core.fux._common import applicable_rules
from music_rules.core.report import CheckReport, empty_report, finalize


def check_dissonance_context(
    prev: int,
    diss: int,
    next_: int,
    *,
    cf_pitch: int | None = None,
    species: int | str | None = 3,
    voices: int | str = "any",
    strict: bool = False,
) -> CheckReport:
    """Validate that a dissonance is approached and left correctly.

    Args:
        prev:      MIDI of the note immediately before the dissonance.
        diss:      MIDI of the candidate dissonant note.
        next_:     MIDI of the note immediately after.
        cf_pitch:  MIDI of the cantus-firmus note sustained against the
                   dissonance, or ``None`` if no CF context is available.
                   When ``None`` the check assumes the caller has already
                   determined the dissonance — useful for unit-testing.
        species:   Counterpoint species (defaults to 3 since H2_3 is sp3).
        voices:    Voice count.
        strict:    Reserved.

    Returns:
        Standard :class:`CheckReport`. If the input is not actually
        dissonant against ``cf_pitch``, the report is empty (the rule
        is vacuously satisfied).
    """
    del strict
    report = empty_report()
    rules = applicable_rules("dissonance-context", species, voices)
    if not rules:
        return report

    if cf_pitch is not None:
        actual_diss = pitch.is_dissonance(pitch.semitones_between(diss, cf_pitch))
        if not actual_diss:
            return report  # caller mis-flagged; nothing to enforce

    approach_step = pitch.is_stepwise(prev, diss)
    leave_step = pitch.is_stepwise(diss, next_)
    if not (approach_step and leave_step):
        for rule in rules:
            report["violations"].append(
                {
                    "rule_id": rule.id,
                    "msg": (
                        f"dissonance {pitch.name_pitch(diss)} not embedded in a "
                        f"stepwise figure (approach={'step' if approach_step else 'leap'}, "
                        f"leave={'step' if leave_step else 'leap'})."
                    ),
                }
            )
        return finalize(report)

    # Both step — must be passing OR neighbor. Anything else (a "diminution"
    # that doesn't fit either pattern) is rejected.
    d_in = pitch.signed_semitones(prev, diss)
    d_out = pitch.signed_semitones(diss, next_)
    is_passing = (d_in > 0 and d_out > 0) or (d_in < 0 and d_out < 0)
    is_neighbor = next_ == prev  # returns to origin pitch
    if not (is_passing or is_neighbor):
        for rule in rules:
            report["violations"].append(
                {
                    "rule_id": rule.id,
                    "msg": (
                        f"dissonance {pitch.name_pitch(diss)} is approached and left "
                        f"by step but is neither a passing tone nor a neighbor "
                        f"({pitch.name_pitch(prev)} -> {pitch.name_pitch(diss)} -> "
                        f"{pitch.name_pitch(next_)})."
                    ),
                }
            )

    return finalize(report)
