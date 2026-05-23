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

import json
import sys
from pathlib import Path
from typing import Any

import typer

from music_rules import __version__
from music_rules.adapters import mcp as mcp_adapter
from music_rules.adapters import openai as openai_adapter
from music_rules.core import corpus
from music_rules.core import evaluate as core_evaluate

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
app.add_typer(rules_app)
app.add_typer(tools_app)
app.add_typer(mcp_app)


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
