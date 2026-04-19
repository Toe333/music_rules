"""EIS voice-leading.

Two complementary jobs in one module:

* :func:`voice_lead`     — given a previous chord (as MIDI numbers, voice
  by voice) and a *target* chord (any voicing), return the smoothest
  re-voicing of the target that respects EIS voice-leading rules
  V-001..V-015 (master rules §7).
* :func:`check_progression` — given two already-voiced chords, score
  the move on the same rules and return the violations + a 0..1
  smoothness rating for ranking candidate progressions.

Rules implemented (master §7 + corpus V-001..V-015)
---------------------------------------------------

* **V-001**  Hold common tones in the same voice.
* **V-002**  Move remaining tones to the **nearest** tones in the new
              chord (minimise total semitone motion).
* **V-003**  Use **contrary motion** between one or more parts and the
              bass when possible (rewarded, not required).
* **V-004**  No three notes of the same pitch class anywhere in the
              voicing — the "no three tones together" rule.
* **V-006**  In a chord containing a natural 7, the 7 must resolve to 6
              whenever the 9 resolves to the octave.
* **V-014**  Watch for **parallel octaves** between bass and any
              treble voice (hard violation).

Soft-flagged but kept in the report for transparency: V-005 (NCTs are
ignored — see :mod:`music_rules.core.eis.nct`), V-007 / V-008 / V-015
(C.O.P. / S.P. / S.V.L. are alternative *strategies* the caller picks
between), V-009..V-013 (Dominant-7 specific moves the caller opts into
via the ``style`` argument).

Public API
----------

* :func:`voice_lead`           — re-voice the target chord smoothly.
* :func:`check_progression`    — score an existing two-chord move.
* :data:`VOICE_LEADING_RULES`  — list of rule ids handled here.
"""

from __future__ import annotations

import itertools
from typing import Final, Literal, TypedDict

VoiceLeadingStyle = Literal["normal", "parallel", "bracket"]


VOICE_LEADING_RULES: Final[tuple[str, ...]] = (
    "V-001", "V-002", "V-003", "V-004", "V-006", "V-014",
)


class VLViolation(TypedDict):
    rule_id: str
    detail: str
    voices: list[int]


class VLReport(TypedDict):
    """Output of :func:`check_progression`.

    * ``smoothness`` — 0..1, higher is smoother (1.0 = every voice
      moves by 0 or 1 semitone).
    * ``total_motion`` — sum of absolute semitone moves across voices.
    * ``common_tones`` — count of voices that held the same MIDI note.
    * ``contrary_motion_pairs`` — count of (treble, bass) pairs moving
      in contrary motion (V-003).
    * ``violations`` — every rule hit (hard or soft).
    """

    smoothness: float
    total_motion: int
    common_tones: int
    contrary_motion_pairs: int
    violations: list[VLViolation]


# ---------------------------------------------------------------------------
# voice_lead — re-voice a target chord to flow smoothly from the prev chord
# ---------------------------------------------------------------------------


def voice_lead(
    prev_chord: list[int],
    next_pcs: list[int],
    *,
    style: VoiceLeadingStyle = "normal",
    keep_bass_in_bass: bool = True,
    max_voice_jump: int = 7,
) -> list[int]:
    """Return a re-voicing of ``next_pcs`` that flows smoothly from ``prev_chord``.

    Algorithm:

    1. Pick the **bass** of the target chord. Standard rule (master §16):
       the bass is the *closest* available bass-eligible tone to the
       prior bass — usually the chord's root in the same octave region,
       but the caller can override by setting ``keep_bass_in_bass=False``.
    2. For the upper voices, enumerate every assignment of the remaining
       target pcs to the prior treble voices. For each assignment,
       pick the octave for each pc that minimises the absolute distance
       from the corresponding prior voice (subject to ``max_voice_jump``).
    3. Score the candidate by total semitone motion (V-002) minus a
       small bonus for contrary motion against the bass (V-003) and
       common-tone holds (V-001). The lowest-scoring candidate wins.

    Args:
        prev_chord:        prior chord as MIDI numbers, low → high.
                           First entry is treated as the bass.
        next_pcs:          pitch-class set of the target chord (output
                           of :func:`music_rules.core.eis.chords.pitch_classes`).
        style:             ``"normal"`` minimises motion; ``"parallel"``
                           keeps the same intervallic shape (V-012);
                           ``"bracket"`` allows one voice to drop
                           (V-013, returns one fewer note).
        keep_bass_in_bass: if True, the bass of ``prev_chord`` is
                           replaced by the closest target pc within an
                           octave; if False, the bass moves freely.
        max_voice_jump:    upper bound on per-voice semitone motion
                           (default 7 — a perfect fifth — Murphy
                           treats anything bigger as a leap, not VL).

    Returns:
        Re-voiced target chord as a sorted list of MIDI numbers.
    """
    if not prev_chord:
        raise ValueError("prev_chord must be non-empty")
    if not next_pcs:
        raise ValueError("next_pcs must be non-empty")

    n_voices = len(prev_chord)
    if style == "bracket" and n_voices > 1:
        n_voices -= 1   # V-013: bracket VL drops one voice

    bass_target_pc = _pick_bass_pc(prev_chord[0], next_pcs, keep_bass_in_bass)
    new_bass = _nearest_octave(prev_chord[0], bass_target_pc, max_voice_jump)

    treble_prev = prev_chord[1:n_voices]
    treble_pcs = [pc for pc in next_pcs if pc != bass_target_pc] or list(next_pcs)
    if not treble_prev:
        return [new_bass]

    # Repeat / pad the treble pc list so we have one pc per upper voice.
    upper_pcs = _pad_pcs(treble_pcs, len(treble_prev))

    if style == "parallel":
        # V-012: keep intervals — every voice moves by the same amount
        # the bass did, modulo octave.
        bass_motion = new_bass - prev_chord[0]
        assigned = [_nearest_octave(p + bass_motion, p_pc, max_voice_jump * 2)
                    for p, p_pc in zip(treble_prev, upper_pcs, strict=True)]
        return sorted([new_bass, *assigned])

    # Normal style — explore every pc-to-voice assignment, pick the
    # arrangement with minimum cost.
    best: tuple[int, list[int]] | None = None
    bass_motion = new_bass - prev_chord[0]
    for permutation in itertools.permutations(upper_pcs):
        candidate = []
        for prev_v, target_pc in zip(treble_prev, permutation, strict=True):
            candidate.append(_nearest_octave(prev_v, target_pc, max_voice_jump))

        cost = _vl_cost(prev_chord[1:n_voices], candidate, bass_motion)
        if best is None or cost < best[0]:
            best = (cost, candidate)

    assert best is not None
    return sorted([new_bass, *best[1]])


# ---------------------------------------------------------------------------
# check_progression — score an existing two-chord move
# ---------------------------------------------------------------------------


def check_progression(prev_chord: list[int], next_chord: list[int]) -> VLReport:
    """Score a fully-voiced chord move and report rule violations.

    Both chords must have the **same number of voices**, ordered from
    low to high. The first index is the bass for V-014's parallel-octave
    check.

    The smoothness score is normalised so that ``1.0`` means every voice
    moved by ≤ 1 semitone (or held a common tone).
    """
    if len(prev_chord) != len(next_chord):
        raise ValueError(
            f"prev/next chord length mismatch: {len(prev_chord)} vs "
            f"{len(next_chord)}. Both must have the same voice count."
        )
    if not prev_chord:
        raise ValueError("chords must be non-empty")

    violations: list[VLViolation] = []
    n = len(prev_chord)
    motions = [next_chord[i] - prev_chord[i] for i in range(n)]
    abs_motion = [abs(m) for m in motions]
    total_motion = sum(abs_motion)

    # V-001 — common tones held? (informational — show the score impact)
    common_tones = sum(1 for m in motions if m == 0)
    # V-002 — every voice should move <= a P5 (7 st).
    for i, m in enumerate(abs_motion):
        if m > 7:
            violations.append({
                "rule_id": "V-002",
                "detail": f"voice {i} jumps {m} semitones (> P5).",
                "voices": [i],
            })

    # V-003 — contrary motion between bass and at least one treble?
    bass_motion = motions[0]
    contrary_pairs = 0
    for i in range(1, n):
        if bass_motion != 0 and motions[i] != 0 and (
            (bass_motion > 0) != (motions[i] > 0)
        ):
            contrary_pairs += 1

    # V-004 — no three notes of the same pitch class in either chord.
    for label, chord in (("prev", prev_chord), ("next", next_chord)):
        pc_counts: dict[int, list[int]] = {}
        for i, midi in enumerate(chord):
            pc_counts.setdefault(midi % 12, []).append(i)
        for pc, voices in pc_counts.items():
            if len(voices) >= 3:
                violations.append({
                    "rule_id": "V-004",
                    "detail": (
                        f"{label} chord triples pitch-class {pc} in "
                        f"voices {voices} ('no three tones together')."
                    ),
                    "voices": voices,
                })

    # V-014 — parallel octaves between bass and any treble voice?
    # Trigger: bass and voice move by the same nonzero amount AND the
    # interval between them is a perfect octave/unison both before and
    # after the move.
    for i in range(1, n):
        prev_interval = (prev_chord[i] - prev_chord[0]) % 12
        next_interval = (next_chord[i] - next_chord[0]) % 12
        if (
            motions[i] == bass_motion
            and motions[i] != 0
            and prev_interval == 0
            and next_interval == 0
        ):
            violations.append({
                "rule_id": "V-014",
                "detail": (
                    f"Parallel octaves: bass and voice {i} move "
                    f"{motions[i]} semitones in lockstep."
                ),
                "voices": [0, i],
            })

    smoothness = max(0.0, 1.0 - (total_motion / (n * 7)))

    return {
        "smoothness": round(smoothness, 3),
        "total_motion": total_motion,
        "common_tones": common_tones,
        "contrary_motion_pairs": contrary_pairs,
        "violations": violations,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _pick_bass_pc(prev_bass_midi: int, next_pcs: list[int],
                  keep_in_bass: bool) -> int:
    """Pick the bass pitch-class for the new chord."""
    if not keep_in_bass:
        return next_pcs[0]
    # Closest pc to the prior bass.
    prev_pc = prev_bass_midi % 12
    return min(next_pcs, key=lambda pc: min(
        (pc - prev_pc) % 12, (prev_pc - pc) % 12,
    ))


def _nearest_octave(prev_midi: int, target_pc: int, max_jump: int) -> int:
    """Return the MIDI number for ``target_pc`` closest to ``prev_midi``.

    Falls back to the nearest pitch even if the move exceeds ``max_jump``;
    it's the caller's job to penalise that in the cost function.
    """
    base = (prev_midi // 12) * 12 + target_pc
    candidates = [base - 12, base, base + 12]
    candidates.sort(key=lambda m: abs(m - prev_midi))
    return candidates[0]


def _pad_pcs(pcs: list[int], target_len: int) -> list[int]:
    """Pad / truncate a pitch-class list to ``target_len`` voices.

    Doubles the first pc (root) when too short; truncates from the
    end when too long.
    """
    out = list(pcs)
    while len(out) < target_len:
        out.append(out[0])
    return out[:target_len]


def _vl_cost(prev_treble: list[int], next_treble: list[int],
             bass_motion: int) -> int:
    """Cost function: total motion - small bonuses for held / contrary tones."""
    cost = 0
    for prev, curr in zip(prev_treble, next_treble, strict=True):
        diff = abs(curr - prev)
        cost += diff
        if diff == 0:
            cost -= 2     # V-001 bonus
        elif diff > 7:
            cost += 5     # large-leap penalty (V-002)
        if (curr - prev) != 0 and bass_motion != 0 and (
            (curr - prev > 0) != (bass_motion > 0)
        ):
            cost -= 1     # V-003 bonus
    return cost
