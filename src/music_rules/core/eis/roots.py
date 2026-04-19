"""EIS Root-tones — the six Equal-Interval (E-number) cycles.

Spud Murphy reduces the 12 chromatic intervals to **6 equal-interval
cycles**, since an interval and its inversion share the same cycle (the
Roots are octave-equivalent).

================  ============================  ==============  ================================================
E#                Generating interval           Cycle length    Example (ascending from C)
================  ============================  ==============  ================================================
``E1``            minor 2nd (semitone)          12              C → C# → D → D# → … (chromatic)
``E2``            major 2nd (whole tone)        6               C → D → E → F# → G# → A#
``E3``            minor 3rd                     4               C → E♭ → G♭ → A
``E4``            major 3rd                     3               C → E → G#
``E5``            perfect 4th                   12              C → F → B♭ → E♭ → … (circle of 4ths)
``E6``            tritone                       2               C → F#
================  ============================  ==============  ================================================

The perfect 5th is *not* a separate cycle — it's the inverse of the 4th
and lives inside ``E5`` (descending or inverted). See
``data/eis/EIS_MASTER_RULES.md`` §4.

Public API
----------

* :data:`E_CYCLES`               — frozen mapping of cycle id → semitone step.
* :func:`cycle_root_pcs`         — pitch-class sequence for one full cycle.
* :func:`cycle_root_names`       — note-name sequence for one full cycle.
* :func:`pick_root_line`         — generate a Root-line of N tones across cycles.
* :func:`is_valid_progression`   — check that adjacent Roots belong to a permitted cycle.

Design choices
--------------

* All math is in pitch classes (0..11). Octave choice is the caller's
  problem (chord builders / voicers handle it in Phase 8).
* ``pick_root_line`` is **deterministic given a seed** and never raises
  on legal inputs — it returns the longest line it can build under the
  elision rules so MCP clients can recover gracefully.
* Cycle membership is judged by the *interval class* between adjacent
  Roots, not by absolute pitches, so transpositions are handled for free.
"""

from __future__ import annotations

import random
from itertools import pairwise
from typing import Final, Literal

CycleId = Literal["E1", "E2", "E3", "E4", "E5", "E6"]


# Semitone step for each cycle. Inversion (e.g. P5 = -P4 mod 12) is the
# *same* cycle, so we store the canonical (smaller) step here and treat
# its inversion as a synonym in :func:`is_valid_progression`.
E_CYCLES: Final[dict[CycleId, int]] = {
    "E1": 1,   # minor 2nd
    "E2": 2,   # major 2nd
    "E3": 3,   # minor 3rd
    "E4": 4,   # major 3rd
    "E5": 5,   # perfect 4th  (P5 = 7 = -5 mod 12 is the same cycle)
    "E6": 6,   # tritone
}

# Cycle length = 12 / gcd(12, step). The corpus calls these out
# explicitly in §4 of the master doc; we re-derive them programmatically
# so the constants stay in sync if a hypothetical cycle is added later.
def _cycle_length(step: int) -> int:
    from math import gcd
    return 12 // gcd(12, step)


CYCLE_LENGTHS: Final[dict[CycleId, int]] = {
    cid: _cycle_length(step) for cid, step in E_CYCLES.items()
}


_NOTE_NAMES_SHARP: Final[tuple[str, ...]] = (
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
)
_NOTE_NAMES_FLAT: Final[tuple[str, ...]] = (
    "C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B",
)
_PC_OF_NAME: Final[dict[str, int]] = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4,
    "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9,
    "A#": 10, "Bb": 10, "B": 11,
}


# ---------------------------------------------------------------------------
# Cycle generation
# ---------------------------------------------------------------------------


def cycle_root_pcs(cycle: CycleId, start: str | int = "C") -> list[int]:
    """Generate every pitch class in a single E-cycle starting at ``start``.

    Args:
        cycle: ``"E1"``..``"E6"``.
        start: starting Root, as a note name (``"C"``, ``"Bb"``) or
               pitch class (0..11).

    Returns:
        A list of pitch classes of length :data:`CYCLE_LENGTHS[cycle]`.
        For ``E1`` this is the full chromatic scale, for ``E6`` it's
        just the tritone pair.
    """
    step = E_CYCLES[cycle]
    pc = _to_pc(start)
    length = CYCLE_LENGTHS[cycle]
    return [(pc + step * i) % 12 for i in range(length)]


def cycle_root_names(
    cycle: CycleId,
    start: str | int = "C",
    *,
    style: Literal["sharp", "flat", "auto"] = "auto",
) -> list[str]:
    """Same as :func:`cycle_root_pcs` but returns note-name strings.

    Args:
        style: spelling preference. ``"sharp"`` always picks ``"C#"``,
               ``"flat"`` picks ``"Db"``, ``"auto"`` picks flats for
               cycles that descend by 4ths (E5) and sharps everywhere
               else, matching how Murphy/Greene typically notate them.
    """
    pcs = cycle_root_pcs(cycle, start)
    if style == "auto":
        names = _NOTE_NAMES_FLAT if cycle == "E5" else _NOTE_NAMES_SHARP
    elif style == "flat":
        names = _NOTE_NAMES_FLAT
    else:
        names = _NOTE_NAMES_SHARP
    return [names[pc] for pc in pcs]


# ---------------------------------------------------------------------------
# Root-line generation
# ---------------------------------------------------------------------------


def pick_root_line(
    length: int,
    cycles: list[CycleId] | None = None,
    *,
    start_root: str | int = "C",
    allow_elision: bool = True,
    seed: int | None = None,
) -> list[str]:
    """Generate a sequence of Root tones of the requested length.

    Strategy:

    1. Pick the first cycle in ``cycles`` (default ``["E5"]`` — the
       circle of fourths, the most common EIS Root-line generator).
    2. Walk the cycle one step at a time until we've produced
       ``length`` Roots.
    3. If multiple cycles are supplied, switch cycles every time the
       current cycle completes (and ``allow_elision`` permits it).
    4. With ``allow_elision=True`` the walker may skip one or two
       Roots when crossing into a new cycle — this is the EIS
       "elision" idiom that lets the bass briefly arrive on a Root
       that wasn't reached by the previous cycle.

    Args:
        length:        How many Root tones to produce. Must be > 0.
        cycles:        Order of cycles to consume. Defaults to ``["E5"]``.
        start_root:    Note name or pitch class (default ``"C"``).
        allow_elision: Permit 1- or 2-step skips at cycle boundaries.
        seed:          RNG seed for the elision choice (deterministic
                       output when set).

    Returns:
        A list of note-name strings (sharp/flat spelling auto-picked
        per cycle).

    Raises:
        ValueError: if ``length < 1`` or ``cycles`` contains an unknown id.
    """
    if length < 1:
        raise ValueError(f"length must be >= 1; got {length}")
    cycles = cycles or ["E5"]
    for c in cycles:
        if c not in E_CYCLES:
            raise ValueError(f"unknown cycle {c!r}; valid: {sorted(E_CYCLES)}")

    rng = random.Random(seed)
    out: list[str] = []
    current_pc = _to_pc(start_root)
    cycle_idx = 0

    while len(out) < length:
        cycle = cycles[cycle_idx % len(cycles)]
        step = E_CYCLES[cycle]
        cycle_len = CYCLE_LENGTHS[cycle]
        names = _NOTE_NAMES_FLAT if cycle == "E5" else _NOTE_NAMES_SHARP

        # Walk this cycle until either we've produced enough Roots OR
        # we've completed one full revolution and need to switch.
        steps_taken = 0
        while len(out) < length and steps_taken < cycle_len:
            out.append(names[current_pc])
            current_pc = (current_pc + step) % 12
            steps_taken += 1

        # If we still need more, advance to the next cycle (and maybe elide).
        if len(out) < length and len(cycles) > 1:
            cycle_idx += 1
            if allow_elision:
                elide = rng.choice([0, 1, 2])
                next_step = E_CYCLES[cycles[cycle_idx % len(cycles)]]
                current_pc = (current_pc + elide * next_step) % 12

    return out


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def is_valid_progression(
    roots: list[str | int],
    *,
    allowed_cycles: list[CycleId] | None = None,
) -> bool:
    """True iff every adjacent Root pair belongs to one of the allowed cycles.

    Inversions count: for example, ``C → G`` (a P5 up = 7 semitones)
    is valid in ``E5`` even though E5's canonical step is 5 (a P4),
    because P5 is the inversion of P4 modulo the octave.
    """
    if len(roots) < 2:
        return True
    allowed = set(allowed_cycles or list(E_CYCLES.keys()))
    pcs = [_to_pc(r) for r in roots]
    for prev, curr in pairwise(pcs):
        diff = (curr - prev) % 12
        # Match against either the canonical step or its inversion.
        if not any(
            diff == E_CYCLES[c] or diff == (-E_CYCLES[c]) % 12
            for c in allowed
        ):
            return False
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_pc(value: str | int) -> int:
    """Coerce a note name or pitch class to a 0..11 integer."""
    if isinstance(value, int):
        return value % 12
    if value not in _PC_OF_NAME:
        raise ValueError(
            f"unknown note name: {value!r}. "
            f"Use one of {sorted(_PC_OF_NAME)}."
        )
    return _PC_OF_NAME[value]
