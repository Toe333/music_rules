"""EIS chord construction.

Murphy's *Equal Interval System* builds every chord from three inputs:

1. A **Root** (any of the 12 pitch classes).
2. A **chord class** (triad, 7th, 9th, dominant 7♭9, 4th-chord stack, …).
3. A **voicing**: parts (2P / 3P / 4P / 5P), close vs open, inversion,
   base octave.

The Root and chord-class together fix the abstract pitch-class set; the
voicing renders that set as actual MIDI numbers.

A **scale** travels alongside the chord (the EIS principle that "a chord
is a set of tones drawn from one scale" — master rules §6 item 9), but
its job is to define the *melodic palette* available over the chord
(see :mod:`music_rules.core.eis.nct` for non-chord-tone use). The
chord-tone recipe itself is fixed in semitone-offsets from the Root,
because alterations like ♭9 cross scale boundaries and would be
ambiguous otherwise.

Public API
----------

* :data:`CHORD_CLASSES` — registry of supported chord classes.
* :func:`pitch_classes`  — abstract pc set for a chord (no octave).
* :func:`build_chord`    — fully voiced MIDI numbers (close/open,
  parts, inversion, base octave).
* :func:`list_chord_classes` — discoverability for MCP / OpenAI clients.

Each class carries a ``rule_ref`` pointing back into the corpus
(``C-001``..``C-012``, ``A-004`` for polytonal, ``GEN-quartal-*`` for
4th-chords).
"""

from __future__ import annotations

from typing import Final, Literal, TypedDict

from music_rules.core.eis.roots import _to_pc  # type: ignore[attr-defined]
from music_rules.core.eis.scales import get_scale

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


Voicing = Literal["close", "open"]


class ChordClass(TypedDict):
    """A single EIS chord-class definition.

    * ``id``           — short name (``"triad"``, ``"dom7"``, …).
    * ``parts``        — supported part-counts (2P / 3P / 4P / 5P).
    * ``intervals``    — semitone offsets from the Root (0 = root). Each
                         value is in 0..23 so we can express ♭9 (13) and
                         13 (21) without ambiguity. The voicer wraps
                         them down to one octave when stacking.
    * ``implied_scale`` — recommended EIS scale id for melodic / NCT
                         derivation (advisory, not enforced).
    * ``quality``       — ``"major"`` / ``"minor"`` / ``"dominant"`` /
                         ``"quartal"`` / ``"polytonal"``. Used by the
                         voice-leader to pick chord-aware moves.
    * ``rule_ref``      — corresponding ``C-NNN`` rule id.
    * ``description``   — human-readable summary.
    """

    id: str
    parts: list[int]
    intervals: list[int]
    implied_scale: str
    quality: str
    rule_ref: str
    description: str


# ---------------------------------------------------------------------------
# Chord-class registry
# ---------------------------------------------------------------------------


# Intervals are semitones above the Root. Numbers > 11 (♭9, 9, 11, 13)
# produce upper-octave tones; the voicer wraps them as needed.
_CLASSES: Final[tuple[ChordClass, ...]] = (
    {
        "id": "triad",
        "parts": [3],
        "intervals": [0, 4, 7],
        "implied_scale": "EIS-18-01",
        "quality": "major",
        "rule_ref": "C-001",
        "description": "Major triad (1, 3, 5).",
    },
    {
        "id": "triad-min",
        "parts": [3],
        "intervals": [0, 3, 7],
        "implied_scale": "EIS-18-01",
        "quality": "minor",
        "rule_ref": "C-001",
        "description": "Minor triad (1, ♭3, 5).",
    },
    {
        "id": "triad-7",
        "parts": [4],
        "intervals": [0, 4, 7, 11],
        "implied_scale": "EIS-18-01",
        "quality": "major",
        "rule_ref": "C-002",
        "description": "Natural 7th (Δ7) — major triad + natural 7.",
    },
    {
        "id": "triad-min-7",
        "parts": [4],
        "intervals": [0, 3, 7, 11],
        "implied_scale": "EIS-18-01",
        "quality": "minor",
        "rule_ref": "C-002",
        "description": "Minor-major 7th (mΔ7).",
    },
    {
        "id": "9",
        "parts": [4, 5],
        "intervals": [0, 4, 7, 11, 14],
        "implied_scale": "EIS-18-01",
        "quality": "major",
        "rule_ref": "C-003",
        "description": "Major 9th (Δ9). 4P drops the 5.",
    },
    {
        "id": "6",
        "parts": [4],
        "intervals": [0, 4, 7, 9],
        "implied_scale": "EIS-18-01",
        "quality": "major",
        "rule_ref": "C-003",
        "description": "6th chord (1, 3, 5, 6) — substitutes 6 for 7.",
    },
    {
        "id": "dom7",
        "parts": [3, 4],
        "intervals": [0, 4, 7, 10],
        "implied_scale": "EIS-18-04",   # Lydian Dominant pairs naturally
        "quality": "dominant",
        "rule_ref": "C-004",
        "description": "Dominant 7 (1, 3, 5, ♭7). 3P drops the 5.",
    },
    {
        "id": "min7",
        "parts": [3, 4],
        "intervals": [0, 3, 7, 10],
        "implied_scale": "EIS-18-01",
        "quality": "minor",
        "rule_ref": "C-005",
        "description": "Minor 7 (1, ♭3, 5, ♭7).",
    },
    {
        "id": "min7b5",
        "parts": [4],
        "intervals": [0, 3, 6, 10],
        "implied_scale": "EIS-18-01",
        "quality": "minor",
        "rule_ref": "C-005",
        "description": "Half-diminished — minor 7 with ♭5.",
    },
    {
        "id": "min9",
        "parts": [4, 5],
        "intervals": [0, 3, 7, 10, 14],
        "implied_scale": "EIS-18-01",
        "quality": "minor",
        "rule_ref": "C-006",
        "description": "Minor 9th. 4P drops the 5.",
    },
    {
        "id": "dom7b9",
        "parts": [4, 5],
        "intervals": [0, 4, 7, 10, 13],
        "implied_scale": "EIS-18-10",
        "quality": "dominant",
        "rule_ref": "C-007",
        "description": "Dominant 7♭9 — generated from Scale #10 melodically.",
    },
    {
        "id": "dom9",
        "parts": [4, 5],
        "intervals": [0, 4, 7, 10, 14],
        "implied_scale": "EIS-18-04",
        "quality": "dominant",
        "rule_ref": "C-008",
        "description": "Dominant 9th. 4P drops the 5; 6 may substitute for ♭7.",
    },
    {
        "id": "dom13",
        "parts": [4, 5],
        "intervals": [0, 4, 7, 10, 14, 21],
        "implied_scale": "EIS-18-04",
        "quality": "dominant",
        "rule_ref": "C-009",
        "description": (
            "Dominant 13. Use scales #1, #3, #4, #7, #8, #9, #10, #11. "
            "Constraint: only ♭10 with 11, or natural 10 with 11+."
        ),
    },
    {
        "id": "dom11",
        "parts": [4, 5],
        "intervals": [0, 4, 7, 10, 17],
        "implied_scale": "EIS-18-09",
        "quality": "dominant",
        "rule_ref": "C-011",
        "description": (
            "Dominant 11. The 11+ variant uses Lydian Dominant (Scale #4)."
        ),
    },
    {
        "id": "4th-3p",
        "parts": [3],
        "intervals": [0, 5, 10],
        "implied_scale": "EIS-18-01",
        "quality": "quartal",
        "rule_ref": "GEN-quartal-3p",
        "description": (
            "3-part 4th-chord (quartal stack). Scales 1, 3, 4, 7 work best."
        ),
    },
    {
        "id": "4th-4p",
        "parts": [4],
        "intervals": [0, 5, 10, 15],
        "implied_scale": "EIS-18-01",
        "quality": "quartal",
        "rule_ref": "GEN-quartal-4p",
        "description": (
            "4-part 4th-chord. Scales 11, 12 (or extension of #1, #3, #7)."
        ),
    },
    {
        "id": "polytonal",
        "parts": [5, 6],
        "intervals": [0, 4, 7, 14, 18, 21],
        "implied_scale": "EIS-18-01",
        "quality": "polytonal",
        "rule_ref": "A-004",
        "description": (
            "Polytonal stack — two superimposed triads. Advanced; the "
            "voicer distributes the 6 tones across two octaves."
        ),
    },
)


CHORD_CLASSES: Final[dict[str, ChordClass]] = {c["id"]: c for c in _CLASSES}


# ---------------------------------------------------------------------------
# Pitch-class derivation
# ---------------------------------------------------------------------------


def pitch_classes(
    root: str | int,
    chord_class: str,
    *,
    scale_id: str | None = None,
) -> list[int]:
    """Return the pitch-class set for a chord (no octave information).

    Args:
        root:         note name (``"C"``) or pitch class (0..11).
        chord_class:  one of the keys in :data:`CHORD_CLASSES`.
        scale_id:     optional scale override. Most chord classes ignore
                      this (their intervals are scale-independent), but
                      we validate its existence so callers see a clear
                      error if they typo a scale id.

    Returns:
        Pitch classes in build order, 0..11. Each pc appears once
        (we deduplicate while preserving first-seen order).
    """
    if chord_class not in CHORD_CLASSES:
        raise KeyError(
            f"Unknown chord_class {chord_class!r}. "
            f"Valid: {sorted(CHORD_CLASSES)}."
        )
    if scale_id is not None:
        # Validate the scale id even though we don't consume its degrees.
        # A pending scale is fine here — the chord intervals stand alone.
        get_scale(scale_id)

    base_pc = _to_pc(root)
    cls = CHORD_CLASSES[chord_class]
    out: list[int] = []
    for st in cls["intervals"]:
        pc = (base_pc + st) % 12
        if pc not in out:
            out.append(pc)
    return out


# ---------------------------------------------------------------------------
# Voicing
# ---------------------------------------------------------------------------


def build_chord(
    root: str | int,
    chord_class: str,
    *,
    scale_id: str | None = None,
    parts: int | None = None,
    voicing: Voicing = "close",
    inversion: int = 0,
    base_octave: int = 4,
) -> list[int]:
    """Return a list of MIDI numbers for a fully voiced chord.

    Args:
        root:         starting note (name or pc).
        chord_class:  chord-class id from :data:`CHORD_CLASSES`.
        scale_id:     optional scale override (validated only).
        parts:        2P / 3P / 4P / 5P. Defaults to the smallest size
                      that the chord-class supports.
        voicing:      ``"close"`` (smallest spacing) or ``"open"``
                      (drop-2 — move the 2nd-from-top voice down an
                      octave; standard EIS / jazz open voicing).
        inversion:    0 (root in bass) … N-1 (top tone in bass).
        base_octave:  octave for the bass tone (4 = middle-C area).

    Returns:
        Sorted list of MIDI numbers (low → high), length ``== parts``.

    Raises:
        KeyError:   unknown ``chord_class``.
        ValueError: ``scale_id`` unknown / ``parts`` not supported /
                    ``inversion`` out of range.
    """
    cls = CHORD_CLASSES[chord_class]
    if parts is None:
        parts = cls["parts"][0]
    if parts not in cls["parts"]:
        raise ValueError(
            f"Chord class {chord_class!r} supports parts={cls['parts']}; "
            f"got {parts}."
        )

    intervals = list(cls["intervals"])

    # Apply EIS reductions when the recipe has more notes than parts.
    # Standard rule (master §16): drop the 5th first when reducing.
    if len(intervals) > parts:
        # Drop any "5th" tone (interval 7 from the root, or +12n).
        intervals = _drop_fifth(intervals, parts)
        # Then truncate from the top if still too many.
        intervals = intervals[:parts]
    while len(intervals) < parts:
        # Double the root if we're short (common in 5-part voicings).
        intervals.append(intervals[0])

    if not 0 <= inversion < parts:
        raise ValueError(
            f"inversion must be in 0..{parts - 1}; got {inversion}."
        )

    base_pc = _to_pc(root)
    midi = _stack_intervals(intervals, base_pc, base_octave)
    if inversion:
        midi = _invert(midi, inversion)
    if voicing == "open" and len(midi) >= 4:
        midi = _drop_2(midi)

    if scale_id is not None:
        get_scale(scale_id)  # validate

    return sorted(midi)


def list_chord_classes() -> list[ChordClass]:
    """Return every registered chord-class definition (for discovery)."""
    return list(CHORD_CLASSES.values())


# ---------------------------------------------------------------------------
# Internal voicing helpers
# ---------------------------------------------------------------------------


def _drop_fifth(intervals: list[int], target: int) -> list[int]:
    """Drop the chord's 5th if doing so brings us to the target part-count."""
    if len(intervals) - 1 < target:
        return intervals
    fifth_indices = [i for i, iv in enumerate(intervals) if iv % 12 == 7]
    if not fifth_indices:
        return intervals
    drop = fifth_indices[0]
    return intervals[:drop] + intervals[drop + 1:]


def _stack_intervals(intervals: list[int], base_pc: int, base_octave: int) -> list[int]:
    """Stack semitone offsets above the base MIDI note, ascending.

    Uses the standard scientific-pitch / GM convention: middle C is C4
    and lives at MIDI 60, so ``midi = (octave + 1) * 12 + pc``.
    """
    bass_midi = (base_octave + 1) * 12 + base_pc
    return [bass_midi + iv for iv in intervals]


def _invert(midi: list[int], inversion: int) -> list[int]:
    """Move the lowest ``inversion`` notes up an octave each."""
    out = list(midi)
    for i in range(inversion):
        out[i] = out[i] + 12
    return out


def _drop_2(close: list[int]) -> list[int]:
    """Apply 'drop-2' voicing: move the 2nd-from-top tone down an octave.

    The canonical EIS / jazz "open" treble voicing per master §16.
    """
    out = sorted(close)
    if len(out) < 4:
        return out
    out[-2] -= 12
    return sorted(out)
