"""Two-voice motion checkers: P1_* (no direct/parallel into a perfect consonance).

A "motion pair" is the transition between two adjacent vertical sonorities
in two voices. The parallel / hidden (direct) fifth-octave-unison detection
is delegated to :class:`music21.voiceLeading.VoiceLeadingQuartet` via
:mod:`._m21`; this module just maps a positive detection onto whichever
corpus rule's species/voices predicate matches.

Rules covered:

* ``P1_1_2v``, ``P1_1_3v``, ``P1_1_4v`` — first species variants
* ``P1_2_2v``, ``P1_2_3v``, ``P1_2_4v`` — second species variants

All six say the same musical thing — no direct (parallel or similar)
motion *into* a perfect consonance (P1, P5, P8) — but they're separated
in the corpus to allow species/voice-specific exceptions later (e.g. the
horn-fifth exception in 4v second species). For now, the same logic
fires for whichever rule's species/voices predicate matches the call.
"""

from __future__ import annotations

from music_rules.core.fux import _m21
from music_rules.core.fux._common import applicable_rules
from music_rules.core.report import CheckReport, empty_report, finalize


class VoicePair(dict[str, int]):
    """A typed-dict-style payload for one verticality.

    Use as ``{"cf": <midi>, "cp": <midi>}``. Two such payloads (prev, curr)
    define a motion-pair fragment. We accept plain dicts everywhere so the
    MCP / OpenAI adapters don't have to import a custom class.
    """


def check_motion_pair(
    prev_pair: dict[str, int],
    curr_pair: dict[str, int],
    *,
    species: int | str | None = 1,
    voices: int | str = 2,
    strict: bool = False,
) -> CheckReport:
    """Validate the motion between two adjacent verticalities.

    Args:
        prev_pair:  ``{"cf": <midi>, "cp": <midi>}`` for the previous beat.
        curr_pair:  ``{"cf": <midi>, "cp": <midi>}`` for the current beat.
        species:    Counterpoint species (1..5 or ``"all"``).
        voices:     Voice count (2|3|4 or ``"any"``).
        strict:     Reserved; no motion-pair rule uses hybrid promotion today.

    The fragment shape uses ``"cf"`` and ``"cp"`` keys for clarity, but
    the rule is symmetric — what matters is whether the two voices move
    by direct motion into a perfect consonance. We follow FuxCP5's
    strictest reading (no horn-fifth / approach-by-step exception); see
    the attribution doc and PROJECT.md "ambiguity" guidance to relax it.
    """
    del strict  # all motion-pair rules in the corpus today are pure-hard
    report = empty_report()
    rules = applicable_rules("motion-pair", species, voices)
    if not rules:
        return report

    cf_prev, cf_curr = prev_pair["cf"], curr_pair["cf"]
    cp_prev, cp_curr = prev_pair["cp"], curr_pair["cp"]

    if _m21.direct_into_perfect(cf_prev, cf_curr, cp_prev, cp_curr):
        motion = _m21.motion_type(cf_prev, cf_curr, cp_prev, cp_curr)
        target = _m21.interval_name(_m21.semitones(cf_curr, cp_curr))
        for rule in rules:
            report["violations"].append(
                {
                    "rule_id": rule.id,
                    "msg": (
                        f"{motion} motion into a perfect consonance "
                        f"({target}): "
                        f"CF {_m21.name_pitch(cf_prev)}->{_m21.name_pitch(cf_curr)}, "
                        f"CP {_m21.name_pitch(cp_prev)}->{_m21.name_pitch(cp_curr)}."
                    ),
                }
            )

    return finalize(report)
