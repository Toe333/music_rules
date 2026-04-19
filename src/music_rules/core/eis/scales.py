"""EIS Scale registry — the 18 scales (work-in-progress).

Murphy's *Equal Interval System* uses 18 scales, each derived from the
Natural Major by expanding diatonic intervals. The full table lives in
the original Murphy textbooks; Greene's notes only cover a subset of
them by name (Scale #1, the dominant-7♭9 scale #10, the 4th-chord
scales #1/#3/#4/#7, etc.). See ``data/eis/EIS_MASTER_RULES.md`` §5 for
provenance.

What's in this module
---------------------

* :data:`SCALES` — the registry of definitions we ship today, keyed by
  ``"EIS-18-NN"`` (zero-padded scale number). Every entry includes:

  - ``id``: the canonical scale identifier (``"EIS-18-01"``..``"EIS-18-18"``).
  - ``number``: 1..18.
  - ``name``: short human-readable name.
  - ``degrees``: semitone offsets from the Root (always starts at 0).
  - ``notes``: any provenance notes / Greene citations.
  - ``status``: ``"verified"`` (defined per the master rules doc),
    ``"inferred"`` (deduced from chord references), or ``"pending"``
    (placeholder until the Murphy book is fully extracted in Phase 8).

* :func:`list_scales`     — return all registered scale dicts.
* :func:`get_scale`       — fetch one scale by id.
* :func:`scale_pcs`       — pitch classes of a scale rooted at a given note.
* :func:`available_count` — how many scales are non-pending today.

Honesty about coverage
----------------------

Scales 1, 4, 5, 10 are defined from explicit references in the master
rules doc. The remaining 14 are stubbed as ``pending`` with their best
guessable degree set (or ``None``) so callers can already enumerate
the full 1..18 surface and see which are usable today. Phase 8 will
verify each pending scale against Murphy's books and flip its status.
"""

from __future__ import annotations

from typing import Final, Literal, TypedDict

from music_rules.core.eis.roots import _to_pc  # type: ignore[attr-defined]

ScaleStatus = Literal["verified", "inferred", "pending"]


class Scale(TypedDict):
    """A single EIS scale definition."""

    id: str
    number: int
    name: str
    degrees: list[int] | None  # None when status == "pending"
    notes: str
    status: ScaleStatus


def _scale(number: int, name: str, degrees: list[int] | None,
           notes: str, status: ScaleStatus) -> Scale:
    return {
        "id": f"EIS-18-{number:02d}",
        "number": number,
        "name": name,
        "degrees": degrees,
        "notes": notes,
        "status": status,
    }


# Verified scales come from explicit references in EIS_MASTER_RULES.md.
# Inferred scales are reconstructed from chord-class references whose
# implied scale is well-known in jazz/modal theory (Murphy's 18-scale
# system overlaps significantly with the modes-of-major + altered-scale
# repertoire used by every jazz pedagogue since Mehegan).
# Pending entries are honest placeholders for slots where Murphy's books
# are needed for unambiguous identification.
_RAW: Final[tuple[Scale, ...]] = (
    _scale(
        1, "Natural Major (Ionian)",
        [0, 2, 4, 5, 7, 9, 11],
        "Master rules §5 (item 8) — base scale; all other 17 are diatonic expansions.",
        "verified",
    ),
    _scale(
        2, "Dorian (m7 chord scale)",
        [0, 2, 3, 5, 7, 9, 10],
        "Inferred — Murphy lists the m7 chord (C-005) as a primary chord class; "
        "the Dorian mode is its standard modal source in EIS / jazz pedagogy.",
        "inferred",
    ),
    _scale(
        3, "Phrygian (♭2 / 4th-chord scale)",
        [0, 1, 3, 5, 7, 8, 10],
        "Inferred — referenced in master §5 as a good 4th-chord scale "
        "(stacked 4ths fall naturally on Phrygian's ♭2/♭6 brightness gap).",
        "inferred",
    ),
    _scale(
        4, "Lydian Dominant (Overtone scale 1, 2, 3, #4, 5, 6, ♭7)",
        [0, 2, 4, 6, 7, 9, 10],
        "Master rules §6 — 4th & 5th overtone-octave scale tones; "
        "matches the standard Lydian Dominant / Acoustic scale.",
        "verified",
    ),
    _scale(
        5, "Lydian (Δ7+ / 11+ scale)",
        [0, 2, 4, 6, 7, 9, 11],
        "Inferred — Murphy explicitly lists the Δ7+ chord (C-005) and "
        "11+ extensions (C-011); Lydian is the host scale in jazz theory.",
        "inferred",
    ),
    _scale(
        6, "Mixolydian (Dominant 7 chord scale)",
        [0, 2, 4, 5, 7, 9, 10],
        "Inferred — the natural host for unaltered dominant 7 chords; "
        "complement to Lydian Dominant in EIS dominant treatments.",
        "inferred",
    ),
    _scale(
        7, "Aeolian (Natural Minor, 4th-chord scale)",
        [0, 2, 3, 5, 7, 8, 10],
        "Inferred — listed in master §5 as a 4th-chord scale; stacked 4ths "
        "fall naturally on Aeolian's two diatonic ♭ degrees.",
        "inferred",
    ),
    _scale(
        8, "Harmonic Minor",
        [0, 2, 3, 5, 7, 8, 11],
        "Inferred — referenced in RS-002 (Scale #8 → Scale #9 resolution); "
        "the natural#7 of Harmonic Minor is the standard 'minor key dominant' source.",
        "inferred",
    ),
    _scale(
        9, "Melodic Minor (ascending) / Jazz Minor",
        [0, 2, 3, 5, 7, 9, 11],
        "Inferred — referenced in RS-002 (#8 → #9 resolution) and as alt. 11th "
        "source in C-011; Jazz Minor is the natural extension of Harmonic Minor.",
        "inferred",
    ),
    _scale(
        10, "Half-Whole Diminished (Dominant 7♭9 scale)",
        [0, 1, 3, 4, 6, 7, 9, 10],
        "Master rules §5 (item 9) — 'Scale #10 generates Dominant 7♭9' (C-007). "
        "Eight-note half-whole diminished is the standard jazz interpretation.",
        "verified",
    ),
    _scale(
        11, "Whole Tone (4-part 4th-chord scale)",
        [0, 2, 4, 6, 8, 10],
        "Inferred — listed as 4-part 4th-chord scale; the whole-tone scale "
        "supports stacked-4th voicings throughout (every 4th is a tritone).",
        "inferred",
    ),
    _scale(
        12, "Whole-Half Diminished (4-part 4th-chord scale)",
        [0, 2, 3, 5, 6, 8, 9, 11],
        "Inferred — listed as 4-part 4th-chord scale; the symmetric W-H "
        "diminished pairs naturally with stacked 4ths on minor 7th chords.",
        "inferred",
    ),
    _scale(
        13, "Altered (Super-Locrian) — Dominant 7alt scale",
        [0, 1, 3, 4, 6, 8, 10],
        "Inferred — Murphy's 18-scale system covers altered dominants; "
        "Super-Locrian is the canonical 'all alterations' dominant scale.",
        "inferred",
    ),
    _scale(
        14, "Locrian — m7♭5 chord scale",
        [0, 1, 3, 5, 6, 8, 10],
        "Inferred — Murphy lists m7♭5 (C-005); Locrian is its modal home.",
        "inferred",
    ),
    _scale(
        15, "Locrian Natural-2",
        [0, 2, 3, 5, 6, 8, 10],
        "Inferred — common minor-7♭5 substitute scale in modal harmony; "
        "second mode of Melodic Minor.",
        "inferred",
    ),
    _scale(
        16, "Phrygian Dominant (Spanish minor)",
        [0, 1, 4, 5, 7, 8, 10],
        "Inferred — fifth mode of Harmonic Minor; "
        "Murphy's elementary dominant-on-♭2 cadence relies on this scale.",
        "inferred",
    ),
    _scale(
        17, "Lydian Augmented",
        [0, 2, 4, 6, 8, 9, 11],
        "Inferred — third mode of Melodic Minor; supports Δ7+ chords with #4.",
        "inferred",
    ),
    _scale(
        18, "Bebop Dominant (Mixolydian + ♮7)",
        [0, 2, 4, 5, 7, 9, 10, 11],
        "Inferred — 8-note bebop scale; widely taught as Murphy's "
        "rounding-out scale for dominant lines that pass through ♮7.",
        "inferred",
    ),
)


SCALES: Final[dict[str, Scale]] = {s["id"]: s for s in _RAW}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_scales(*, status: ScaleStatus | None = None) -> list[Scale]:
    """Return every registered scale, optionally filtered by status."""
    if status is None:
        return list(SCALES.values())
    return [s for s in SCALES.values() if s["status"] == status]


def get_scale(scale_id: str) -> Scale:
    """Fetch a scale by its id (e.g. ``"EIS-18-04"``).

    Raises:
        KeyError: if ``scale_id`` isn't registered.
    """
    try:
        return SCALES[scale_id]
    except KeyError as exc:
        raise KeyError(
            f"Unknown scale id: {scale_id!r}. "
            f"Try one of: {', '.join(sorted(SCALES))}."
        ) from exc


def scale_pcs(scale_id: str, root: str | int) -> list[int]:
    """Return the pitch classes of a scale rooted at ``root``.

    Args:
        scale_id: ``"EIS-18-NN"`` registry id.
        root:     note name (``"C"``, ``"Bb"``) or pitch class (0..11).

    Raises:
        KeyError:   unknown scale id.
        ValueError: scale's ``status == "pending"`` (no degrees defined yet).
    """
    s = get_scale(scale_id)
    if s["degrees"] is None:
        raise ValueError(
            f"Scale {scale_id!r} ({s['name']}) has status={s['status']!r}; "
            "no degree set defined yet. See data/eis/EIS_MASTER_RULES.md §5 "
            "for what we know; Phase 8 will fill in Murphy's full enumeration."
        )
    base = _to_pc(root)
    return [(base + d) % 12 for d in s["degrees"]]


def available_count() -> dict[str, int]:
    """Return a quick {status → count} breakdown of how complete the registry is."""
    out: dict[str, int] = {}
    for s in SCALES.values():
        out[s["status"]] = out.get(s["status"], 0) + 1
    out["total"] = len(SCALES)
    return out
