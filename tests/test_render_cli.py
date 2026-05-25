"""Smoke-test the ``music-rules render`` CLI subcommand.

CI scope is deliberately narrow: MIDI only (``--soundfont none``). The
timidity / fluidsynth / webplayer code paths are excluded — they shell
out to non-deterministic external binaries.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from music_rules.adapters import cli as cli_module

runner = CliRunner()


def test_render_writes_midi_for_selected_style(tmp_path: Path) -> None:
    out_dir = tmp_path / "renders"
    result = runner.invoke(
        cli_module.app,
        ["render", "--styles", "dre_g_funk", "--soundfont", "none", "--out", str(out_dir)],
    )
    assert result.exit_code == 0, result.stdout
    midi_path = out_dir / "dre_g_funk.mid"
    assert midi_path.exists()
    assert midi_path.stat().st_size > 0
    assert not (out_dir / "dre_g_funk.mp3").exists()


def test_render_glob_selects_multiple_styles(tmp_path: Path) -> None:
    out_dir = tmp_path / "renders"
    result = runner.invoke(
        cli_module.app,
        ["render", "--styles", "dre_*", "--soundfont", "none", "--out", str(out_dir)],
    )
    assert result.exit_code == 0, result.stdout
    assert (out_dir / "dre_g_funk.mid").exists()
    assert (out_dir / "dre_1990s_gangsta.mid").exists()


def test_render_unmatched_pattern_errors(tmp_path: Path) -> None:
    result = runner.invoke(
        cli_module.app,
        ["render", "--styles", "no_such_style_*", "--out", str(tmp_path)],
    )
    assert result.exit_code == 2
    assert "no bundled styles matched" in (result.stderr or result.output)


def test_render_player_without_soundfont_errors(tmp_path: Path) -> None:
    result = runner.invoke(
        cli_module.app,
        ["render", "--styles", "dre_g_funk", "--player", "--out", str(tmp_path)],
    )
    assert result.exit_code == 2
    assert "--player requires --soundfont" in (result.stderr or result.output)


def test_render_invalid_soundfont_errors(tmp_path: Path) -> None:
    result = runner.invoke(
        cli_module.app,
        ["render", "--styles", "dre_g_funk", "--soundfont", "bogus", "--out", str(tmp_path)],
    )
    assert result.exit_code == 2
    assert "invalid --soundfont" in (result.stderr or result.output)
