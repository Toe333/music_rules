"""Command-line adapter — the ``music-rules`` console script.

Built with Typer, kept deliberately small and orthogonal: each command
is a thin wrapper around a core function or an MCP-adapter call.
Adding a command should never require touching :mod:`music_rules.core`.

Commands::

    music-rules rules list   [--system EIS|Fux] [--category C] [--kind K]
                             [--input-shape S] [--limit N] [--json]
    music-rules rules show   <rule_id> [--json]
    music-rules rules search <text>    [--json] [--limit N]
    music-rules evaluate     <piece.json> [--species N] [--strict] [--json]
                                          [--ruleset Fux|EIS|both]
                                          [--include id ...] [--exclude id ...]
    music-rules tools list                 [--json]
    music-rules tools schema [--name X]    [--json]
    music-rules mcp serve                  # run the FastMCP server over stdio

Output style
------------

Every command supports ``--json`` for machine-readable output. The
default is a compact, terminal-friendly rendering (tables for lists,
key/value blocks for single records, indented summaries for evaluator
reports). We deliberately avoid a heavy table library — Typer +
``str.format`` is plenty for the data sizes involved here (158 rules,
~25 tools).
"""

from __future__ import annotations

import base64
import csv
import glob
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer

from music_rules import __version__
from music_rules.adapters import mcp as mcp_adapter
from music_rules.adapters import openai as openai_adapter
from music_rules.core import corpus
from music_rules.core import evaluate as core_evaluate
from music_rules.core import reporting as core_reporting
from music_rules.core.midi import render as midi_render

_GRADE_ORDER: dict[str, int] = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
_PREFERRED_SF2_NAMES: tuple[str, ...] = ("FluidR3_GM.sf2", "TimGM6mb.sf2", "default-GM.sf2")

# ---------------------------------------------------------------------------
# Top-level Typer app
# ---------------------------------------------------------------------------


app = typer.Typer(
    name="music-rules",
    help=(
        "Music theory rule checker for Fuxian counterpoint and the Equal "
        "Interval System (EIS). Use `music-rules rules list` to discover "
        "rules and `music-rules evaluate <piece.json>` to grade a passage."
    ),
    no_args_is_help=True,
    add_completion=False,
)

rules_app = typer.Typer(name="rules", help="Browse the rule corpus.", no_args_is_help=True)
tools_app = typer.Typer(name="tools", help="Inspect the AI tool surface.", no_args_is_help=True)
mcp_app = typer.Typer(name="mcp", help="Run the MCP server.", no_args_is_help=True)
progression_app = typer.Typer(
    name="progression",
    help="Render chord-progression tables to MIDI files.",
    no_args_is_help=True,
)
app.add_typer(rules_app)
app.add_typer(tools_app)
app.add_typer(mcp_app)
app.add_typer(progression_app)


# ---------------------------------------------------------------------------
# music-rules version
# ---------------------------------------------------------------------------


@app.command("version")
def version() -> None:
    """Print the installed music-rules version and exit."""
    typer.echo(__version__)


# ---------------------------------------------------------------------------
# music-rules rules ...
# ---------------------------------------------------------------------------


@rules_app.command("list")
def rules_list(
    system: str | None = typer.Option(None, "--system", "-s", help="EIS | Fux"),
    category: str | None = typer.Option(None, "--category", "-c"),
    kind: str | None = typer.Option(
        None, "--kind", "-k", help="hard | soft | hybrid | informational"
    ),
    input_shape: str | None = typer.Option(None, "--input-shape", "-i"),
    species: str | None = typer.Option(None, "--species"),
    voices: str | None = typer.Option(None, "--voices"),
    limit: int = typer.Option(50, "--limit", "-n", min=1, max=500),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """List rules matching the supplied filters (AND-combined)."""
    rules = corpus.get_rules(
        system=system,  # type: ignore[arg-type]
        category=category,
        kind=kind,  # type: ignore[arg-type]
        input_shape=input_shape,
        species=species,
        voices=voices,
        limit=limit,
    )

    if as_json:
        typer.echo(json.dumps([r.model_dump() for r in rules], indent=2))
        return

    if not rules:
        typer.echo("No rules matched the supplied filters.")
        raise typer.Exit(code=0)

    _print_rules_table(rules)
    typer.echo(f"\n{len(rules)} rule(s) shown.")


@rules_app.command("show")
def rules_show(
    rule_id: str = typer.Argument(..., help="Rule ID, e.g. 'P1_1_2v' or 'V-014'."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show one rule in full."""
    try:
        rule = corpus.get_rule(rule_id)
    except KeyError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if as_json:
        typer.echo(json.dumps(rule.model_dump(), indent=2))
        return

    _print_rule_block(rule.model_dump())


@rules_app.command("search")
def rules_search(
    text: str = typer.Argument(..., help="Free-text substring to search rule statements for."),
    limit: int = typer.Option(20, "--limit", "-n"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Substring search across rule statements (case-insensitive)."""
    needle = text.lower()
    matches = [
        r
        for r in corpus.get_rules(limit=10_000)
        if needle in r.rule.lower() or needle in (r.scope or "").lower()
    ][:limit]

    if as_json:
        typer.echo(json.dumps([r.model_dump() for r in matches], indent=2))
        return

    if not matches:
        typer.echo(f"No rules contain {text!r}.")
        raise typer.Exit(code=0)

    _print_rules_table(matches)
    typer.echo(f"\n{len(matches)} rule(s) matched {text!r}.")


# ---------------------------------------------------------------------------
# music-rules evaluate
# ---------------------------------------------------------------------------


@app.command("evaluate")
def evaluate(
    piece_path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        file_okay=True,
        dir_okay=False,
        help="Path to a piece JSON file (see PROJECT.md for the schema).",
    ),
    species: int | None = typer.Option(None, "--species", help="Override the species in the file."),
    strict: bool = typer.Option(False, "--strict", help="Promote hybrid rules to hard violations."),
    ruleset: str = typer.Option("Fux", "--ruleset", help="Fux | EIS | both"),
    include: list[str] = typer.Option(
        [], "--include", help="Only report these rule IDs (repeatable)."
    ),
    exclude: list[str] = typer.Option(
        [], "--exclude", help="Suppress these rule IDs (repeatable)."
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Evaluate a passage and print a report (or full JSON with --json)."""
    try:
        piece: dict[str, Any] = json.loads(piece_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        typer.echo(f"error: {piece_path} is not valid JSON: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if species is not None:
        piece["species"] = species

    try:
        report = core_evaluate.evaluate_passage(
            piece,  # type: ignore[arg-type]
            ruleset=ruleset,  # type: ignore[arg-type]
            strict=strict,
            include=include or None,
            exclude=exclude or None,
        )
    except ValueError as exc:
        typer.echo(f"error: invalid piece — {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if as_json:
        typer.echo(json.dumps(report, indent=2))
        return

    _print_passage_report(report, piece_path=piece_path)
    if report["hard_violations"]:
        raise typer.Exit(code=1)


@app.command("evaluate-explain")
def evaluate_explain(
    report_path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        file_okay=True,
        dir_okay=False,
        help="Path to an evaluate_passage JSON report.",
    ),
    top_n: int = typer.Option(5, "--top-n", min=1, max=20),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Explain an evaluator JSON report in fix-priority order."""
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        typer.echo(f"error: {report_path} is not valid JSON: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if as_json:
        summary = core_reporting.summarize_passage_report(report, top_n=top_n)
        typer.echo(json.dumps(summary, indent=2))
        return

    typer.echo(core_reporting.format_passage_report_summary(report, top_n=top_n))


# ---------------------------------------------------------------------------
# music-rules tools ...
# ---------------------------------------------------------------------------


@tools_app.command("list")
def tools_list(as_json: bool = typer.Option(False, "--json")) -> None:
    """List every AI-callable tool exposed by the MCP / OpenAI adapters."""
    names = mcp_adapter.list_tool_names()
    if as_json:
        typer.echo(json.dumps(names, indent=2))
        return
    typer.echo(f"{len(names)} tool(s):")
    for n in names:
        typer.echo(f"  - {n}")


@tools_app.command("schema")
def tools_schema(
    name: str | None = typer.Option(
        None, "--name", help="Single tool name; omit to dump the full catalogue."
    ),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """Print OpenAI function-calling schemas (default: JSON to stdout)."""
    if name is not None:
        try:
            schema: Any = openai_adapter.get_tool_schema(name)
        except KeyError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=2) from exc
    else:
        schema = openai_adapter.get_tools_schema()

    if as_json:
        typer.echo(json.dumps(schema, indent=2))
    else:
        typer.echo(repr(schema))


# ---------------------------------------------------------------------------
# music-rules mcp serve
# ---------------------------------------------------------------------------


@mcp_app.command("serve")
def mcp_serve() -> None:
    """Run the FastMCP server over stdio (for Claude Desktop / Cursor)."""
    mcp_adapter.main()


# ---------------------------------------------------------------------------
# music-rules progression ...
# ---------------------------------------------------------------------------


@progression_app.command("render-csv")
def progression_render_csv(
    progression_csv_path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        file_okay=True,
        dir_okay=False,
        help="CSV with chord events (chord_symbol, duration_beats, start_beat).",
    ),
    chord_lexicon_path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        file_okay=True,
        dir_okay=False,
        help="Lexicon JSON exported by examples/export_chord_tables.py.",
    ),
    out_midi_path: Path = typer.Argument(
        ...,
        help="Where to write the rendered .mid file.",
    ),
    steps_per_beat: int = typer.Option(1, "--steps-per-beat", min=1),
    rest_symbol: str = typer.Option("REST", "--rest-symbol"),
    strict_missing: bool = typer.Option(True, "--strict-missing/--allow-missing"),
    meter: str = typer.Option("4/4", "--meter"),
    tempo: int = typer.Option(500_000, "--tempo"),
    ticks_per_beat: int = typer.Option(480, "--ticks-per-beat"),
    velocity: int = typer.Option(80, "--velocity", min=1, max=127),
    program: int = typer.Option(0, "--program", min=0, max=127),
) -> None:
    """Render a progression CSV to a MIDI file on disk."""
    progression = midi_render.read_progression_csv(str(progression_csv_path))
    symbol_to_midi = midi_render.load_chord_lexicon(None, str(chord_lexicon_path))
    voices, total_steps, unresolved = midi_render.progression_to_rolls(
        progression,
        symbol_to_midi,
        steps_per_beat=steps_per_beat,
        rest_symbol=rest_symbol,
    )
    if unresolved and strict_missing:
        preview = ", ".join(unresolved[:8])
        typer.echo(
            "error: unresolved chord symbols: "
            f"{preview}{' ...' if len(unresolved) > 8 else ''}",
            err=True,
        )
        raise typer.Exit(code=2)

    midi_b64 = midi_render.progression_to_midi(
        voices,
        meter=meter,
        tempo=tempo,
        ticks_per_beat=ticks_per_beat,
        velocity=velocity,
        program=program,
    )

    out_midi_path.parent.mkdir(parents=True, exist_ok=True)
    out_midi_path.write_bytes(base64.b64decode(midi_b64))
    typer.echo(
        f"Wrote {out_midi_path} | voices={len(voices)} steps={total_steps} "
        f"unresolved={len(unresolved)}"
    )


@progression_app.command("render-voiced-csv")
def progression_render_voiced_csv(
    voiced_csv_path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        file_okay=True,
        dir_okay=False,
        help="CSV with per-bar voiced MIDI columns (e.g. chord_midis, melody_qn_midis).",
    ),
    out_midi_path: Path = typer.Argument(
        ...,
        help="Where to write the rendered .mid file.",
    ),
    chord_column: str = typer.Option("chord_midis", "--chord-column"),
    melody_column: str = typer.Option("melody_qn_midis", "--melody-column"),
    include_melody: bool = typer.Option(True, "--include-melody/--no-melody"),
    beats_per_bar: int = typer.Option(4, "--beats-per-bar", min=1, max=16),
    meter: str = typer.Option("4/4", "--meter"),
    tempo: int = typer.Option(500_000, "--tempo"),
    ticks_per_beat: int = typer.Option(480, "--ticks-per-beat"),
    velocity: int = typer.Option(80, "--velocity", min=1, max=127),
    harmony_program: int = typer.Option(0, "--harmony-program", min=0, max=127),
    melody_program: int = typer.Option(65, "--melody-program", min=0, max=127),
    write_wav: bool = typer.Option(False, "--write-wav"),
    wav_out_path: Path | None = typer.Option(None, "--wav-out-path"),
    soundfont_path: Path | None = typer.Option(None, "--soundfont-path"),
    wav_required: bool = typer.Option(False, "--wav-required"),
) -> None:
    """Render voiced per-bar CSV tables (like eis_*_harmonized.csv) to MIDI."""
    with voiced_csv_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    try:
        voices = _render_voiced_rows(
            rows,
            chord_column=chord_column,
            melody_column=melody_column,
            include_melody=include_melody,
            beats_per_bar=beats_per_bar,
        )
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    programs = [harmony_program] * (len(voices) - (1 if include_melody else 0))
    if include_melody:
        programs.append(melody_program)

    midi_b64 = midi_render.progression_to_midi(
        voices,
        meter=meter,
        tempo=tempo,
        ticks_per_beat=ticks_per_beat,
        velocity=velocity,
        programs=programs,
    )
    out_midi_path.parent.mkdir(parents=True, exist_ok=True)
    out_midi_path.write_bytes(base64.b64decode(midi_b64))
    total_steps = len(voices[0]) if voices else 0
    typer.echo(f"Wrote {out_midi_path} | voices={len(voices)} steps={total_steps}")
    if write_wav:
        wav_path = wav_out_path or out_midi_path.with_suffix(".wav")
        ok, msg = _try_render_wav(
            out_midi_path=out_midi_path,
            out_wav_path=wav_path,
            soundfont_path=soundfont_path,
        )
        if ok:
            typer.echo(f"Wrote {wav_path}")
        else:
            typer.echo(f"warn: {msg}", err=True)
            if wav_required:
                raise typer.Exit(code=2)


@progression_app.command("render-voiced-batch")
def progression_render_voiced_batch(
    glob_pattern: str = typer.Argument(
        "examples/eis_*_harmonized.csv",
        help="Glob pattern for voiced CSV tables.",
    ),
    out_dir: Path | None = typer.Option(None, "--out-dir"),
    suffix: str = typer.Option("_cli.mid", "--suffix"),
    chord_column: str = typer.Option("chord_midis", "--chord-column"),
    melody_column: str = typer.Option("melody_qn_midis", "--melody-column"),
    include_melody: bool = typer.Option(True, "--include-melody/--no-melody"),
    beats_per_bar: int = typer.Option(4, "--beats-per-bar", min=1, max=16),
    meter: str = typer.Option("4/4", "--meter"),
    tempo: int = typer.Option(500_000, "--tempo"),
    ticks_per_beat: int = typer.Option(480, "--ticks-per-beat"),
    velocity: int = typer.Option(80, "--velocity", min=1, max=127),
    harmony_program: int = typer.Option(0, "--harmony-program", min=0, max=127),
    melody_program: int = typer.Option(65, "--melody-program", min=0, max=127),
    write_wav: bool = typer.Option(False, "--write-wav"),
    wav_out_dir: Path | None = typer.Option(None, "--wav-out-dir"),
    soundfont_path: Path | None = typer.Option(None, "--soundfont-path"),
    wav_required: bool = typer.Option(False, "--wav-required"),
) -> None:
    """Batch-render multiple voiced CSV tables to MIDI."""
    matches = sorted(Path(p) for p in glob.glob(glob_pattern))
    if not matches:
        typer.echo(f"error: no files matched {glob_pattern!r}", err=True)
        raise typer.Exit(code=2)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    if wav_out_dir is not None:
        wav_out_dir.mkdir(parents=True, exist_ok=True)

    programs_tail = [melody_program] if include_melody else []
    failures: list[str] = []
    wav_failures: list[str] = []
    rendered = 0
    for csv_path in matches:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        try:
            voices = _render_voiced_rows(
                rows,
                chord_column=chord_column,
                melody_column=melody_column,
                include_melody=include_melody,
                beats_per_bar=beats_per_bar,
            )
        except ValueError as exc:
            failures.append(f"{csv_path}: {exc}")
            continue

        harmony_count = len(voices) - (1 if include_melody else 0)
        programs = [harmony_program] * harmony_count + programs_tail
        midi_b64 = midi_render.progression_to_midi(
            voices,
            meter=meter,
            tempo=tempo,
            ticks_per_beat=ticks_per_beat,
            velocity=velocity,
            programs=programs,
        )
        out_name = f"{csv_path.stem}{suffix}"
        out_path = (out_dir / out_name) if out_dir is not None else csv_path.with_name(out_name)
        out_path.write_bytes(base64.b64decode(midi_b64))
        if write_wav:
            wav_name = f"{csv_path.stem}{suffix}".replace(".mid", ".wav")
            wav_path = (wav_out_dir / wav_name) if wav_out_dir is not None else out_path.with_suffix(".wav")
            ok, msg = _try_render_wav(
                out_midi_path=out_path,
                out_wav_path=wav_path,
                soundfont_path=soundfont_path,
            )
            if ok:
                typer.echo(f"Wrote {wav_path}")
            else:
                wav_failures.append(f"{csv_path}: {msg}")
        rendered += 1
        typer.echo(f"Wrote {out_path}")

    typer.echo(f"Rendered {rendered}/{len(matches)} files")
    if failures:
        for line in failures:
            typer.echo(f"error: {line}", err=True)
        raise typer.Exit(code=1)
    if wav_required and wav_failures:
        for line in wav_failures:
            typer.echo(f"error: {line}", err=True)
        raise typer.Exit(code=2)
    if wav_failures:
        for line in wav_failures:
            typer.echo(f"warn: {line}", err=True)


@progression_app.command("audit-voiced-csv")
def progression_audit_voiced_csv(
    voiced_csv_path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        file_okay=True,
        dir_okay=False,
        help="CSV with per-bar voiced MIDI columns.",
    ),
    chord_column: str = typer.Option("chord_midis", "--chord-column"),
    melody_column: str = typer.Option("melody_qn_midis", "--melody-column"),
    include_melody: bool = typer.Option(True, "--include-melody/--no-melody"),
    beats_per_bar: int = typer.Option(4, "--beats-per-bar", min=1, max=16),
    ruleset: str = typer.Option("EIS", "--ruleset", help="Fux | EIS | both"),
    species: int = typer.Option(1, "--species"),
    key: str = typer.Option("C", "--key"),
    meter: str = typer.Option("4/4", "--meter"),
    cantus_firmus_voice: int = typer.Option(0, "--cantus-firmus-voice"),
    strict: bool = typer.Option(False, "--strict"),
    min_grade: str | None = typer.Option(None, "--min-grade", help="A | B | C | D | F"),
    max_total_cost: float | None = typer.Option(None, "--max-total-cost"),
    max_hard_count: int | None = typer.Option(None, "--max-hard-count", min=0),
    fail_on_rule: list[str] = typer.Option(
        [],
        "--fail-on-rule",
        help="Rule ID that must have zero hits (repeatable).",
    ),
    max_rule_total_cost: list[str] = typer.Option(
        [],
        "--max-rule-total-cost",
        help="Per-rule cost cap as RULE_ID=FLOAT (repeatable).",
    ),
    report_out: Path | None = typer.Option(None, "--report-out"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Evaluate a voiced progression CSV and print a compact audit summary."""
    with voiced_csv_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    try:
        voices = _render_voiced_rows(
            rows,
            chord_column=chord_column,
            melody_column=melody_column,
            include_melody=include_melody,
            beats_per_bar=beats_per_bar,
        )
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    piece: dict[str, Any] = {
        "voices": voices,
        "meter": meter,
        "key": key,
        "species": species,
        "cantus_firmus_voice": cantus_firmus_voice,
    }
    report = core_evaluate.evaluate_passage(piece, ruleset=ruleset, strict=strict)

    if report_out is not None:
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if as_json:
        typer.echo(json.dumps(report, indent=2))
    else:
        typer.echo(core_reporting.format_passage_report_summary(report))

    if report["hard_violations"]:
        raise typer.Exit(code=1)
    try:
        rule_cost_limits = _parse_rule_cost_limits(max_rule_total_cost)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    gate_msg = _quality_gate_failure(
        report,
        min_grade=min_grade,
        max_total_cost=max_total_cost,
        max_hard_count=max_hard_count,
        fail_on_rule=fail_on_rule,
        max_rule_total_cost=rule_cost_limits,
    )
    if gate_msg is not None:
        typer.echo(f"error: {gate_msg}", err=True)
        raise typer.Exit(code=1)


@progression_app.command("audit-voiced-batch")
def progression_audit_voiced_batch(
    glob_pattern: str = typer.Argument(
        "examples/eis_*_harmonized.csv",
        help="Glob pattern for voiced CSV tables.",
    ),
    chord_column: str = typer.Option("chord_midis", "--chord-column"),
    melody_column: str = typer.Option("melody_qn_midis", "--melody-column"),
    include_melody: bool = typer.Option(True, "--include-melody/--no-melody"),
    beats_per_bar: int = typer.Option(4, "--beats-per-bar", min=1, max=16),
    ruleset: str = typer.Option("EIS", "--ruleset", help="Fux | EIS | both"),
    species: int = typer.Option(1, "--species"),
    key: str = typer.Option("C", "--key"),
    meter: str = typer.Option("4/4", "--meter"),
    cantus_firmus_voice: int = typer.Option(0, "--cantus-firmus-voice"),
    strict: bool = typer.Option(False, "--strict"),
    min_grade: str | None = typer.Option(None, "--min-grade", help="A | B | C | D | F"),
    max_total_cost: float | None = typer.Option(None, "--max-total-cost"),
    max_hard_count: int | None = typer.Option(None, "--max-hard-count", min=0),
    fail_on_rule: list[str] = typer.Option(
        [],
        "--fail-on-rule",
        help="Rule ID that must have zero hits (repeatable).",
    ),
    max_rule_total_cost: list[str] = typer.Option(
        [],
        "--max-rule-total-cost",
        help="Per-rule cost cap as RULE_ID=FLOAT (repeatable).",
    ),
    summary_out: Path | None = typer.Option(None, "--summary-out"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Batch-audit voiced CSV tables and print one-line results."""
    matches = sorted(Path(p) for p in glob.glob(glob_pattern))
    if not matches:
        typer.echo(f"error: no files matched {glob_pattern!r}", err=True)
        raise typer.Exit(code=2)

    try:
        rule_cost_limits = _parse_rule_cost_limits(max_rule_total_cost)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    summary_items: list[dict[str, Any]] = []
    hard_failures = 0
    parse_failures = 0
    quality_failures = 0
    for csv_path in matches:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        try:
            voices = _render_voiced_rows(
                rows,
                chord_column=chord_column,
                melody_column=melody_column,
                include_melody=include_melody,
                beats_per_bar=beats_per_bar,
            )
        except ValueError as exc:
            parse_failures += 1
            typer.echo(f"{csv_path.name}: parse_error={exc}")
            summary_items.append(
                {"file": str(csv_path), "ok": False, "error": str(exc)}
            )
            continue

        piece: dict[str, Any] = {
            "voices": voices,
            "meter": meter,
            "key": key,
            "species": species,
            "cantus_firmus_voice": cantus_firmus_voice,
        }
        report = core_evaluate.evaluate_passage(piece, ruleset=ruleset, strict=strict)
        hard_count = len(report["hard_violations"])
        if hard_count:
            hard_failures += 1
        if not as_json:
            typer.echo(
                f"{csv_path.name}: grade={report['grade']} "
                f"hard={hard_count} soft={len(report['soft_violations'])} "
                f"cost={report['total_cost']}"
            )
        summary = core_reporting.summarize_passage_report(report)
        gate_msg = _quality_gate_failure(
            report,
            min_grade=min_grade,
            max_total_cost=max_total_cost,
            max_hard_count=max_hard_count,
            fail_on_rule=fail_on_rule,
            max_rule_total_cost=rule_cost_limits,
        )
        if gate_msg is not None:
            quality_failures += 1
        summary_items.append(
            {
                "file": str(csv_path),
                "ok": hard_count == 0 and gate_msg is None,
                "grade": report["grade"],
                "hard_count": hard_count,
                "soft_count": len(report["soft_violations"]),
                "total_cost": report["total_cost"],
                "quality_gate_error": gate_msg,
                "top_hard_rules": summary["top_hard_rules"],
                "top_soft_rules": summary["top_soft_rules"],
            }
        )

    payload = {
        "ruleset": ruleset,
        "items": summary_items,
        "hard_failures": hard_failures,
        "parse_failures": parse_failures,
        "quality_failures": quality_failures,
        "file_count": len(matches),
    }
    if summary_out is not None:
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if as_json:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(
            f"Audited {len(matches)} files | hard_failures={hard_failures} "
            f"parse_failures={parse_failures} quality_failures={quality_failures}"
        )
    if hard_failures or parse_failures or quality_failures:
        raise typer.Exit(code=1)


@progression_app.command("find-soundfonts")
def progression_find_soundfonts(
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List likely SoundFont files (.sf2/.sf3) from common Linux paths."""
    candidates = [str(p) for p in _find_soundfonts()]
    if as_json:
        typer.echo(json.dumps(candidates, indent=2))
        return
    if not candidates:
        typer.echo("No soundfonts found in common paths.")
        raise typer.Exit(code=1)
    typer.echo("Found soundfonts:")
    for path in candidates:
        typer.echo(f"  - {path}")


@progression_app.command("pipeline-voiced-batch")
def progression_pipeline_voiced_batch(
    glob_pattern: str = typer.Argument(
        "examples/eis_*_harmonized.csv",
        help="Glob pattern for voiced CSV tables.",
    ),
    out_dir: Path = typer.Option(Path("examples"), "--out-dir"),
    suffix: str = typer.Option("_cli.mid", "--suffix"),
    chord_column: str = typer.Option("chord_midis", "--chord-column"),
    melody_column: str = typer.Option("melody_qn_midis", "--melody-column"),
    include_melody: bool = typer.Option(True, "--include-melody/--no-melody"),
    beats_per_bar: int = typer.Option(4, "--beats-per-bar", min=1, max=16),
    meter: str = typer.Option("4/4", "--meter"),
    tempo: int = typer.Option(500_000, "--tempo"),
    ticks_per_beat: int = typer.Option(480, "--ticks-per-beat"),
    velocity: int = typer.Option(80, "--velocity", min=1, max=127),
    harmony_program: int = typer.Option(0, "--harmony-program", min=0, max=127),
    melody_program: int = typer.Option(65, "--melody-program", min=0, max=127),
    write_wav: bool = typer.Option(False, "--write-wav"),
    wav_out_dir: Path | None = typer.Option(None, "--wav-out-dir"),
    soundfont_path: Path | None = typer.Option(None, "--soundfont-path"),
    wav_required: bool = typer.Option(False, "--wav-required"),
    ruleset: str = typer.Option("EIS", "--ruleset", help="Fux | EIS | both"),
    species: int = typer.Option(1, "--species"),
    key: str = typer.Option("C", "--key"),
    cantus_firmus_voice: int = typer.Option(0, "--cantus-firmus-voice"),
    strict: bool = typer.Option(False, "--strict"),
    min_grade: str | None = typer.Option(None, "--min-grade", help="A | B | C | D | F"),
    max_total_cost: float | None = typer.Option(None, "--max-total-cost"),
    max_hard_count: int | None = typer.Option(None, "--max-hard-count", min=0),
    fail_on_rule: list[str] = typer.Option(
        [],
        "--fail-on-rule",
        help="Rule ID that must have zero hits (repeatable).",
    ),
    max_rule_total_cost: list[str] = typer.Option(
        [],
        "--max-rule-total-cost",
        help="Per-rule cost cap as RULE_ID=FLOAT (repeatable).",
    ),
    summary_out: Path | None = typer.Option(None, "--summary-out"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run render (+ optional wav) + audit over a voiced CSV batch."""
    matches = sorted(Path(p) for p in glob.glob(glob_pattern))
    if not matches:
        typer.echo(f"error: no files matched {glob_pattern!r}", err=True)
        raise typer.Exit(code=2)
    out_dir.mkdir(parents=True, exist_ok=True)
    if wav_out_dir is not None:
        wav_out_dir.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, Any]] = []
    parse_failures = 0
    hard_failures = 0
    wav_failures = 0
    quality_failures = 0
    try:
        rule_cost_limits = _parse_rule_cost_limits(max_rule_total_cost)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    for csv_path in matches:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        try:
            voices = _render_voiced_rows(
                rows,
                chord_column=chord_column,
                melody_column=melody_column,
                include_melody=include_melody,
                beats_per_bar=beats_per_bar,
            )
        except ValueError as exc:
            parse_failures += 1
            items.append(
                {"file": str(csv_path), "ok": False, "error": str(exc)}
            )
            if not as_json:
                typer.echo(f"{csv_path.name}: parse_error={exc}")
            continue

        programs = [harmony_program] * (len(voices) - (1 if include_melody else 0))
        if include_melody:
            programs.append(melody_program)
        midi_b64 = midi_render.progression_to_midi(
            voices,
            meter=meter,
            tempo=tempo,
            ticks_per_beat=ticks_per_beat,
            velocity=velocity,
            programs=programs,
        )
        out_name = f"{csv_path.stem}{suffix}"
        midi_out = out_dir / out_name
        midi_out.write_bytes(base64.b64decode(midi_b64))

        wav_out: str | None = None
        wav_warning: str | None = None
        if write_wav:
            wav_name = out_name.replace(".mid", ".wav")
            wav_path = (wav_out_dir / wav_name) if wav_out_dir is not None else midi_out.with_suffix(".wav")
            ok, msg = _try_render_wav(
                out_midi_path=midi_out,
                out_wav_path=wav_path,
                soundfont_path=soundfont_path,
            )
            if ok:
                wav_out = str(wav_path)
            else:
                wav_failures += 1
                wav_warning = msg

        piece: dict[str, Any] = {
            "voices": voices,
            "meter": meter,
            "key": key,
            "species": species,
            "cantus_firmus_voice": cantus_firmus_voice,
        }
        report = core_evaluate.evaluate_passage(piece, ruleset=ruleset, strict=strict)
        hard_count = len(report["hard_violations"])
        if hard_count:
            hard_failures += 1
        summary = core_reporting.summarize_passage_report(report)
        gate_msg = _quality_gate_failure(
            report,
            min_grade=min_grade,
            max_total_cost=max_total_cost,
            max_hard_count=max_hard_count,
            fail_on_rule=fail_on_rule,
            max_rule_total_cost=rule_cost_limits,
        )
        if gate_msg is not None:
            quality_failures += 1
        item = {
            "file": str(csv_path),
            "ok": hard_count == 0 and gate_msg is None,
            "grade": report["grade"],
            "hard_count": hard_count,
            "soft_count": len(report["soft_violations"]),
            "total_cost": report["total_cost"],
            "midi_out": str(midi_out),
            "wav_out": wav_out,
            "wav_warning": wav_warning,
            "quality_gate_error": gate_msg,
            "top_hard_rules": summary["top_hard_rules"],
            "top_soft_rules": summary["top_soft_rules"],
        }
        items.append(item)
        if not as_json:
            status = "ok" if item["ok"] else "hard-fail"
            wav_note = " wav=ok" if wav_out is not None else (" wav=warn" if wav_warning else "")
            typer.echo(
                f"{csv_path.name}: {status} grade={item['grade']} "
                f"hard={item['hard_count']} soft={item['soft_count']} cost={item['total_cost']}{wav_note}"
            )

    payload = {
        "ruleset": ruleset,
        "items": items,
        "file_count": len(matches),
        "hard_failures": hard_failures,
        "parse_failures": parse_failures,
        "wav_failures": wav_failures,
        "quality_failures": quality_failures,
    }
    if summary_out is not None:
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if as_json:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(
            f"Processed {len(matches)} files | hard_failures={hard_failures} "
            f"parse_failures={parse_failures} wav_failures={wav_failures} "
            f"quality_failures={quality_failures}"
        )
    if parse_failures or hard_failures or quality_failures or (wav_required and wav_failures):
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Pretty-printers
# ---------------------------------------------------------------------------


def _print_rules_table(rules: list[Any]) -> None:
    """Print a compact ID / system / kind / rule-statement table."""
    rows = [
        (
            r.id,
            r.system,
            r.kind,
            r.input_shape or "-",
            _truncate(r.rule, 60),
        )
        for r in rules
    ]
    headers = ("ID", "SYS", "KIND", "INPUT_SHAPE", "RULE")
    widths = [
        max(len(h), max((len(c) for c in col), default=0))
        for h, col in zip(headers, zip(*rows, strict=False), strict=False)
    ]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    typer.echo(fmt.format(*headers))
    typer.echo(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        typer.echo(fmt.format(*row))


def _print_rule_block(rule: dict[str, Any]) -> None:
    """Print a single rule as a labelled key/value block."""
    typer.echo(f"id:           {rule['id']}")
    typer.echo(f"system:       {rule['system']}")
    typer.echo(f"category:     {rule['category']}")
    typer.echo(f"kind:         {rule['kind']}")
    typer.echo(f"tier:         {rule['tier']}")
    typer.echo(f"species:      {rule.get('species') or '-'}")
    typer.echo(f"voices:       {rule.get('voices') or '-'}")
    typer.echo(f"input_shape:  {rule.get('input_shape') or '-'}")
    typer.echo(f"source:       {rule['source']}")
    typer.echo("")
    typer.echo(f"rule:    {rule['rule']}")
    typer.echo(f"scope:   {rule['scope']}")
    if rule.get("exceptions"):
        typer.echo(f"except:  {rule['exceptions']}")


def _print_passage_report(report: dict[str, Any], *, piece_path: Path) -> None:
    """Render the evaluator report in a human-friendly form."""
    grade_emoji = {"A": "★", "B": "✓", "C": "·", "D": "?", "F": "✗"}.get(report["grade"], "?")
    typer.echo(f"== {piece_path.name} ==")
    typer.echo(
        f"grade: {report['grade']} {grade_emoji}   "
        f"hard: {len(report['hard_violations'])}   "
        f"soft: {len(report['soft_violations'])}   "
        f"total_cost: {report['total_cost']}"
    )

    if report["hard_violations"]:
        typer.echo("\nHARD violations:")
        for v in report["hard_violations"]:
            typer.echo(
                f"  [{v['rule_id']:<12}] pos={v['position']:>3} "
                f"voices={v['voices_involved']}  {v['msg']}"
            )

    if report["soft_violations"]:
        typer.echo("\nSOFT costs:")
        for c in report["soft_violations"]:
            typer.echo(
                f"  [{c['rule_id']:<12}] pos={c['position']:>3} cost={c['cost']:>4}  {c['msg']}"
            )

    if report["per_rule_summary"]:
        typer.echo("\nPer-rule summary:")
        for rid, info in sorted(report["per_rule_summary"].items()):
            cost = info["total_cost"]
            cost_str = "—" if cost is None else f"{cost}"
            typer.echo(f"  {rid:<14} count={info['count']:>3}  total_cost={cost_str}")


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _parse_pipe_midis(cell: str) -> list[int]:
    parts = [tok.strip() for tok in cell.split("|") if tok.strip()]
    out: list[int] = []
    for token in parts:
        try:
            out.append(int(token))
        except ValueError:
            continue
    return out


def _render_voiced_rows(
    rows: list[dict[str, str | None]],
    *,
    chord_column: str,
    melody_column: str,
    include_melody: bool,
    beats_per_bar: int,
) -> list[list[int]]:
    if not rows:
        raise ValueError("voiced CSV has no rows")

    text_rows = [
        {
            key: "" if value is None else str(value)
            for key, value in row.items()
        }
        for row in rows
    ]
    first_chord = _parse_pipe_midis(text_rows[0].get(chord_column, ""))
    if not first_chord:
        raise ValueError(f"first row has no parseable chord data in column {chord_column!r}")

    harmony_voice_count = len(first_chord)
    harmony_voices = [[] for _ in range(harmony_voice_count)]
    melody_voice: list[int] = []

    for idx, row in enumerate(text_rows, start=1):
        chord = _parse_pipe_midis(row.get(chord_column, ""))
        if len(chord) != harmony_voice_count:
            raise ValueError(
                f"inconsistent chord voice count at row {idx} "
                f"({len(chord)} vs expected {harmony_voice_count})"
            )
        for v_idx, pitch in enumerate(chord):
            harmony_voices[v_idx].extend([pitch] * beats_per_bar)
        if include_melody:
            raw_melody = _parse_pipe_midis(row.get(melody_column, ""))
            if not raw_melody:
                raw_melody = [chord[-1]] * beats_per_bar
            if len(raw_melody) != beats_per_bar:
                raise ValueError(
                    f"melody note-count mismatch at row {idx} "
                    f"({len(raw_melody)} vs beats_per_bar={beats_per_bar})"
                )
            melody_voice.extend(raw_melody)

    voices = list(harmony_voices)
    if include_melody:
        voices.append(melody_voice)
    return voices


def _try_render_wav(
    *,
    out_midi_path: Path,
    out_wav_path: Path,
    soundfont_path: Path | None,
) -> tuple[bool, str]:
    """Attempt to synthesize a WAV file from a MIDI file.

    Strategy:
    1) Use ``fluidsynth`` when available (requires a soundfont path).
    2) Fallback to ``timidity`` if installed.
    """
    fluidsynth_bin = shutil.which("fluidsynth")
    if fluidsynth_bin is not None:
        resolved_soundfont = soundfont_path or _pick_default_soundfont()
        if resolved_soundfont is None:
            return (
                False,
                "fluidsynth found but no soundfont was provided/found",
            )
        cmd = [
            fluidsynth_bin,
            "-ni",
            str(resolved_soundfont),
            str(out_midi_path),
            "-F",
            str(out_wav_path),
            "-r",
            "44100",
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return True, "ok"
        except subprocess.CalledProcessError as exc:
            return False, f"fluidsynth failed: {exc.stderr.strip() or exc.stdout.strip()}"

    timidity_bin = shutil.which("timidity")
    if timidity_bin is not None:
        cmd = [timidity_bin, str(out_midi_path), "-Ow", "-o", str(out_wav_path)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return True, "ok"
        except subprocess.CalledProcessError as exc:
            return False, f"timidity failed: {exc.stderr.strip() or exc.stdout.strip()}"

    return False, "no MIDI synth found (install fluidsynth or timidity)"


def _find_soundfonts() -> list[Path]:
    search_roots = [
        Path.home() / ".local" / "share" / "sounds" / "sf2",
        Path.home() / ".soundfonts",
        Path("/usr/share/sounds/sf2"),
        Path("/usr/share/soundfonts"),
        Path("/usr/local/share/soundfonts"),
    ]
    found: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        for pattern in ("**/*.sf2", "**/*.SF2", "**/*.sf3", "**/*.SF3"):
            found.extend(root.glob(pattern))
    return sorted(set(found))


def _pick_default_soundfont() -> Path | None:
    found = _find_soundfonts()
    if not found:
        return None
    by_name = {p.name: p for p in found}
    for name in _PREFERRED_SF2_NAMES:
        if name in by_name:
            return by_name[name]
    return found[0]


def _quality_gate_failure(
    report: dict[str, Any],
    *,
    min_grade: str | None,
    max_total_cost: float | None,
    max_hard_count: int | None,
    fail_on_rule: list[str],
    max_rule_total_cost: dict[str, float],
) -> str | None:
    hard_count = len(report.get("hard_violations", []))
    total_cost = float(report.get("total_cost", 0.0))
    grade = str(report.get("grade", "F")).upper()

    if max_hard_count is not None and hard_count > max_hard_count:
        return f"hard_count {hard_count} exceeds max_hard_count {max_hard_count}"
    if max_total_cost is not None and total_cost > max_total_cost:
        return f"total_cost {total_cost} exceeds max_total_cost {max_total_cost}"
    if min_grade is not None:
        target = min_grade.upper()
        if target not in _GRADE_ORDER:
            return f"invalid min_grade {min_grade!r}; expected one of A,B,C,D,F"
        if grade not in _GRADE_ORDER:
            return f"unknown report grade {grade!r}"
        if _GRADE_ORDER[grade] < _GRADE_ORDER[target]:
            return f"grade {grade} is below min_grade {target}"

    per_rule = report.get("per_rule_summary", {}) or {}
    for rid in fail_on_rule:
        if rid in per_rule and int(per_rule[rid].get("count", 0)) > 0:
            return f"rule {rid} has {per_rule[rid]['count']} hit(s) but is fail-on-rule"

    for rid, cap in max_rule_total_cost.items():
        info = per_rule.get(rid)
        if info is None:
            continue
        total = info.get("total_cost")
        count = int(info.get("count", 0))
        if total is None:
            if count > 0:
                return f"rule {rid} has hard-only hits and exceeds max-rule-total-cost policy"
            continue
        if float(total) > cap:
            return f"rule {rid} total_cost {float(total)} exceeds cap {cap}"
    return None


def _parse_rule_cost_limits(entries: list[str]) -> dict[str, float]:
    limits: dict[str, float] = {}
    for item in entries:
        if "=" not in item:
            raise ValueError(
                f"Invalid --max-rule-total-cost value {item!r}; expected RULE_ID=FLOAT"
            )
        rid, raw = item.split("=", maxsplit=1)
        rid = rid.strip()
        if not rid:
            raise ValueError(
                f"Invalid --max-rule-total-cost value {item!r}; missing RULE_ID"
            )
        try:
            limit = float(raw.strip())
        except ValueError as exc:
            raise ValueError(
                f"Invalid --max-rule-total-cost value {item!r}; FLOAT is required"
            ) from exc
        limits[rid] = limit
    return limits


# ---------------------------------------------------------------------------
# Programmatic entry point (used by tests + by `python -m music_rules.adapters.cli`)
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run the CLI with the given args (or ``sys.argv`` by default).

    Returns:
        The process exit code Typer would have used.

    Notes:
        We invoke the Typer app with ``standalone_mode=False`` so that
        Click does not call :func:`sys.exit` itself. In modern Click
        (>=8.1) ``standalone_mode=False`` *returns* the would-be exit
        code rather than raising :class:`typer.Exit`; we still handle
        the exception path for older Click compatibility.
    """
    try:
        rv = app(args=argv, standalone_mode=False)
    except typer.Exit as exc:
        return int(exc.exit_code or 0)
    except SystemExit as exc:  # pragma: no cover - belt-and-suspenders
        return int(exc.code or 0)
    if isinstance(rv, int):
        return rv
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
