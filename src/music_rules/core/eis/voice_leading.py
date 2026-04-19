"""EIS voice-leading — TODO(phase 8).

This module will implement rules V-001..V-015 from the corpus:

* hold common tones,
* contrary motion vs. the bass,
* move remaining tones to the nearest tones in the next chord,
* never sound three of the same tone (no matter how voiced),
* NCTs sit between two chord tones (don't affect VL),
* in chords containing a natural 7, ♮7 must always resolve to 6
  whenever 9 resolves to 8.

Until then, the function below raises :class:`NotImplementedError`.
"""

from __future__ import annotations


def voice_lead(
    prev_chord: list[int],
    next_chord: list[int],
    *,
    mode: str = "strict",
) -> list[int]:
    """Voice-lead from ``prev_chord`` to ``next_chord``. **Not implemented.**

    Args:
        prev_chord: MIDI numbers of the prior chord (low-to-high).
        next_chord: MIDI numbers of the target chord (any voicing).
        mode:       ``"strict"`` (V-001..V-015 hard) | ``"relaxed"``.

    Returns:
        A re-voicing of ``next_chord`` that minimizes voice-motion
        per the EIS rules.
    """
    raise NotImplementedError(
        "EIS voice-leader (Group B / phase 8). "
        "See docs/MCP_TOOL_SURFACE_SPEC.md §2 Group B."
    )
