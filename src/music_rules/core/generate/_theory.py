"""Tiny music-theory helpers used by the generator modules.

Kept private (underscore prefix) because the canonical theory layer is
:mod:`music_rules.core.pitch`; this module only adds the
generator-specific conveniences (chord-symbol parsing for the small
vocabulary the bundled styles use, octave-snapping for register
control, scale name → pitch-class set).
"""

from __future__ import annotations

NOTE_TO_PC: dict[str, int] = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "Fb": 4,
    "E#": 5,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
    "Cb": 11,
    "B#": 0,
}

# Chord quality templates (root-relative semitone offsets).
# Includes triads, sevenths, ninth/eleventh/thirteenth extensions, and
# the common altered-dominant shapes. Pitch classes are reduced mod 12
# at use sites (parse_chord_symbol consumers), so leaving the upper
# extensions un-reduced here keeps the templates readable.
_CHORD_QUALITY_INTERVALS: dict[str, tuple[int, ...]] = {
    "": (0, 4, 7),
    "m": (0, 3, 7),
    "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
    "7": (0, 4, 7, 10),
    "7sus": (0, 5, 7, 10),
    "dim": (0, 3, 6),
    "dim7": (0, 3, 6, 9),
    "m7b5": (0, 3, 6, 10),
    "sus4": (0, 5, 7),
    "sus2": (0, 2, 7),
    "add9": (0, 4, 7, 14),
    "madd9": (0, 3, 7, 14),
    "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9),
    "9": (0, 4, 7, 10, 14),
    "maj9": (0, 4, 7, 11, 14),
    "m9": (0, 3, 7, 10, 14),
    "11": (0, 4, 7, 10, 14, 17),
    "m11": (0, 3, 7, 10, 14, 17),
    "maj11": (0, 4, 7, 11, 14, 17),
    "13": (0, 4, 7, 10, 14, 21),
    "maj13": (0, 4, 7, 11, 14, 21),
    "m13": (0, 3, 7, 10, 14, 21),
    "7b9": (0, 4, 7, 10, 13),
    "7#9": (0, 4, 7, 10, 15),
    "7b5": (0, 4, 6, 10),
    "7#5": (0, 4, 8, 10),
    "7alt": (0, 4, 8, 10, 13),
    "aug": (0, 4, 8),
    "+": (0, 4, 8),
}


def note_to_pc(note: str) -> int:
    """Map ``"C"``, ``"Eb"``, ... to its pitch class in [0, 12)."""
    try:
        return NOTE_TO_PC[note]
    except KeyError as exc:
        raise ValueError(f"unknown note name: {note!r}") from exc


def parse_chord_symbol(symbol: str) -> tuple[int, tuple[int, ...]]:
    """Parse e.g. ``"Am"`` → (root_pc, semitone_offsets_from_root).

    Only handles the small vocabulary used by the bundled style profiles.
    Raises ``ValueError`` for unknown roots or qualities.
    """
    if not symbol:
        raise ValueError("empty chord symbol")
    if len(symbol) >= 2 and symbol[1] in "b#":
        root, rest = symbol[:2], symbol[2:]
    else:
        root, rest = symbol[:1], symbol[1:]
    try:
        intervals = _CHORD_QUALITY_INTERVALS[rest]
    except KeyError as exc:
        raise ValueError(f"unknown chord quality: {rest!r} in {symbol!r}") from exc
    return note_to_pc(root), intervals


def chord_tone_pcs(symbol: str) -> set[int]:
    """Pitch-class set of the chord's notes (root + quality offsets)."""
    root_pc, intervals = parse_chord_symbol(symbol)
    return {(root_pc + semi) % 12 for semi in intervals}


def scale_pcs(scale_names: list[str]) -> set[int]:
    """Pitch-class set built from an explicit list of note names."""
    return {note_to_pc(n) for n in scale_names}


def midi_in_octave(pc: int, octave: int) -> int:
    """Return the MIDI number of pitch-class ``pc`` in the given octave.

    Octave numbering follows the common MIDI convention where C4 = 60
    (so ``midi_in_octave(0, 4) == 60``).
    """
    return pc + 12 * (octave + 1)


def snap_pc_near(pc: int, reference_midi: int) -> int:
    """Pick the MIDI register of ``pc`` closest to ``reference_midi``.

    Used to keep walking-bass lines and lead phrases from jumping
    multiple octaves between adjacent notes.
    """
    base = (reference_midi // 12) * 12 + pc
    candidates = (base - 12, base, base + 12)
    return min(candidates, key=lambda m: abs(m - reference_midi))
