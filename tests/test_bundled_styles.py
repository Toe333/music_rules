"""Smoke-test every bundled style JSON profile.

Every file under ``music_rules.data.styles`` must:

1. Load and validate cleanly via :class:`StyleProfile`.
2. Render to non-empty MIDI bytes with a 4-track summary at a fixed seed.
"""

from __future__ import annotations

from importlib.resources import files

import pytest

from music_rules.core.generate import generate_track, load_style
from music_rules.core.generate.style import StyleProfile


def _bundled_style_ids() -> list[str]:
    root = files("music_rules.data.styles")
    return sorted(p.name[:-5] for p in root.iterdir() if p.name.endswith(".json"))


BUNDLED_STYLE_IDS = _bundled_style_ids()


def test_bundled_styles_present() -> None:
    assert len(BUNDLED_STYLE_IDS) >= 21


@pytest.mark.parametrize("style_id", BUNDLED_STYLE_IDS)
def test_bundled_style_loads_and_generates(style_id: str) -> None:
    style = load_style(style_id)
    assert isinstance(style, StyleProfile)
    result = generate_track(style, seed=1990)
    assert result.midi_bytes
    assert len(result.tracks) == 4
    assert result.summary["bars"] > 0
