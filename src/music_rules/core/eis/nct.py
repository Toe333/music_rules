"""EIS non-chord-tone insertion — TODO(phase 8).

Inserts EIS NCTs into a melodic line:

* ``PT`` — Passing Tone
* ``CA`` — Cambiata
* ``RT`` — Returning Tone
* ``CT`` — Changing Tone
* ``Sus`` — Suspension
* ``Ant`` — Anticipation

Until Phase 8 the function below raises :class:`NotImplementedError`.
"""

from __future__ import annotations

NctType = str  # exhaustive Literal will land in Phase 8


def insert_nct(voice: list[int], nct_type: NctType, beat: float) -> list[int]:
    """Insert an EIS non-chord tone into a melodic line. **Not implemented.**

    Args:
        voice:    MIDI numbers of the melodic line.
        nct_type: ``"PT"`` | ``"CA"`` | ``"RT"`` | ``"CT"`` | ``"Sus"`` | ``"Ant"``.
        beat:     fractional beat position to insert at.
    """
    raise NotImplementedError(
        "EIS NCT inserter (Group B / phase 8). "
        "See docs/MCP_TOOL_SURFACE_SPEC.md §2 Group B."
    )
