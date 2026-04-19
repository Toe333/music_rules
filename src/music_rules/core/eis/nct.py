"""EIS Non-Chord Tones (NCTs).

Murphy/Greene catalogue six NCT types (master rules §10, corpus rules
``N-001``..``N-012``):

| Abbrev | Name                | Insertion pattern                              |
|--------|---------------------|------------------------------------------------|
| P.T.   | Passing Tone        | step-wise note BETWEEN two chord tones a 3rd apart |
| C.A.   | Chromatic Alteration| inflect a chord tone up/down by 1 semitone, then resolve back |
| R.T.   | Returning Tone      | upper or lower neighbour, returns to the chord tone |
| C.T.   | Chord Tone (passing)| pass through a chord tone of a *different* chord (often in bass) |
| Sus.   | Suspension          | hold a chord tone INTO the next chord, then resolve down by step |
| Ant.   | Anticipation        | sound the next chord's tone EARLY, before the bass moves |

EIS rule **V-005** specifies that NCTs do *not* affect voice-leading;
they sit between two chord tones (the surrounding chord tones still
satisfy V-001..V-004). This module formalises that as a single
:func:`insert_nct` operation that decorates a (chord_a, chord_b) move
with one NCT in a specified voice.

Public API
----------

* :data:`NCT_TYPES`     — registry of NCT type metadata (id, label, rule_ref).
* :func:`insert_nct`    — decorate one voice of a chord move with an NCT.
* :func:`list_nct_types` — discoverability for MCP / OpenAI clients.

The result is a list of "events" describing the inserted notes with
beat positions, voice indices, and the NCT classification. Callers
flatten that into MIDI by adding the events to the chord's existing
notes.
"""

from __future__ import annotations

from typing import Final, Literal, TypedDict

from music_rules.core.eis.scales import scale_pcs

NCTType = Literal["PT", "CA", "RT", "CT", "Sus", "Ant"]


class NCTSpec(TypedDict):
    id: NCTType
    label: str
    rule_ref: str
    description: str


class NCTEvent(TypedDict):
    """One inserted NCT in a chord move.

    * ``voice``  — index of the voice carrying the NCT (0 = bass).
    * ``midi``   — pitch of the NCT.
    * ``beat``   — fractional beat within the chord move:
                  0.0 = on the downbeat of chord A,
                  1.0 = on the downbeat of chord B,
                  0.5 = exactly between, etc.
    * ``type``   — NCT type id.
    * ``rule_ref`` — the corpus rule it instantiates.
    """

    voice: int
    midi: int
    beat: float
    type: NCTType
    rule_ref: str


_TYPES: Final[tuple[NCTSpec, ...]] = (
    {"id": "PT",  "label": "Passing Tone",
     "rule_ref": "N-002",
     "description": "Stepwise tone between two chord tones a 3rd apart."},
    {"id": "CA",  "label": "Chromatic Alteration",
     "rule_ref": "N-003",
     "description": "Inflect a chord tone by 1 semitone, then resolve back."},
    {"id": "RT",  "label": "Returning Tone",
     "rule_ref": "N-004",
     "description": "Upper or lower neighbour returning to the chord tone."},
    {"id": "CT",  "label": "Chord Tone (passing)",
     "rule_ref": "N-005",
     "description": "Pass through a chord tone of a different chord."},
    {"id": "Sus", "label": "Suspension",
     "rule_ref": "N-006",
     "description": "Hold a chord A tone into chord B; resolve down by step."},
    {"id": "Ant", "label": "Anticipation",
     "rule_ref": "N-007",
     "description": "Sound chord B's tone before the bass moves."},
)

NCT_TYPES: Final[dict[NCTType, NCTSpec]] = {t["id"]: t for t in _TYPES}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def insert_nct(
    chord_a: list[int],
    chord_b: list[int],
    *,
    voice: int,
    nct_type: NCTType,
    scale_id: str = "EIS-18-01",
    scale_root: str | int = "C",
    direction: Literal["up", "down"] = "down",
) -> NCTEvent:
    """Compute a single NCT to insert in ``voice`` between two chords.

    Args:
        chord_a:    sounding chord on the previous beat (low → high).
        chord_b:    sounding chord on the next beat.
        voice:      index of the voice carrying the NCT.
        nct_type:   one of the six NCT type ids.
        scale_id:   melodic palette to draw from (PT / RT / CT use it).
        scale_root: tonic for the scale palette.
        direction:  for RT only — upper (``"up"``) or lower (``"down"``)
                    neighbour.

    Returns:
        An :class:`NCTEvent` describing the inserted NCT.

    Raises:
        ValueError: voice index out of range, mismatched chord lengths,
                    or NCT geometry impossible for the given chord pair.
        KeyError:   bad ``nct_type`` or ``scale_id``.
    """
    if nct_type not in NCT_TYPES:
        raise KeyError(
            f"Unknown nct_type {nct_type!r}. Valid: {sorted(NCT_TYPES)}."
        )
    if len(chord_a) != len(chord_b):
        raise ValueError(
            f"chord_a/chord_b length mismatch: {len(chord_a)} vs {len(chord_b)}"
        )
    if not 0 <= voice < len(chord_a):
        raise ValueError(
            f"voice {voice} out of range 0..{len(chord_a) - 1}"
        )

    a = chord_a[voice]
    b = chord_b[voice]
    spec = NCT_TYPES[nct_type]

    if nct_type == "PT":
        # Stepwise pass through scale tones between a and b.
        if abs(b - a) < 2 or abs(b - a) > 4:
            raise ValueError(
                f"Passing tone needs a 3rd or 4th between voices "
                f"({a}→{b} is {abs(b - a)} semitones)."
            )
        midi = _scale_step_between(a, b, scale_id, scale_root)
        beat = 0.5
    elif nct_type == "CA":
        # Chromatic alteration: 1-semitone away from a, then resolves to b.
        midi = a + (1 if b > a else -1)
        beat = 0.5
    elif nct_type == "RT":
        # Upper / lower neighbour from scale, resolves back to a.
        step = _next_scale_step(a, scale_id, scale_root, direction)
        midi = a + step
        beat = 0.5
    elif nct_type == "CT":
        # Pass through chord tone of B (early arrival, returns to A).
        # Use the closest tone in chord_b.
        midi = min(chord_b, key=lambda m: abs(m - a))
        beat = 0.5
    elif nct_type == "Sus":
        # Hold A's tone, then resolve down by step on the next beat.
        midi = a
        beat = 0.0    # The "suspension" itself sounds on the downbeat of B.
    else:  # Ant
        # Anticipate B's tone early.
        midi = b
        beat = 0.75   # Final fraction before chord B sounds.

    return {
        "voice": voice,
        "midi": midi,
        "beat": beat,
        "type": nct_type,
        "rule_ref": spec["rule_ref"],
    }


def list_nct_types() -> list[NCTSpec]:
    """Return every registered NCT type (for discovery)."""
    return list(NCT_TYPES.values())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _scale_step_between(a: int, b: int, scale_id: str,
                        scale_root: str | int) -> int:
    """Return the scale tone strictly between ``a`` and ``b``."""
    pcs = scale_pcs(scale_id, scale_root)
    low, high = sorted([a, b])
    for midi in range(low + 1, high):
        if midi % 12 in pcs:
            return midi
    # Fall back to chromatic mid-point if the scale skips this region.
    return (a + b) // 2


def _next_scale_step(a: int, scale_id: str, scale_root: str | int,
                     direction: Literal["up", "down"]) -> int:
    """Return the semitone offset to the next scale tone above / below ``a``."""
    pcs = scale_pcs(scale_id, scale_root)
    rng = range(1, 13) if direction == "up" else range(-1, -13, -1)
    for offset in rng:
        if (a + offset) % 12 in pcs:
            return offset
    return 1 if direction == "up" else -1   # chromatic fallback
