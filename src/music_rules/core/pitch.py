"""Pitch and interval primitives used by every checker.

Pure standard library — no ``music21``, no ``mido`` (the latter only
shows up in ``core.midi.io`` for actual MIDI byte I/O).

Conventions
-----------

* MIDI numbers are integers, 0..127, where 60 = middle C, 69 = A440.
* "Semitones" always means the **absolute difference** between two MIDI
  numbers (so a major third is 4 semitones, never -4).
* "Signed semitones" are used when direction matters (motion type,
  ascending vs descending leaps); positive = ascending.
* "Interval class" is the simple-interval name (P1, m2, M2, ..., M7, P8)
  reduced modulo 12 to the octave 0..11. P1 and P8 collide on 0; the
  caller decides whether the unison/octave distinction matters.

Why this exists
---------------

Every Fux (and several EIS) rules need answers to questions like
"is this a perfect consonance?" or "is this leap larger than a minor
sixth?" Centralizing those judgments here keeps the checker code
focused on the *rule* rather than re-deriving interval taxonomy.
"""

from __future__ import annotations

from typing import Final, Literal

# ---------------------------------------------------------------------------
# Interval taxonomy
# ---------------------------------------------------------------------------

INTERVAL_NAMES: Final[dict[int, str]] = {
    0: "P1",
    1: "m2",
    2: "M2",
    3: "m3",
    4: "M3",
    5: "P4",
    6: "TT",  # tritone (A4 / d5)
    7: "P5",
    8: "m6",
    9: "M6",
    10: "m7",
    11: "M7",
    12: "P8",
}

# Perfect consonances (the "do not approach by direct/similar motion" set).
# P1 and P8 are functionally equivalent here.
PERFECT_CONSONANCES: Final[frozenset[int]] = frozenset({0, 7, 12})

# Imperfect consonances. Major/minor 3rds and 6ths.
IMPERFECT_CONSONANCES: Final[frozenset[int]] = frozenset({3, 4, 8, 9})

# Strict-Fux dissonances in two-voice species 1: anything not in
# (perfect | imperfect). Notably P4 IS dissonant in 2v Fuxian writing.
DISSONANT_INTERVALS: Final[frozenset[int]] = frozenset({1, 2, 5, 6, 10, 11})

# The minor-sixth ceiling for melodic leaps (M1_1_2v in FuxCP5).
MAX_MELODIC_LEAP_SEMITONES: Final[int] = 8  # m6 = 8 semitones
OCTAVE: Final[int] = 12

ConsonanceClass = Literal["perfect", "imperfect", "dissonant"]
MotionType = Literal["parallel", "similar", "contrary", "oblique"]


# ---------------------------------------------------------------------------
# Single-interval queries
# ---------------------------------------------------------------------------


def semitones_between(a: int, b: int) -> int:
    """Absolute semitone distance between two MIDI numbers."""
    return abs(b - a)


def signed_semitones(prev: int, curr: int) -> int:
    """Signed semitone delta; positive = ascending, negative = descending."""
    return curr - prev


def reduce_to_octave(semitones: int) -> int:
    """Reduce an interval to its simple form within the octave (0..12).

    Treats the octave (12) and any compound octave (24, 36, ...) as 12,
    not 0, so we can distinguish "unison" from "octave" downstream when
    the caller cares.
    """
    s = abs(semitones)
    if s == 0:
        return 0
    reduced = s % OCTAVE
    if reduced == 0:
        return OCTAVE
    return reduced


def interval_name(semitones: int) -> str:
    """Human-readable name for an interval (e.g. ``'M3'``, ``'TT'``, ``'P8'``)."""
    reduced = reduce_to_octave(semitones)
    return INTERVAL_NAMES[reduced]


def classify_consonance(semitones: int) -> ConsonanceClass:
    """Return ``'perfect'`` | ``'imperfect'`` | ``'dissonant'`` for an interval."""
    reduced = reduce_to_octave(semitones)
    if reduced in PERFECT_CONSONANCES or reduced == 0:
        return "perfect"
    if reduced in IMPERFECT_CONSONANCES:
        return "imperfect"
    return "dissonant"


def is_perfect_consonance(semitones: int) -> bool:
    return classify_consonance(semitones) == "perfect"


def is_imperfect_consonance(semitones: int) -> bool:
    return classify_consonance(semitones) == "imperfect"


def is_consonance(semitones: int) -> bool:
    """True iff the interval is a Fuxian-strict consonance.

    Per Fux's *Gradus ad Parnassum* in 2-voice writing, P4 is treated as
    a dissonance (it only becomes a consonance in 3+ voices when properly
    supported by a lower voice). :data:`DISSONANT_INTERVALS` therefore
    includes 5 (P4); see :func:`is_consonance_in_context` for the
    voice-count-aware version.
    """
    return classify_consonance(semitones) != "dissonant"


def is_consonance_in_context(semitones: int, *, voice_count: int) -> bool:
    """True iff the interval is consonant *in the given voice-count context*.

    The only difference from :func:`is_consonance` is the P4: dissonant
    in 2-voice writing, consonant in 3-or-more-voice writing.
    """
    if voice_count >= 3 and is_p4(semitones):
        return True
    return is_consonance(semitones)


def is_dissonance(semitones: int) -> bool:
    return classify_consonance(semitones) == "dissonant"


def is_tritone(semitones: int) -> bool:
    return reduce_to_octave(semitones) == 6


def is_p4(semitones: int) -> bool:
    return reduce_to_octave(semitones) == 5


# ---------------------------------------------------------------------------
# Motion classification (for check_motion_pair, P1_*, P3_*, P6_*)
# ---------------------------------------------------------------------------


def classify_motion(cf_prev: int, cf_curr: int, cp_prev: int, cp_curr: int) -> MotionType:
    """Classify two-voice motion between two adjacent verticalities.

    Args:
        cf_prev, cf_curr: cantus-firmus voice MIDI before and after.
        cp_prev, cp_curr: counterpoint voice MIDI before and after.

    Returns:
        ``'parallel'``  — both voices move the same direction by the same interval.
        ``'similar'``   — both voices move the same direction (different intervals).
        ``'contrary'``  — voices move in opposite directions.
        ``'oblique'``   — one voice stays, the other moves.

    Both voices stationary returns ``'oblique'`` (vacuously — no motion to classify).
    """
    cf_delta = signed_semitones(cf_prev, cf_curr)
    cp_delta = signed_semitones(cp_prev, cp_curr)

    if cf_delta == 0 or cp_delta == 0:
        return "oblique"
    if (cf_delta > 0) == (cp_delta > 0):
        # Same direction
        return "parallel" if cf_delta == cp_delta else "similar"
    return "contrary"


def is_stepwise(prev: int, curr: int) -> bool:
    """True iff the melodic interval is a half- or whole-step."""
    return semitones_between(prev, curr) in {1, 2}


# ---------------------------------------------------------------------------
# Key / scale membership (used by G4 — borrowed-note check)
# ---------------------------------------------------------------------------

# Major scale pitch classes relative to tonic (no modal adjustments — Fux
# operates in modal church-tone scales, but for borrowed-note detection
# vs the main key we use the major/minor diatonic set).
_MAJOR_DIATONIC: Final[frozenset[int]] = frozenset({0, 2, 4, 5, 7, 9, 11})
_NATURAL_MINOR_DIATONIC: Final[frozenset[int]] = frozenset({0, 2, 3, 5, 7, 8, 10})

NOTE_NAMES_SHARP: Final[tuple[str, ...]] = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)
NOTE_NAMES_FLAT: Final[tuple[str, ...]] = (
    "C",
    "Db",
    "D",
    "Eb",
    "E",
    "F",
    "Gb",
    "G",
    "Ab",
    "A",
    "Bb",
    "B",
)


def pitch_class(midi: int) -> int:
    """Pitch class 0..11 for a MIDI number."""
    return midi % 12


def name_pitch(midi: int, *, prefer_flats: bool = False) -> str:
    """Human-readable pitch name with octave (e.g. ``'C4'``, ``'F#5'``)."""
    pc = pitch_class(midi)
    octave = midi // 12 - 1
    table = NOTE_NAMES_FLAT if prefer_flats else NOTE_NAMES_SHARP
    return f"{table[pc]}{octave}"


def parse_key(key: str) -> tuple[int, Literal["major", "minor"]]:
    """Parse a key string like ``'C'``, ``'D minor'``, ``'F# major'``.

    Returns ``(tonic_pitch_class, mode)``. Raises ``ValueError`` on bad input.
    """
    s = key.strip()
    if not s:
        raise ValueError("Empty key string")

    parts = s.replace("-", " ").split()
    name = parts[0]
    mode_str = parts[1].lower() if len(parts) > 1 else "major"
    if mode_str.startswith("maj"):
        mode: Literal["major", "minor"] = "major"
    elif mode_str.startswith("min"):
        mode = "minor"
    else:
        raise ValueError(f"Unknown mode {mode_str!r} in key {key!r}")

    name_norm = name[0].upper() + (name[1:] if len(name) > 1 else "")
    if name_norm in NOTE_NAMES_SHARP:
        tonic = NOTE_NAMES_SHARP.index(name_norm)
    elif name_norm in NOTE_NAMES_FLAT:
        tonic = NOTE_NAMES_FLAT.index(name_norm)
    else:
        raise ValueError(f"Unknown note name {name!r} in key {key!r}")

    return tonic, mode


def in_key(midi: int, key: str) -> bool:
    """True iff the pitch belongs to the diatonic collection of the given key.

    For Fuxian writing this is a simple diatonic check; modal accidentals
    (raised 7th in melodic minor, etc.) are out of scope here — the
    G4 "borrowed note" rule deliberately treats raised leading tones as
    out-of-key and lets the soft cost capture them.
    """
    tonic, mode = parse_key(key)
    diatonic = _MAJOR_DIATONIC if mode == "major" else _NATURAL_MINOR_DIATONIC
    return ((midi - tonic) % 12) in diatonic
