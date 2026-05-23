"""Deterministic, rules-driven music generators.

Reads a :class:`StyleProfile` (a JSON file under ``data/styles/`` or a
caller-supplied object), renders multi-track MIDI with a seeded RNG.

Public surface
--------------
* :func:`load_style` — load a profile by name or path.
* :func:`generate_track` — orchestrate drums + bass + lead + chord pad
  into base64-encoded MIDI bytes and a structured event summary.
"""

from __future__ import annotations

from music_rules.core.generate.generator import GenerationResult, generate_track
from music_rules.core.generate.style import StyleProfile, load_style

__all__ = ["GenerationResult", "StyleProfile", "generate_track", "load_style"]
