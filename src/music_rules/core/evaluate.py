"""Passage evaluator — Phase 4 orchestrator.

Walks a complete piece (one or more voices, all of equal length) and
runs every Phase-3 checker at every applicable position, then folds the
per-fragment :class:`CheckReport` outputs into the unified passage report
described in ``docs/MCP_TOOL_SURFACE_SPEC.md`` §2 Group D::

    {
        total_cost:      float,
        hard_violations: [ {rule_id, position, voices_involved, msg}, ... ],
        soft_violations: [ {rule_id, position, cost, msg}, ... ],
        per_rule_summary:{ "H1_1": {"count": 2, "total_cost": null}, ... },
        grade:           "A" | "B" | "C" | "D" | "F"
    }

Design notes
------------

* The dispatch table (``_DISPATCH``) maps each Phase-3 checker to its
  positional role. Adding a new checker is a one-line edit; the
  evaluator never grows arms-and-legs branching logic.
* ``ruleset="EIS"`` and ``"both"`` are accepted but currently behave the
  same as ``"Fux"`` because EIS checkers don't exist yet (Phase 7).
  When they do, dispatching them is the same one-line addition.
* ``include`` and ``exclude`` rule-ID filters are applied *post-hoc*
  to each per-fragment report — the checkers always run; we just
  filter what we count. This keeps the evaluator deterministic and
  the per-rule cost summary accurate even when filters are off.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal, TypedDict

from music_rules.core.eis import ood as eis_ood
from music_rules.core.fux import dissonance, harmonic, melodic, motion
from music_rules.core.report import CheckReport

# Standard SATB ranges (MIDI numbers). Used as the default when the
# caller asks for ``"satb"`` voice ranges without specifying numbers.
_SATB_RANGES: dict[str, tuple[int, int]] = {
    "soprano": (60, 79),  # C4 .. G5
    "alto": (53, 74),  # F3 .. D5
    "tenor": (48, 67),  # C3 .. G4
    "bass": (40, 60),  # E2 .. C4
}
_SATB_ORDER = ("bass", "tenor", "alto", "soprano")

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


Ruleset = Literal["Fux", "EIS", "both"]
Grade = Literal["A", "B", "C", "D", "F"]


class PassagePiece(TypedDict, total=False):
    voices: list[list[int]]
    meter: str
    key: str
    species: int | str
    cantus_firmus_voice: int
    voice_ranges: list[list[int]] | str
    check_ood: bool


class HardViolation(TypedDict):
    rule_id: str
    position: int
    voices_involved: list[int]
    msg: str


class SoftViolation(TypedDict):
    rule_id: str
    position: int
    cost: float
    msg: str


class PerRuleSummary(TypedDict):
    count: int
    total_cost: float | None


class PassageReport(TypedDict):
    total_cost: float
    hard_violations: list[HardViolation]
    soft_violations: list[SoftViolation]
    per_rule_summary: dict[str, PerRuleSummary]
    grade: Grade


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def evaluate_passage(
    piece: PassagePiece,
    *,
    ruleset: Ruleset = "Fux",
    strict: bool = False,
    include: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
) -> PassageReport:
    """Evaluate a full piece and return a passage-level report.

    Args:
        piece: A dict with at least::

            {
                "voices": [[midi, midi, ...],  ...],   # one list per voice
                "meter":  "4/4",                       # currently informational
                "key":    "C",                         # used by future EIS rules
                "species": 1,                          # 1..5 or "all"
                "cantus_firmus_voice": 0,              # index into voices[]
            }

            All voices must have the same length. ``cantus_firmus_voice``
            tells the motion-pair checker which voice is the CF (and
            therefore which is the counterpoint).

        ruleset: ``"Fux"`` | ``"EIS"`` | ``"both"``. EIS is a pass-through
            no-op until Phase 7 wires its checkers in.
        strict: If True, hybrid rules promote to hard. (No hybrid rule
            in the Phase-3 set yet, so this is forward-compat for now.)
        include: If set, only rule IDs in this set are reported.
        exclude: If set, rule IDs in this set are dropped from the report.

    Returns:
        :class:`PassageReport` matching the MCP spec §2 Group D shape.
    """
    _validate_piece(piece)
    voices = piece["voices"]
    species = piece.get("species", 1)
    voice_count = len(voices)
    cf_idx = int(piece.get("cantus_firmus_voice", 0))
    cp_idx = next((i for i in range(voice_count) if i != cf_idx), cf_idx)
    length = len(voices[0])

    include_set = set(include) if include is not None else None
    exclude_set = set(exclude) if exclude is not None else set()

    hard: list[HardViolation] = []
    soft: list[SoftViolation] = []

    if ruleset in ("Fux", "both"):
        _run_fux_passes(
            voices=voices,
            cf_idx=cf_idx,
            cp_idx=cp_idx,
            voice_count=voice_count,
            length=length,
            species=species,
            strict=strict,
            hard=hard,
            soft=soft,
        )

    if ruleset in ("EIS", "both"):
        _run_eis_passes(
            voices=voices,
            voice_count=voice_count,
            length=length,
            piece=piece,
            soft=soft,
        )

    # ---- Voice-range constraints (cross-system) ---------------------------
    voice_ranges = _resolve_voice_ranges(piece, voice_count)
    if voice_ranges is not None:
        _check_voice_ranges(voices, voice_ranges, hard)

    hard = _filter(hard, include_set, exclude_set)
    soft = _filter(soft, include_set, exclude_set)

    per_rule = _build_per_rule_summary(hard, soft)
    total_cost = sum(v["cost"] for v in soft)
    grade = _compute_grade(hard_count=len(hard), total_cost=total_cost)

    return {
        "total_cost": round(total_cost, 4),
        "hard_violations": hard,
        "soft_violations": soft,
        "per_rule_summary": per_rule,
        "grade": grade,
    }


# ---------------------------------------------------------------------------
# Per-pass helpers (kept tiny so the dispatch logic is grep-able)
# ---------------------------------------------------------------------------


def _run_fux_passes(
    *,
    voices: list[list[int]],
    cf_idx: int,
    cp_idx: int,
    voice_count: int,
    length: int,
    species: int | str,
    strict: bool,
    hard: list[HardViolation],
    soft: list[SoftViolation],
) -> None:
    """Run every Phase-3 Fux checker at every applicable position."""
    cf = voices[cf_idx]
    cp = voices[cp_idx]

    # ---- Per-voice melodic passes -----------------------------------------
    for v_idx, voice in enumerate(voices):
        for pos in range(1, length):
            r = melodic.check_melodic_interval(
                voice[pos - 1],
                voice[pos],
                species=species,
                voices=voice_count,
                strict=strict,
            )
            _absorb(r, position=pos, voices_involved=[v_idx], hard=hard, soft=soft)

        for pos in range(2, length):
            r = melodic.check_melodic_triple(
                voice[pos - 2],
                voice[pos - 1],
                voice[pos],
                species=species,
                voices=voice_count,
                strict=strict,
            )
            _absorb(r, position=pos, voices_involved=[v_idx], hard=hard, soft=soft)

    # ---- Two-voice motion-pair pass (cf vs cp) ----------------------------
    if voice_count >= 2 and cf_idx != cp_idx:
        for pos in range(1, length):
            r = motion.check_motion_pair(
                {"cf": cf[pos - 1], "cp": cp[pos - 1]},
                {"cf": cf[pos], "cp": cp[pos]},
                species=species,
                voices=voice_count,
                strict=strict,
            )
            _absorb(
                r,
                position=pos,
                voices_involved=[cf_idx, cp_idx],
                hard=hard,
                soft=soft,
            )

    # ---- Per-beat vertical passes -----------------------------------------
    for pos in range(length):
        chord = [voice[pos] for voice in voices]
        all_voices = list(range(voice_count))

        r = harmonic.check_per_measure_downbeat(
            chord,
            species=species,
            voices=voice_count,
            strict=strict,
        )
        _absorb(r, position=pos, voices_involved=all_voices, hard=hard, soft=soft)

        r = harmonic.check_vertical_chord(
            chord,
            species=species,
            voices=voice_count,
            strict=strict,
        )
        _absorb(r, position=pos, voices_involved=all_voices, hard=hard, soft=soft)

    # ---- Opening / closing intervals --------------------------------------
    if voice_count >= 2 and length >= 1:
        opening = [voices[i][0] for i in range(voice_count)]
        r = harmonic.check_first_interval(
            opening,
            species=species,
            voices=voice_count,
            strict=strict,
        )
        _absorb(r, position=0, voices_involved=list(range(voice_count)), hard=hard, soft=soft)

        closing = [voices[i][-1] for i in range(voice_count)]
        r = harmonic.check_final_interval(
            closing,
            species=species,
            voices=voice_count,
            strict=strict,
        )
        _absorb(
            r, position=length - 1, voices_involved=list(range(voice_count)), hard=hard, soft=soft
        )

    # ---- 3rd-species dissonance windows -----------------------------------
    # Only meaningful when species in {3, "all"}; cheap to skip otherwise.
    if str(species) in {"3", "all"} and voice_count >= 2 and cf_idx != cp_idx:
        for pos in range(1, length - 1):
            r = dissonance.check_dissonance_context(
                cp[pos - 1],
                cp[pos],
                cp[pos + 1],
                cf_pitch=cf[pos],
                species=species,
                voices=voice_count,
                strict=strict,
            )
            _absorb(
                r,
                position=pos,
                voices_involved=[cp_idx],
                hard=hard,
                soft=soft,
            )


def _run_eis_passes(
    *,
    voices: list[list[int]],
    voice_count: int,
    length: int,
    piece: PassagePiece,
    soft: list[SoftViolation],
) -> None:
    """Run EIS-side checkers on every chord in the passage.

    Today we surface OOD (Outside-Octave Dissonance) hits as *soft*
    violations because Murphy explicitly relaxes OOD as the student
    advances (master rules §17, rule A-008). Use ``check_ood=False``
    in the piece dict to silence this pass.
    """
    if voice_count < 2:
        return
    if not piece.get("check_ood", True):
        return
    for pos in range(length):
        chord = sorted(voices[i][pos] for i in range(voice_count))
        hits = eis_ood.check_voicing(chord)
        for hit in hits:
            soft.append(
                {
                    "rule_id": hit["rule_id"],
                    "position": pos,
                    "cost": 0.5,  # Conservative — OOD is informational/soft.
                    "msg": hit["detail"],
                }
            )


def _resolve_voice_ranges(
    piece: PassagePiece,
    voice_count: int,
) -> list[tuple[int, int]] | None:
    """Resolve the ``voice_ranges`` field into per-voice ``(low, high)`` pairs.

    Accepts:
        * Omitted / None      — no range checking.
        * ``"satb"``          — apply standard SATB ranges from low to high.
                                Voices are matched bottom-up to bass / tenor /
                                alto / soprano.
        * ``[[40, 60], ...]`` — explicit per-voice ``[low, high]`` lists,
                                one per voice.
    """
    spec = piece.get("voice_ranges")
    if spec is None:
        return None
    if isinstance(spec, str):
        if spec.lower() != "satb":
            raise ValueError(f"Unknown voice_ranges preset {spec!r} (only 'satb' is built-in).")
        # Map bottom voice to bass, top voice to soprano.
        out: list[tuple[int, int]] = []
        for i in range(voice_count):
            slot = _SATB_ORDER[min(i, len(_SATB_ORDER) - 1)]
            out.append(_SATB_RANGES[slot])
        return out
    if not isinstance(spec, list) or len(spec) != voice_count:
        raise ValueError(
            f"voice_ranges must be 'satb' or a list of {voice_count} "
            f"[low, high] pairs; got {spec!r}."
        )
    parsed: list[tuple[int, int]] = []
    for i, pair in enumerate(spec):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(f"voice_ranges[{i}] must be a [low, high] pair; got {pair!r}.")
        low, high = int(pair[0]), int(pair[1])
        if low > high:
            raise ValueError(f"voice_ranges[{i}] low ({low}) > high ({high}).")
        parsed.append((low, high))
    return parsed


def _check_voice_ranges(
    voices: list[list[int]],
    ranges: list[tuple[int, int]],
    hard: list[HardViolation],
) -> None:
    """Flag any pitch outside its voice's [low, high] envelope as a hard hit."""
    for v_idx, voice in enumerate(voices):
        low, high = ranges[v_idx]
        for pos, pitch in enumerate(voice):
            if pitch < 0:
                continue
            if pitch < low or pitch > high:
                hard.append(
                    {
                        "rule_id": "RG-001",
                        "position": pos,
                        "voices_involved": [v_idx],
                        "msg": (f"Voice {v_idx} pitch {pitch} outside range [{low}..{high}]."),
                    }
                )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _absorb(
    report: CheckReport,
    *,
    position: int,
    voices_involved: list[int],
    hard: list[HardViolation],
    soft: list[SoftViolation],
) -> None:
    for v in report["violations"]:
        hard.append(
            {
                "rule_id": v["rule_id"],
                "position": position,
                "voices_involved": list(voices_involved),
                "msg": v["msg"],
            }
        )
    for c in report["soft_costs"]:
        soft.append(
            {
                "rule_id": c["rule_id"],
                "position": position,
                "cost": c["cost"],
                "msg": c["msg"],
            }
        )


def _filter(items: list[Any], include: set[str] | None, exclude: set[str]) -> list[Any]:
    out = items
    if include is not None:
        out = [i for i in out if i["rule_id"] in include]
    if exclude:
        out = [i for i in out if i["rule_id"] not in exclude]
    return out


def _build_per_rule_summary(
    hard: list[HardViolation], soft: list[SoftViolation]
) -> dict[str, PerRuleSummary]:
    summary: dict[str, PerRuleSummary] = {}
    for v in hard:
        rid = v["rule_id"]
        entry = summary.setdefault(rid, {"count": 0, "total_cost": None})
        entry["count"] += 1
    for c in soft:
        rid = c["rule_id"]
        entry = summary.setdefault(rid, {"count": 0, "total_cost": 0.0})
        entry["count"] += 1
        # Convert int -> float on the fly if the rule mixes hard+soft.
        cur = entry["total_cost"] or 0.0
        entry["total_cost"] = round(cur + c["cost"], 4)
    return summary


def _compute_grade(*, hard_count: int, total_cost: float) -> Grade:
    """Derive a letter grade from the violation count and total soft cost.

    Rubric (kept simple and predictable so it's debuggable):

    +-----------+--------------+-------+
    | hard      | total_cost   | grade |
    +===========+==============+=======+
    | 0         | <= 1.0       |   A   |
    | 0         | <= 5.0       |   B   |
    | 0         | <= 15.0      |   C   |
    | 1-2       | (any)        |   D   |
    | 3+        | (any)        |   F   |
    +-----------+--------------+-------+

    Tunable later; for now this gives the AI / human grader a clear
    "did anything bad happen" signal at a glance.
    """
    if hard_count >= 3:
        return "F"
    if hard_count >= 1:
        return "D"
    if total_cost <= 1.0:
        return "A"
    if total_cost <= 5.0:
        return "B"
    if total_cost <= 15.0:
        return "C"
    return "D"


def _validate_piece(piece: PassagePiece) -> None:
    """Cheap structural validation — informative errors over Pydantic overhead."""
    if "voices" not in piece:
        raise ValueError("piece must contain 'voices' (list of MIDI sequences)")
    voices = piece["voices"]
    if not isinstance(voices, list) or not voices:
        raise ValueError("piece['voices'] must be a non-empty list of voice lists")
    if not all(isinstance(v, list) and v for v in voices):
        raise ValueError("each voice must be a non-empty list of MIDI numbers")
    L = len(voices[0])
    if any(len(v) != L for v in voices):
        raise ValueError(f"all voices must have the same length; got {[len(v) for v in voices]}")
    cf_idx = piece.get("cantus_firmus_voice", 0)
    if not (0 <= int(cf_idx) < len(voices)):
        raise ValueError(f"cantus_firmus_voice {cf_idx} out of range for {len(voices)} voices")
