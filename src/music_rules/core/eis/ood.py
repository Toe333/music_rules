"""Outside-Octave Dissonance (OOD) checker.

Master rules §9 (corpus rules ``O-001``..``O-006``):

* Generally **avoid OOD** — dissonant intervals between an upper voice
  and a lower voice when the two are MORE than one octave apart.
* Exceptions allowed:
  - ♭9 above the bass is OK **if ♭7 is in the chord** (O-002).
  - ♭2 above the bass is OK **over a pedal** (O-003).
  - 4 & 10 together are fine (O-005); 3 & 11 are not (O-004).
  - 11 & 17 follow the same pattern as 3 & 11 (O-006).

This module reports OOD hits in any voicing. It's a soft check (jazz
playing routinely uses OOD intentionally), but the report is useful
to the AI orchestrator when it wants to keep an arrangement strictly
within Murphy's elementary rules.

Public API
----------

* :func:`check_voicing`  — list of OOD hits in a single chord.
* :func:`check_passage`  — list of OOD hits across a full passage.
* :data:`OOD_RULES`      — registered rule ids handled here.
"""

from __future__ import annotations

from typing import Final, TypedDict

OOD_RULES: Final[tuple[str, ...]] = (
    "O-001", "O-002", "O-003", "O-004", "O-005", "O-006",
)


class OODHit(TypedDict):
    rule_id: str
    detail: str
    bass_voice: int
    upper_voice: int
    interval_semitones: int


# Dissonant intervals — minor 2nd, major 2nd, tritone, minor 7th, major 7th.
_DISSONANT_PCS: Final[set[int]] = {1, 2, 6, 10, 11}


def check_voicing(midi: list[int], *, has_b7: bool = False,
                  pedal: bool = False) -> list[OODHit]:
    """Return every OOD hit between the bass and any upper voice.

    Args:
        midi:    chord voicing as MIDI numbers, low → high.
                 First entry is treated as the bass.
        has_b7:  set True if the chord contains a ♭7 — allows ♭9 over
                 the bass (O-002).
        pedal:   set True if the bass is a pedal point — allows ♭2
                 above the bass (O-003).

    Returns:
        List of :class:`OODHit` records (empty if the voicing is clean).
    """
    if len(midi) < 2:
        return []
    bass = midi[0]
    hits: list[OODHit] = []

    for i in range(1, len(midi)):
        v = midi[i]
        interval = v - bass
        if interval <= 12:
            continue   # Within one octave — not "outside" per master §9.
        pc_above_bass = interval % 12

        # 4 + 10 (perfect-4th + 10th == 4th + major-3rd) is fine — O-005.
        if pc_above_bass in {5, 9}:    # perfect 4 above bass, or 6th
            continue

        # 3 + 11 (major 3rd + 11) — O-004 not good.
        if pc_above_bass == 4 and interval >= 16:
            hits.append({
                "rule_id": "O-004",
                "detail": (
                    f"3 & 11 outside-octave (bass {bass}, voice {i} "
                    f"at {v}, interval {interval})."
                ),
                "bass_voice": 0,
                "upper_voice": i,
                "interval_semitones": interval,
            })
            continue

        # ♭9 over a chord WITH ♭7 is OK — O-002.
        if pc_above_bass == 1 and has_b7:
            continue
        # ♭2 over a pedal is OK — O-003.
        if pc_above_bass == 1 and pedal:
            continue

        if pc_above_bass in _DISSONANT_PCS:
            # Map specific cases to specific rule ids; otherwise generic O-001.
            if pc_above_bass == 1:
                rid = "O-002"   # ♭9 without ♭7 in chord → O-002 violated
                detail = (
                    f"♭9 outside-octave without ♭7 in the chord (bass "
                    f"{bass}, voice {i} at {v}, interval {interval})."
                )
            elif pc_above_bass == 4 and interval >= 28:
                rid = "O-006"   # 11 & 17 follow the same pattern as 3 & 11
                detail = (
                    f"11 & 17 outside-octave (bass {bass}, voice {i} "
                    f"at {v}, interval {interval})."
                )
            else:
                rid = "O-001"
                detail = (
                    f"Outside-octave dissonance (bass {bass}, voice {i} "
                    f"at {v}, interval {interval} st = pc {pc_above_bass})."
                )
            hits.append({
                "rule_id": rid,
                "detail": detail,
                "bass_voice": 0,
                "upper_voice": i,
                "interval_semitones": interval,
            })

    return hits


def check_passage(chords: list[list[int]], *,
                  has_b7: list[bool] | None = None,
                  pedal: list[bool] | None = None) -> list[OODHit]:
    """Sweep every chord in a passage for OOD hits.

    ``has_b7`` and ``pedal`` (when supplied) must be one-per-chord; if
    omitted they default to ``False`` for every chord.
    """
    out: list[OODHit] = []
    for i, chord in enumerate(chords):
        b7 = has_b7[i] if has_b7 else False
        ped = pedal[i] if pedal else False
        out.extend(check_voicing(chord, has_b7=b7, pedal=ped))
    return out
