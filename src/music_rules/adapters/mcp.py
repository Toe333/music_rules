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

* **Groups B & E — Stubs** (return ``"not_implemented"`` payloads with
  a clear pointer to Phase 7)
    * ``eis_pick_root_line`` / ``eis_list_scales`` / ``eis_build_chord``
      / ``eis_voice_lead`` / ``eis_insert_nct`` / ``eis_check_ood``
    * ``skytnt_generate`` / ``skytnt_constrained_generate``
      / ``midi_to_rolls`` / ``rolls_to_midi``

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
from music_rules.core.eis import roots as eis_roots
from music_rules.core.eis import scales as eis_scales
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
    scale_id: str,
    chord_class: str,
    parts: int = 4,
) -> dict[str, Any]:
    """Build an EIS chord (triad → polytonal). Coming in Phase 8."""
    del root, scale_id, chord_class, parts
    return _stub(
        "eis_build_chord",
        "Build an EIS chord from a root + scale + chord class.",
    )


def tool_eis_voice_lead(
    prev_chord: list[int],
    next_chord: list[int],
    mode: str = "strict",
) -> dict[str, Any]:
    """Voice-lead between two EIS chords (rules V-001..V-015). Coming in Phase 8."""
    del prev_chord, next_chord, mode
    return _stub(
        "eis_voice_lead",
        "Apply EIS voice-leading rules (V-001..V-015) between two chords.",
    )


def tool_eis_insert_nct(
    voice: list[int],
    nct_type: str,
    beat: float,
) -> dict[str, Any]:
    """Insert an EIS non-chord tone (PT/CA/RT/CT/Sus/Ant). Coming in Phase 8."""
    del voice, nct_type, beat
    return _stub(
        "eis_insert_nct",
        "Insert a non-chord tone into a melodic line per EIS NCT rules.",
    )


def tool_eis_check_ood(
    chord: list[int],
    outside_octave_pairs: list[list[int]] | None = None,
) -> dict[str, Any]:
    """Check EIS Outside-Octave-Doubling rules. Coming in Phase 8."""
    del chord, outside_octave_pairs
    return _stub(
        "eis_check_ood",
        "Check Outside-Octave Doubling for an EIS chord voicing.",
    )


def tool_skytnt_generate(
    prompt_midi: str | None = None,
    conditioning: dict[str, Any] | None = None,
    num_candidates: int = 4,
    temperature: float = 1.0,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate raw MIDI with SkyTNT's ``midi-model``. Coming in Phase 8."""
    del prompt_midi, conditioning, num_candidates, temperature, seed
    return _stub(
        "skytnt_generate",
        "Generate MIDI candidates from SkyTNT's HuggingFace midi-model.",
    )


def tool_skytnt_constrained_generate(
    prompt_midi: str | None = None,
    conditioning: dict[str, Any] | None = None,
    ruleset: str = "both",
    strict: bool = False,
    max_hard_violations: int = 0,
    max_total_cost: float = 10.0,
    num_candidates_per_try: int = 8,
    max_tries: int = 8,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate + reject-sample MIDI candidates against the rule corpus. Coming in Phase 8."""
    del (
        prompt_midi, conditioning, ruleset, strict,
        max_hard_violations, max_total_cost,
        num_candidates_per_try, max_tries, seed,
    )
    return _stub(
        "skytnt_constrained_generate",
        "Loop SkyTNT generation through evaluate_passage and return the best candidate.",
    )


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
) -> dict[str, Any]:
    """Encode per-voice MIDI-number lists into a base64 MIDI blob.

    Args:
        voices:         one MIDI-number list per voice (``-1`` = rest).
        meter:          time signature like ``"4/4"``.
        tempo:          microseconds per quarter note (default 120 BPM).
        ticks_per_beat: PPQN (default 480, GM-friendly).
        velocity:       note-on velocity (1..127).
        program:        General MIDI program number for every track.

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
    # Group B — EIS helpers (Phase 7 stubs)
    "eis_pick_root_line": tool_eis_pick_root_line,
    "eis_list_scales": tool_eis_list_scales,
    "eis_build_chord": tool_eis_build_chord,
    "eis_voice_lead": tool_eis_voice_lead,
    "eis_insert_nct": tool_eis_insert_nct,
    "eis_check_ood": tool_eis_check_ood,
    # Group E — SkyTNT bridge (Phase 7 stubs)
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
