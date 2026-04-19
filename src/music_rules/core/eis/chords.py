"""EIS chord builders — TODO(phase 8).

This module will implement Murphy's vertical chord-class taxonomy:
``triad-open``, ``triad-close``, ``nat7``, ``9``, ``11``, ``13``,
``quartal``, ``quintal``, ``secondal``, ``polytonal``. Each builder
takes a Root, a Scale (from :mod:`music_rules.core.eis.scales`), and a
voicing parameter, then returns a list of MIDI numbers respecting EIS
spacing rules (no harmony tone below the 3rd space of the bass clef
except the lowest Root or 5th, etc.).

Until then, every public function below raises :class:`NotImplementedError`
with a pointer to ``docs/MCP_TOOL_SURFACE_SPEC.md`` §2 Group B.
"""

from __future__ import annotations

ChordClass = str  # exhaustive Literal will land in Phase 8


def build_chord(
    root: str,
    scale_id: str,
    chord_class: ChordClass,
    parts: int = 4,
) -> list[int]:
    """Build an EIS chord. **Not implemented (Phase 8).**

    Args:
        root:         tonal root, e.g. ``"C"``, ``"Bb"``, ``"F#"``.
        scale_id:     id from :mod:`music_rules.core.eis.scales`.
        chord_class:  ``"triad-open"`` | ``"triad-close"`` | ``"nat7"`` |
                      ``"9"`` | ``"11"`` | ``"13"`` | ``"quartal"`` |
                      ``"quintal"`` | ``"secondal"`` | ``"polytonal"``.
        parts:        number of voices (2..5).

    Returns:
        List of MIDI numbers, low-to-high, respecting EIS spacing rules.
    """
    raise NotImplementedError(
        "EIS chord-builder (Group B / phase 8). "
        "See docs/MCP_TOOL_SURFACE_SPEC.md §2 Group B."
    )
