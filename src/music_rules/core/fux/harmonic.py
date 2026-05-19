"""Harmonic / vertical sonority checkers: H1_1, H2_1, H2_2, H3_1, H8_*.

These checkers all look at a single vertical sonority (a chord — but in
2-voice species 1 that's just the harmonic interval between the two
voices) and judge it against the rules whose ``input_shape`` indicates
"this is a vertical context."

Triad-completeness and consonance judgments are delegated to music21
(via :mod:`._m21`); the Fuxian "P4 is dissonant in 2 voices" convention
lives in :mod:`._m21` as a voice-count parameter and is selected here.

Public API:

* :func:`check_vertical_chord`     — generic vertical-chord rules (H8_*)
* :func:`check_first_interval`     — opening sonority rules (H2_1)
* :func:`check_final_interval`     — closing sonority rules (H3_1)
* :func:`check_per_measure_downbeat` — H1_1 (downbeat consonance)
* :func:`check_weak_beat_interval` — H2_2 (arsis cannot be dissonant in sp 2)
"""

from __future__ import annotations

from collections.abc import Sequence

from music_rules.core.fux import _m21
from music_rules.core.fux._common import applicable_rules
from music_rules.core.report import CheckReport, empty_report, finalize


def _bass_and_top(chord: Sequence[int]) -> tuple[int, int]:
    """Return ``(bass_midi, top_midi)`` for a 2+-note chord."""
    if len(chord) < 2:
        raise ValueError(f"chord must have at least 2 notes; got {chord!r}")
    return min(chord), max(chord)


# ---------------------------------------------------------------------------
# Vertical-chord rules (H8_*)
# ---------------------------------------------------------------------------


def check_vertical_chord(
    chord: Sequence[int],
    *,
    key: str = "C",
    position: int = 0,
    total_length: int = 1,
    species: int | str | None = 1,
    voices: int | str = 3,
    strict: bool = False,
) -> CheckReport:
    """Validate a single vertical sonority.

    Today this fires the H8_* "prefer complete triad" soft costs in 3v
    and 4v writing. Other vertical-context rules (downbeat, weak-beat,
    first, final) live in their own dedicated checkers below so the
    evaluator can dispatch on ``input_shape`` cleanly.

    Args:
        chord:         MIDI numbers of the simultaneous notes (≥1 note).
        key:           Tonal key (currently only used for first/final tests
                       elsewhere; accepted here for signature uniformity).
        position:      0-based bar/beat index of this chord in the piece.
        total_length:  Total length so position/total_length disambiguates
                       first / penultimate / final contexts.
        species:       Counterpoint species.
        voices:        Voice count.
        strict:        Reserved.
    """
    del key, position, total_length, strict  # unused for H8_* today
    report = empty_report()
    rules = applicable_rules("vertical-chord", species, voices)
    if not rules:
        return report

    if _m21.is_complete_triad(chord):
        return report  # nothing to penalize

    # Otherwise, every applicable H8_* rule fires its soft cost once.
    # Cost magnitude is set per-rule so future tuning can differentiate
    # 3v vs 4v penalties.
    for rule in rules:
        cost = 1.0  # soft baseline; future: read from rule metadata
        report["soft_costs"].append(
            {
                "rule_id": rule.id,
                "cost": cost,
                "msg": (
                    f"incomplete triad at vertical sonority "
                    f"{[_m21.name_pitch(n) for n in chord]} "
                    f"(missing 3rd or 5th over bass)."
                ),
            }
        )
    return finalize(report)


# ---------------------------------------------------------------------------
# First-interval rules (H2_1)
# ---------------------------------------------------------------------------


def check_first_interval(
    chord: Sequence[int],
    *,
    species: int | str | None = 1,
    voices: int | str = 2,
    strict: bool = False,
) -> CheckReport:
    """Validate the very first vertical sonority of the piece.

    For 2v 1st-species (H2_1) the opening interval must be a perfect
    consonance (P1, P5, P8). The corpus rule's ``species`` / ``voices``
    predicates govern when the rule applies.
    """
    del strict
    report = empty_report()
    rules = applicable_rules("first-interval", species, voices)
    if not rules:
        return report

    bass, top = _bass_and_top(chord)
    if not _m21.is_perfect_consonance(bass, top):
        interval = _m21.interval_name(_m21.semitones(bass, top))
        for rule in rules:
            report["violations"].append(
                {
                    "rule_id": rule.id,
                    "msg": (
                        f"opening interval is {interval}, "
                        f"must be a perfect consonance (P1, P5, or P8)."
                    ),
                }
            )
    return finalize(report)


# ---------------------------------------------------------------------------
# Final-interval rules (H3_1)
# ---------------------------------------------------------------------------


def check_final_interval(
    chord: Sequence[int],
    *,
    species: int | str | None = 1,
    voices: int | str = 2,
    strict: bool = False,
) -> CheckReport:
    """Validate the very last vertical sonority of the piece.

    For 2v 1st-species (H3_1) the final interval must be a perfect
    consonance — historically a unison or octave on the tonic.
    """
    del strict
    report = empty_report()
    rules = applicable_rules("final-interval", species, voices)
    if not rules:
        return report

    bass, top = _bass_and_top(chord)
    if not _m21.is_perfect_consonance(bass, top):
        interval = _m21.interval_name(_m21.semitones(bass, top))
        for rule in rules:
            report["violations"].append(
                {
                    "rule_id": rule.id,
                    "msg": (
                        f"closing interval is {interval}, "
                        f"must be a perfect consonance (P1, P5, or P8)."
                    ),
                }
            )
    return finalize(report)


# ---------------------------------------------------------------------------
# Per-measure downbeat rules (H1_1)
# ---------------------------------------------------------------------------


def check_per_measure_downbeat(
    chord: Sequence[int],
    *,
    species: int | str | None = "all",
    voices: int | str = "any",
    strict: bool = False,
) -> CheckReport:
    """Validate the harmonic intervals on a measure's downbeat (thesis).

    H1_1: Every downbeat sonority must be a consonance. In 2v Fuxian
    writing this excludes the P4 (dissonant in 2 voices, consonant once
    a third voice supports it). The voice-count-aware consonance test
    lives in :mod:`._m21`.
    """
    del strict
    report = empty_report()
    rules = applicable_rules("per-measure-downbeat", species, voices)
    if not rules:
        return report

    voice_count = _voice_count_int(voices) or 2  # default conservative

    for rule in rules:
        for low_idx, low in enumerate(chord):
            for high in chord[low_idx + 1 :]:
                if not _m21.is_consonant(low, high, voice_count=voice_count):
                    semis = _m21.semitones(low, high)
                    p4_note = (
                        " (P4 is dissonant in 2-voice writing)"
                        if voice_count == 2 and _m21.is_p4(semis)
                        else ""
                    )
                    report["violations"].append(
                        {
                            "rule_id": rule.id,
                            "msg": (
                                f"downbeat sonority contains a dissonant interval "
                                f"{_m21.interval_name(semis)} between "
                                f"{_m21.name_pitch(low)} and {_m21.name_pitch(high)}"
                                f"{p4_note}."
                            ),
                        }
                    )
    return finalize(report)


# ---------------------------------------------------------------------------
# Weak-beat interval rules (H2_2)
# ---------------------------------------------------------------------------


def check_weak_beat_interval(
    chord: Sequence[int],
    *,
    species: int | str | None = 2,
    voices: int | str = "any",
    strict: bool = False,
) -> CheckReport:
    """In 2nd species, the arsis (weak beat) cannot be dissonant (H2_2).

    Stricter than ``check_per_measure_downbeat`` only in that it applies
    to the off-beat note specifically; the dispatch decision (is this a
    weak-beat fragment?) is the evaluator's job in Phase 4.
    """
    del strict
    report = empty_report()
    rules = applicable_rules("weak-beat-interval", species, voices)
    if not rules:
        return report

    for rule in rules:
        for low_idx, low in enumerate(chord):
            for high in chord[low_idx + 1 :]:
                if _m21.is_dissonant(low, high):
                    semis = _m21.semitones(low, high)
                    report["violations"].append(
                        {
                            "rule_id": rule.id,
                            "msg": (
                                f"weak-beat interval {_m21.interval_name(semis)} "
                                f"between {_m21.name_pitch(low)} and {_m21.name_pitch(high)} "
                                f"is dissonant (forbidden in 2nd-species arsis)."
                            ),
                        }
                    )
    return finalize(report)


def _voice_count_int(voices: int | str) -> int:
    if isinstance(voices, int):
        return voices
    if voices == "any":
        return 0
    return int(voices.rstrip("v").split(",")[0])
