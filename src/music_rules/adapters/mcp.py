"""MCP adapter — exposes the music-rules core as a FastMCP server.

This is a thin shim: every tool is a 5-15 line wrapper around a core
function. Adding or removing a tool is a one-decorator edit.

Tool surface (per ``docs/MCP_TOOL_SURFACE_SPEC.md``):

* **Group A — Corpus introspection** (always available)
    * ``list_rule_systems``
    * ``list_rule_categories``
    * ``list_rule_kinds``
    * ``list_input_shapes``
    * ``get_rules``
    * ``get_rule``
    * ``explain_rule``

* **Group C — Fux checkers** (the Phase-3 set)
    * ``check_melodic_interval``
    * ``check_melodic_triple``
    * ``check_motion_pair``
    * ``check_vertical_chord``
    * ``check_first_interval``
    * ``check_final_interval``
    * ``check_per_measure_downbeat``
    * ``check_weak_beat_interval``
    * ``check_dissonance_context``

* **Group D — Passage evaluator**
    * ``evaluate_passage``

* **Group B — EIS helpers**
    * ``eis_pick_root_line`` / ``eis_list_scales`` / ``eis_list_chord_classes``
    * ``eis_build_chord`` / ``eis_voice_lead`` / ``eis_check_voice_leading``
    * ``eis_insert_nct`` / ``eis_list_nct_types`` / ``eis_check_ood``

* **Group E — SkyTNT MIDI bridge**
    * ``midi_to_rolls`` / ``rolls_to_midi`` (per-voice GM programs)
    * ``skytnt_generate`` / ``skytnt_constrained_generate``
      (lazy-load ``transformers``; gracefully report when extras missing)

Architecture
------------

The module is split into two layers:

1. **Pure tool functions** (the ``_impl_*`` private helpers and the
   public ``tool_*``-prefixed equivalents). These import only from
   :mod:`music_rules.core` and return JSON-serializable dicts. They are
   directly importable and unit-testable without ``fastmcp`` installed.
2. **Server factory** (:func:`build_server`). Imports ``fastmcp`` lazily
   and registers every tool function with descriptive names. Called by
   :func:`main` (the ``music-rules-mcp`` console script).

This split means:

* Tests can exercise every tool by calling the plain functions directly.
* The package can be imported in environments where ``fastmcp`` isn't
  installed yet (e.g. partial editable installs), without ImportErrors.
* Adding a new tool only requires (a) writing a function and (b) adding
  it to ``_TOOLS`` — registration is uniform.
"""

from __future__ import annotations

from typing import Any

from music_rules.core import corpus, evaluate
from music_rules.core.eis import chords as eis_chords
from music_rules.core.eis import nct as eis_nct
from music_rules.core.eis import ood as eis_ood
from music_rules.core.eis import roots as eis_roots
from music_rules.core.eis import scales as eis_scales
from music_rules.core.eis import voice_leading as eis_voice_leading
from music_rules.core.fux import dissonance, harmonic, melodic, motion
from music_rules.core.midi import skytnt_bridge

# ---------------------------------------------------------------------------
# Group A — Corpus introspection
# ---------------------------------------------------------------------------


def tool_list_rule_systems() -> list[str]:
    """List every rule system present in the corpus.

    Returns: a sorted list, e.g. ``["EIS", "Fux"]``.
    """
    return corpus.list_systems()


def tool_list_rule_categories(system: str | None = None) -> list[str]:
    """List rule categories, optionally filtered to one system.

    Args:
        system: ``"EIS"`` | ``"Fux"`` | ``None`` (all).
    """
    return corpus.list_categories(system=system)  # type: ignore[arg-type]


def tool_list_rule_kinds() -> list[str]:
    """List rule kinds present in the corpus (e.g. ``hard``, ``soft``)."""
    return corpus.list_kinds()


def tool_list_input_shapes() -> list[str]:
    """List the canonical ``input_shape`` vocabulary used by checkers."""
    return corpus.list_input_shapes()


def tool_get_rules(
    system: str | None = None,
    category: str | None = None,
    species: int | str | None = None,
    voices: int | str | None = None,
    kind: str | None = None,
    tier: str | None = None,
    input_shape: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Filtered rule lookup. All filters AND-combined.

    Args:
        system:      ``"EIS"`` | ``"Fux"`` (omit for both).
        category:    rule category bucket (e.g. ``"voice-leading"``).
        species:     ``1`` | ``2`` | ... | ``"all"``.
        voices:      ``2`` | ``3`` | ``4`` (becomes ``"2v"``...).
        kind:        ``"hard"`` | ``"soft"`` | ``"hybrid"`` | ``"informational"``.
        tier:        rule tier string (corpus-defined).
        input_shape: e.g. ``"motion-pair"``, ``"melodic-interval"``.
        limit:       cap on returned rules (default 200).
    """
    rules = corpus.get_rules(
        system=system,                 # type: ignore[arg-type]
        category=category,
        species=species,
        voices=voices,
        kind=kind,                     # type: ignore[arg-type]
        tier=tier,
        input_shape=input_shape,
        limit=limit,
    )
    return [r.model_dump() for r in rules]


def tool_get_rule(rule_id: str) -> dict[str, Any]:
    """Fetch a single rule by ID. Raises ``KeyError`` if unknown."""
    return corpus.get_rule(rule_id).model_dump()


def tool_explain_rule(rule_id: str) -> dict[str, Any]:
    """Return a short paraphrase + structural hint for a single rule.

    Output shape::

        {
            "rule_id":      "P1_1_2v",
            "system":       "Fux",
            "kind":         "hard",
            "rule":         "<the corpus 'rule' string>",
            "scope":        "<corpus 'scope'>",
            "exceptions":   "<corpus 'exceptions'>",
            "applies_to":   {"species": "1", "voices": "2v"},
            "input_shape":  "motion-pair",
            "checker_hint": "Use check_motion_pair(...).",
            "source":       "<provenance citation>",
        }

    The ``checker_hint`` is derived from ``input_shape`` so an agent can
    discover which Group-C tool to call without hardcoding mappings.
    """
    rule = corpus.get_rule(rule_id)
    hint = _CHECKER_HINTS.get(
        rule.input_shape or "",
        "No mechanical checker for this rule (informational / principle).",
    )
    return {
        "rule_id": rule.id,
        "system": rule.system,
        "kind": rule.kind,
        "rule": rule.rule,
        "scope": rule.scope,
        "exceptions": rule.exceptions,
        "applies_to": {"species": rule.species, "voices": rule.voices},
        "input_shape": rule.input_shape,
        "checker_hint": hint,
        "source": rule.source,
    }


# Maps input_shape → MCP tool name. Built off the existing checker
# functions, *not* hardcoded for specific rule IDs.
_CHECKER_HINTS: dict[str, str] = {
    "melodic-interval": "Use check_melodic_interval(prev_midi, curr_midi, ...).",
    "melodic-triple": "Use check_melodic_triple(n1, n2, n3, ...).",
    "motion-pair": "Use check_motion_pair(prev_pair, curr_pair, ...).",
    "vertical-chord": "Use check_vertical_chord(chord, ...).",
    "first-interval": "Use check_first_interval(chord, ...).",
    "final-interval": "Use check_final_interval(chord, ...).",
    "per-measure-downbeat": "Use check_per_measure_downbeat(chord, ...).",
    "weak-beat-interval": "Use check_weak_beat_interval(chord, ...).",
    "dissonance-context": "Use check_dissonance_context(prev, diss, next, cf_pitch=..., ...).",
}


# ---------------------------------------------------------------------------
# Group C — Fux checkers (Phase-3 set)
# ---------------------------------------------------------------------------


def tool_check_melodic_interval(
    prev_midi: int,
    curr_midi: int,
    species: int | str = 1,
    voices: int | str = 2,
    strict: bool = False,
) -> dict[str, Any]:
    """Check one melodic step (single voice, two consecutive MIDI notes)."""
    return dict(
        melodic.check_melodic_interval(
            prev_midi, curr_midi, species=species, voices=voices, strict=strict
        )
    )


def tool_check_melodic_triple(
    n1: int,
    n2: int,
    n3: int,
    species: int | str = "all",
    voices: int | str = "any",
    strict: bool = False,
) -> dict[str, Any]:
    """Check three consecutive melodic notes (e.g. for chromatic-ascent G6)."""
    return dict(
        melodic.check_melodic_triple(n1, n2, n3, species=species, voices=voices, strict=strict)
    )


def tool_check_motion_pair(
    prev_pair: dict[str, int],
    curr_pair: dict[str, int],
    species: int | str = 1,
    voices: int | str = 2,
    strict: bool = False,
) -> dict[str, Any]:
    """Check the motion between two adjacent verticalities (P1_*).

    Each pair is ``{"cf": <midi>, "cp": <midi>}``.
    """
    return dict(
        motion.check_motion_pair(
            prev_pair, curr_pair, species=species, voices=voices, strict=strict
        )
    )


def tool_check_vertical_chord(
    chord: list[int],
    key: str = "C",
    position: int = 0,
    total_length: int = 1,
    species: int | str = 1,
    voices: int | str = 3,
    strict: bool = False,
) -> dict[str, Any]:
    """Check a single vertical sonority for completeness (H8_*)."""
    return dict(
        harmonic.check_vertical_chord(
            chord,
            key=key,
            position=position,
            total_length=total_length,
            species=species,
            voices=voices,
            strict=strict,
        )
    )


def tool_check_first_interval(
    chord: list[int],
    species: int | str = 1,
    voices: int | str = 2,
    strict: bool = False,
) -> dict[str, Any]:
    """Check the opening sonority (H2_1: must be a perfect consonance)."""
    return dict(
        harmonic.check_first_interval(
            chord, species=species, voices=voices, strict=strict
        )
    )


def tool_check_final_interval(
    chord: list[int],
    species: int | str = 1,
    voices: int | str = 2,
    strict: bool = False,
) -> dict[str, Any]:
    """Check the closing sonority (H3_1: must be a perfect consonance)."""
    return dict(
        harmonic.check_final_interval(
            chord, species=species, voices=voices, strict=strict
        )
    )


def tool_check_per_measure_downbeat(
    chord: list[int],
    species: int | str = "all",
    voices: int | str = "any",
    strict: bool = False,
) -> dict[str, Any]:
    """Check that every interval in a downbeat sonority is consonant (H1_1)."""
    return dict(
        harmonic.check_per_measure_downbeat(
            chord, species=species, voices=voices, strict=strict
        )
    )


def tool_check_weak_beat_interval(
    chord: list[int],
    species: int | str = 2,
    voices: int | str = "any",
    strict: bool = False,
) -> dict[str, Any]:
    """Check 2nd-species arsis intervals (H2_2: weak beats can't be dissonant)."""
    return dict(
        harmonic.check_weak_beat_interval(
            chord, species=species, voices=voices, strict=strict
        )
    )


def tool_check_dissonance_context(
    prev: int,
    diss: int,
    next_: int,
    cf_pitch: int | None = None,
    species: int | str = 3,
    voices: int | str = "any",
    strict: bool = False,
) -> dict[str, Any]:
    """Check 3rd-species dissonance treatment (H2_3: passing/neighbor)."""
    return dict(
        dissonance.check_dissonance_context(
            prev, diss, next_,
            cf_pitch=cf_pitch, species=species, voices=voices, strict=strict,
        )
    )


# ---------------------------------------------------------------------------
# Group D — Passage evaluator
# ---------------------------------------------------------------------------


def tool_evaluate_passage(
    piece: dict[str, Any],
    ruleset: str = "Fux",
    strict: bool = False,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> dict[str, Any]:
    """Run every Phase-3 checker over a complete piece.

    See :func:`music_rules.core.evaluate.evaluate_passage` for the
    exact ``piece`` and report shapes.
    """
    return dict(
        evaluate.evaluate_passage(
            piece,                           # type: ignore[arg-type]
            ruleset=ruleset,                 # type: ignore[arg-type]
            strict=strict,
            include=include,
            exclude=exclude,
        )
    )


# ---------------------------------------------------------------------------
# Groups B & E — Stubs (Phase 7)
# ---------------------------------------------------------------------------
#
# These return informative ``not_implemented`` payloads rather than raising,
# so an MCP client can discover the future tool surface today and warn the
# user gracefully. When Phase 7 lands, replace each body with the real
# implementation; the function signature stays stable.


def _stub(name: str, summary: str, *, phase: str = "Phase 8") -> dict[str, Any]:
    """Standard "not yet implemented" payload returned by scaffolded tools.

    Returning a payload (rather than raising) lets MCP clients discover
    the future tool surface today and warn their user gracefully.
    """
    return {
        "ok": False,
        "status": "not_implemented",
        "tool": name,
        "summary": summary,
        "available_in": phase,
        "tracking": "See docs/MCP_TOOL_SURFACE_SPEC.md §2 Group B and §2 Group E.",
    }


def tool_eis_pick_root_line(
    length: int,
    cycles: list[str] | None = None,
    start_root: str = "C",
    allow_elision: bool = True,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate an EIS Root-line walking through one or more E1..E6 cycles.

    Args:
        length:        number of Root tones to produce (>=1).
        cycles:        ordered list of cycle ids (``"E1"``..``"E6"``).
                       Defaults to ``["E5"]`` (the circle of 4ths).
        start_root:    starting note name (``"C"``, ``"Bb"``, …).
        allow_elision: permit 1- or 2-step skips at cycle boundaries.
        seed:          deterministic RNG seed for elision choices.

    Returns:
        ``{"roots": ["C", "F", "Bb", ...], "cycles": [...]}``
    """
    line = eis_roots.pick_root_line(
        length=length,
        cycles=cycles,                # type: ignore[arg-type]
        start_root=start_root,
        allow_elision=allow_elision,
        seed=seed,
    )
    return {"roots": line, "cycles": cycles or ["E5"]}


def tool_eis_list_scales(status: str | None = None) -> dict[str, Any]:
    """List the 18 EIS scales (verified + inferred + pending).

    Args:
        status: optional filter — ``"verified"`` | ``"inferred"`` | ``"pending"``.

    Returns:
        ``{"scales": [<scale dict>, ...], "summary": {"verified": N, ...}}``
    """
    scales = eis_scales.list_scales(status=status)  # type: ignore[arg-type]
    return {
        "scales": [dict(s) for s in scales],
        "summary": eis_scales.available_count(),
    }


def tool_eis_build_chord(
    root: str,
    chord_class: str,
    scale_id: str | None = None,
    parts: int | None = None,
    voicing: str = "close",
    inversion: int = 0,
    base_octave: int = 4,
) -> dict[str, Any]:
    """Build an EIS chord and return its fully voiced MIDI numbers.

    Args:
        root:        starting note (``"C"``, ``"Bb"``, ...) or pitch class.
        chord_class: chord-class id (``"triad"``, ``"dom7"``, ``"min9"``,
                     ``"dom7b9"``, ``"4th-3p"``, ``"polytonal"``, …).
                     Use ``eis_list_chord_classes`` for the full menu.
        scale_id:    optional EIS scale id used as melodic context
                     (advisory; chord intervals stand alone).
        parts:       2P / 3P / 4P / 5P. Defaults to the chord's smallest
                     supported part-count.
        voicing:     ``"close"`` or ``"open"`` (drop-2).
        inversion:   0 = root in bass, 1 = first inversion, …
        base_octave: octave for the bass tone (4 = middle C area).

    Returns:
        ``{"midi": [...], "pitch_classes": [...], "chord_class": {...}}``
    """
    midi = eis_chords.build_chord(
        root, chord_class,
        scale_id=scale_id, parts=parts,
        voicing=voicing,                  # type: ignore[arg-type]
        inversion=inversion, base_octave=base_octave,
    )
    return {
        "midi": midi,
        "pitch_classes": eis_chords.pitch_classes(
            root, chord_class, scale_id=scale_id,
        ),
        "chord_class": dict(eis_chords.CHORD_CLASSES[chord_class]),
    }


def tool_eis_list_chord_classes() -> dict[str, Any]:
    """List every EIS chord class the builder supports."""
    return {"chord_classes": [dict(c) for c in eis_chords.list_chord_classes()]}


def tool_eis_voice_lead(
    prev_chord: list[int],
    next_pcs: list[int],
    style: str = "normal",
    keep_bass_in_bass: bool = True,
    max_voice_jump: int = 7,
) -> dict[str, Any]:
    """Re-voice ``next_pcs`` to flow smoothly from ``prev_chord``.

    Args:
        prev_chord:        prior chord as MIDI numbers, low → high.
                           First entry is the bass.
        next_pcs:          target chord as a pitch-class set (use
                           ``eis_build_chord`` first to derive these).
        style:             ``"normal"`` (minimum motion), ``"parallel"``
                           (same intervallic shape), or ``"bracket"``
                           (drop one voice — V-013).
        keep_bass_in_bass: if False, the bass moves freely.
        max_voice_jump:    upper bound on per-voice semitone motion.

    Returns:
        ``{"voiced": [...], "report": <VLReport>}``
    """
    voiced = eis_voice_leading.voice_lead(
        prev_chord, next_pcs,
        style=style,                      # type: ignore[arg-type]
        keep_bass_in_bass=keep_bass_in_bass,
        max_voice_jump=max_voice_jump,
    )
    if len(voiced) == len(prev_chord):
        report = eis_voice_leading.check_progression(prev_chord, voiced)
    else:
        # Bracket style — different lengths, can't compute parallel report.
        report = {
            "smoothness": None,
            "total_motion": None,
            "common_tones": None,
            "contrary_motion_pairs": None,
            "violations": [],
        }
    return {"voiced": voiced, "report": report}


def tool_eis_check_voice_leading(
    prev_chord: list[int],
    next_chord: list[int],
) -> dict[str, Any]:
    """Score an existing two-chord move on EIS voice-leading rules.

    Returns the :class:`VLReport` (``smoothness``, ``total_motion``,
    ``common_tones``, ``contrary_motion_pairs``, ``violations``).
    """
    return dict(
        eis_voice_leading.check_progression(prev_chord, next_chord)
    )


def tool_eis_insert_nct(
    chord_a: list[int],
    chord_b: list[int],
    voice: int,
    nct_type: str,
    scale_id: str = "EIS-18-01",
    scale_root: str = "C",
    direction: str = "down",
) -> dict[str, Any]:
    """Insert one EIS non-chord tone between two chords.

    Args:
        chord_a:    sounding chord on the previous beat (low → high).
        chord_b:    sounding chord on the next beat.
        voice:      index of the voice carrying the NCT.
        nct_type:   one of ``"PT"`` (passing), ``"CA"`` (chromatic
                    alteration), ``"RT"`` (returning / neighbour),
                    ``"CT"`` (chord-tone passing), ``"Sus"``
                    (suspension), ``"Ant"`` (anticipation).
        scale_id:   melodic palette for PT / RT / CT.
        scale_root: tonic of that scale.
        direction:  for RT only — ``"up"`` or ``"down"``.

    Returns:
        ``{"event": {voice, midi, beat, type, rule_ref}}``
    """
    event = eis_nct.insert_nct(
        chord_a, chord_b,
        voice=voice,
        nct_type=nct_type,                # type: ignore[arg-type]
        scale_id=scale_id,
        scale_root=scale_root,
        direction=direction,              # type: ignore[arg-type]
    )
    return {"event": dict(event)}


def tool_eis_list_nct_types() -> dict[str, Any]:
    """List the six EIS non-chord-tone types."""
    return {"nct_types": [dict(t) for t in eis_nct.list_nct_types()]}


def tool_eis_check_ood(
    chord: list[int],
    has_b7: bool = False,
    pedal: bool = False,
) -> dict[str, Any]:
    """Check Outside-Octave Dissonance for a single chord voicing.

    Args:
        chord:    voicing as MIDI numbers, low → high.
        has_b7:   set True if the chord contains a ♭7 (allows ♭9 — O-002).
        pedal:    set True if the bass is a pedal (allows ♭2 — O-003).

    Returns:
        ``{"hits": [<OODHit>, ...], "ok": bool}``
    """
    hits = eis_ood.check_voicing(chord, has_b7=has_b7, pedal=pedal)
    return {"hits": [dict(h) for h in hits], "ok": not hits}


def tool_skytnt_generate(
    prompt_midi: str | None = None,
    conditioning: dict[str, Any] | None = None,
    num_candidates: int = 4,
    max_new_tokens: int = 1024,
    temperature: float = 1.0,
    top_p: float = 0.95,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate raw MIDI with SkyTNT's ``midi-model``.

    Lazy-loads ``transformers`` + ``torch`` on first call. Requires the
    optional extras: ``pip install music-rules[skytnt]``.

    Args / Returns: see
    :func:`music_rules.core.midi.skytnt_bridge.skytnt_generate`.
    """
    try:
        return skytnt_bridge.skytnt_generate(
            prompt_midi=prompt_midi,
            conditioning=conditioning,
            num_candidates=num_candidates,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            seed=seed,
        )
    except skytnt_bridge.SkyTNTUnavailableError as exc:
        return {
            "ok": False,
            "status": "skytnt_unavailable",
            "tool": "skytnt_generate",
            "summary": str(exc),
            "fix": "pip install music-rules[skytnt]",
        }


def tool_skytnt_constrained_generate(
    prompt_midi: str | None = None,
    conditioning: dict[str, Any] | None = None,
    ruleset: str = "both",
    strict: bool = False,
    max_hard_violations: int = 0,
    max_total_cost: float = 10.0,
    num_candidates_per_try: int = 4,
    max_tries: int = 4,
    temperature: float = 1.0,
    seed: int | None = None,
) -> dict[str, Any]:
    """Best-of-N SkyTNT loop filtered through ``evaluate_passage``.

    Returns the lowest-cost candidate that satisfies the supplied caps,
    or the lowest-cost candidate ever seen if none qualify.
    """
    try:
        return skytnt_bridge.skytnt_constrained_generate(
            prompt_midi=prompt_midi,
            conditioning=conditioning,
            ruleset=ruleset,
            strict=strict,
            max_hard_violations=max_hard_violations,
            max_total_cost=max_total_cost,
            num_candidates_per_try=num_candidates_per_try,
            max_tries=max_tries,
            temperature=temperature,
            seed=seed,
        )
    except skytnt_bridge.SkyTNTUnavailableError as exc:
        return {
            "ok": False,
            "status": "skytnt_unavailable",
            "tool": "skytnt_constrained_generate",
            "summary": str(exc),
            "fix": "pip install music-rules[skytnt]",
        }


def tool_midi_to_rolls(
    midi_base64: str,
    beats_per_quarter: int = 1,
) -> dict[str, Any]:
    """Decode a base64 MIDI blob into per-voice MIDI-number lists.

    Args:
        midi_base64:       base64-encoded MIDI file contents.
        beats_per_quarter: subdivision per quarter note (1 = quarter,
                           2 = eighth, 4 = sixteenth, ...).

    Returns:
        ``{"voices": [...], "meter": "4/4", "tempo": int,
            "key_guess": str|None, "ticks_per_beat": int}``
    """
    bundle = skytnt_bridge.midi_to_rolls(
        midi_base64, beats_per_quarter=beats_per_quarter,
    )
    return dict(bundle)


def tool_rolls_to_midi(
    voices: list[list[int]],
    meter: str = "4/4",
    tempo: int = 500_000,
    ticks_per_beat: int = 480,
    velocity: int = 80,
    program: int = 0,
    programs: list[int] | None = None,
) -> dict[str, Any]:
    """Encode per-voice MIDI-number lists into a base64 MIDI blob.

    Args:
        voices:         one MIDI-number list per voice (``-1`` = rest).
        meter:          time signature like ``"4/4"``.
        tempo:          microseconds per quarter note (default 120 BPM).
        ticks_per_beat: PPQN (default 480, GM-friendly).
        velocity:       note-on velocity (1..127).
        program:        General MIDI program number applied to every
                        track when ``programs`` is omitted.
        programs:       optional per-voice GM program list. Length must
                        equal ``len(voices)``. Used for chip-tune
                        (square / square / triangle / noise), SATB
                        choir, mixed orchestration, etc.

    Returns:
        ``{"midi_base64": "..."}`` — round-trip exact at the grid step.
    """
    midi_b64 = skytnt_bridge.rolls_to_midi(
        voices,
        meter=meter,
        tempo=tempo,
        ticks_per_beat=ticks_per_beat,
        velocity=velocity,
        program=program,
        programs=programs,
    )
    return {"midi_base64": midi_b64}


# ---------------------------------------------------------------------------
# Tool registry (single source of truth — used by build_server and tests)
# ---------------------------------------------------------------------------
#
# Each entry maps the *MCP-visible* tool name to its implementation.
# Keeping this as data (not a flurry of decorators) means tests can iterate
# the registry mechanically and the server factory stays trivial.

_TOOLS: dict[str, Any] = {
    # Group A — corpus introspection
    "list_rule_systems": tool_list_rule_systems,
    "list_rule_categories": tool_list_rule_categories,
    "list_rule_kinds": tool_list_rule_kinds,
    "list_input_shapes": tool_list_input_shapes,
    "get_rules": tool_get_rules,
    "get_rule": tool_get_rule,
    "explain_rule": tool_explain_rule,
    # Group C — Fux checkers
    "check_melodic_interval": tool_check_melodic_interval,
    "check_melodic_triple": tool_check_melodic_triple,
    "check_motion_pair": tool_check_motion_pair,
    "check_vertical_chord": tool_check_vertical_chord,
    "check_first_interval": tool_check_first_interval,
    "check_final_interval": tool_check_final_interval,
    "check_per_measure_downbeat": tool_check_per_measure_downbeat,
    "check_weak_beat_interval": tool_check_weak_beat_interval,
    "check_dissonance_context": tool_check_dissonance_context,
    # Group D — passage evaluator
    "evaluate_passage": tool_evaluate_passage,
    # Group B — EIS helpers
    "eis_pick_root_line": tool_eis_pick_root_line,
    "eis_list_scales": tool_eis_list_scales,
    "eis_list_chord_classes": tool_eis_list_chord_classes,
    "eis_build_chord": tool_eis_build_chord,
    "eis_voice_lead": tool_eis_voice_lead,
    "eis_check_voice_leading": tool_eis_check_voice_leading,
    "eis_insert_nct": tool_eis_insert_nct,
    "eis_list_nct_types": tool_eis_list_nct_types,
    "eis_check_ood": tool_eis_check_ood,
    # Group E — SkyTNT bridge
    "skytnt_generate": tool_skytnt_generate,
    "skytnt_constrained_generate": tool_skytnt_constrained_generate,
    "midi_to_rolls": tool_midi_to_rolls,
    "rolls_to_midi": tool_rolls_to_midi,
}


def list_tool_names() -> list[str]:
    """Return every tool name this adapter exposes. Useful for sanity tests."""
    return list(_TOOLS.keys())


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Invoke a tool by name. Used by tests and the OpenAI dispatcher.

    Raises:
        KeyError: if ``name`` isn't a registered tool.
        TypeError: if ``arguments`` don't match the tool's signature.
    """
    try:
        fn = _TOOLS[name]
    except KeyError as exc:
        raise KeyError(
            f"Unknown MCP tool: {name!r}. "
            f"Available: {', '.join(sorted(_TOOLS))}"
        ) from exc
    return fn(**(arguments or {}))


# ---------------------------------------------------------------------------
# Server factory + main entry point
# ---------------------------------------------------------------------------


def build_server() -> Any:
    """Construct a fresh :class:`fastmcp.FastMCP` server with every tool registered.

    ``fastmcp`` is imported lazily so the rest of the module remains
    importable in environments where ``fastmcp`` isn't installed yet.
    """
    from fastmcp import FastMCP  # local import keeps the module light

    server = FastMCP(
        "music-rules",
        instructions=(
            "Music theory rule checker for Fuxian counterpoint and the Equal "
            "Interval System (EIS). Discover rules with list_rule_systems / "
            "get_rules, validate fragments with the check_* tools, and grade "
            "complete passages with evaluate_passage."
        ),
    )
    for name, fn in _TOOLS.items():
        server.tool(name=name)(fn)
    return server


def main() -> None:
    """Entry point for the ``music-rules-mcp`` console script.

    Runs the server over stdio (the transport used by Claude Desktop,
    Cursor, and most MCP clients today). HTTP transport can be added
    by reading an env var or a CLI flag in a future iteration.
    """
    server = build_server()
    server.run()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
