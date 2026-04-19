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
# implied scale is well-known in jazz theory.
# Pending entries are honest placeholders; they preserve the 1..18 surface
# without inventing data.
_RAW: Final[tuple[Scale, ...]] = (
    _scale(
        1, "Natural Major (Ionian)",
        [0, 2, 4, 5, 7, 9, 11],
        "Master rules §5 (item 8) — base scale; all other 17 are diatonic expansions.",
        "verified",
    ),
    _scale(
        2, "Scale #2 (pending Murphy book extraction)",
        None,
        "Greene notes don't enumerate; awaiting Murphy book #2 verification.",
        "pending",
    ),
    _scale(
        3, "Scale #3 (4th-chord scale, pending verification)",
        None,
        "Referenced in master §5 as a good 4th-chord scale and in C-009.",
        "pending",
    ),
    _scale(
        4, "Overtone Scale Tones — 1, 2, 3, #4, 5, 6, ♭7 (Lydian Dominant)",
        [0, 2, 4, 6, 7, 9, 10],
        "Master rules §6 — 4th & 5th overtone-octave scale tones; "
        "matches the standard Lydian Dominant / Acoustic scale.",
        "verified",
    ),
    _scale(
        5, "Overtone Scale Tones (duplicate of #4 in master rules §6)",
        [0, 2, 4, 6, 7, 9, 10],
        "Master rules §6 lists identical degrees as #4; treated as the same "
        "scale degree-wise here. Murphy may distinguish by harmonization.",
        "inferred",
    ),
    _scale(6, "Scale #6 (pending)", None, "Awaiting Murphy book extraction.", "pending"),
    _scale(
        7, "Scale #7 (4th-chord scale, pending)", None,
        "Referenced as good 4th-chord scale in master §5.",
        "pending",
    ),
    _scale(8, "Scale #8 (pending)", None,
           "Referenced in RS-002 (Scale #8 → Scale #9 resolution).",
           "pending"),
    _scale(9, "Scale #9 (pending)", None,
           "Referenced in RS-002 and C-011 as alternative 11th source.",
           "pending"),
    _scale(
        10, "Dominant 7♭9 scale (Half-Whole Diminished)",
        [0, 1, 3, 4, 6, 7, 9, 10],
        "Master rules §5 (item 9) — 'Scale #10 generates Dominant 7♭9' (C-007). "
        "Eight-note half-whole diminished is the standard jazz interpretation.",
        "verified",
    ),
    _scale(11, "Scale #11 (4-part 4th-chord scale, pending)",
           None, "Referenced as a 4-part 4th-chord scale in master §5.",
           "pending"),
    _scale(12, "Scale #12 (4-part 4th-chord scale, pending)",
           None, "Referenced as a 4-part 4th-chord scale in master §5.",
           "pending"),
    _scale(13, "Scale #13 (pending)", None, "Awaiting verification.", "pending"),
    _scale(14, "Scale #14 (pending)", None, "Awaiting verification.", "pending"),
    _scale(15, "Scale #15 (pending)", None, "Awaiting verification.", "pending"),
    _scale(16, "Scale #16 (pending)", None, "Awaiting verification.", "pending"),
    _scale(17, "Scale #17 (pending)", None, "Awaiting verification.", "pending"),
    _scale(18, "Scale #18 (pending)", None, "Awaiting verification.", "pending"),
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
