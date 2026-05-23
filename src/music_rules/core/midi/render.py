"""Chord-progression rendering: lexicon + events → voice rolls / base64 MIDI.

Lives in ``core/`` so every adapter (MCP, OpenAI fn-call, CLI) renders
chord progressions the same way. The MCP tool functions in
``adapters/mcp.py`` are thin wrappers around the helpers here.
"""

from __future__ import annotations

import contextlib
import csv
import json
from pathlib import Path
from typing import Any

from music_rules.core.midi import skytnt_bridge


def load_chord_lexicon(
    chord_lexicon: dict[str, Any] | None,
    chord_lexicon_path: str | None,
) -> dict[str, list[int]]:
    """Normalize several lexicon JSON shapes into ``symbol -> [midi...]``."""
    payload: dict[str, Any]
    if chord_lexicon is not None:
        payload = chord_lexicon
    elif chord_lexicon_path is not None:
        payload = json.loads(Path(chord_lexicon_path).read_text(encoding="utf-8"))
    else:
        raise ValueError(
            "Provide either chord_lexicon (object) or chord_lexicon_path (JSON file path)."
        )

    out: dict[str, list[int]] = {}
    # Exporter shape: {"chords": {"Cmaj7": {"midi": [60,64,67,71], ...}, ...}}
    if "chords" in payload and isinstance(payload["chords"], dict):
        for symbol, entry in payload["chords"].items():
            if not isinstance(symbol, str):
                continue
            if isinstance(entry, dict) and isinstance(entry.get("midi"), list):
                out[symbol] = [int(n) for n in entry["midi"]]
        return out

    # Also accept a flat mapping: {"Cmaj7": [60,64,67,71], ...}
    for symbol, entry in payload.items():
        if not isinstance(symbol, str):
            continue
        if isinstance(entry, list):
            out[symbol] = [int(n) for n in entry]
    return out


def read_progression_csv(path: str) -> list[dict[str, Any]]:
    """Read progression events from CSV (chord_symbol, duration_beats, start_beat?)."""
    out: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if not row:
                continue
            event: dict[str, Any] = {}
            if row.get("bar"):
                with contextlib.suppress(TypeError, ValueError):
                    event["bar"] = int(row["bar"])
            if row.get("start_beat") not in (None, ""):
                event["start_beat"] = float(row["start_beat"])
            if row.get("duration_beats") not in (None, ""):
                event["duration_beats"] = float(row["duration_beats"])
            event["chord_symbol"] = str(row.get("chord_symbol", "")).strip()
            out.append(event)
    return out


def progression_to_rolls(
    progression: list[dict[str, Any]],
    symbol_to_midi: dict[str, list[int]],
    *,
    steps_per_beat: int = 1,
    rest_symbol: str = "REST",
) -> tuple[list[list[int]], int, list[str]]:
    """Render timed chord events onto a fixed-step roll grid.

    Returns ``(voices, total_steps, unresolved_symbols)`` where ``voices``
    is a per-voice MIDI-number list with rests as ``-1``.
    """
    if steps_per_beat < 1:
        raise ValueError("steps_per_beat must be >= 1")
    if not progression:
        raise ValueError("progression must include at least one event")

    cursor_beats = 0.0
    events: list[tuple[int, int, str]] = []  # (start_step, duration_steps, symbol)
    unresolved: list[str] = []
    max_voices = 1
    total_steps = 0

    for idx, row in enumerate(progression):
        symbol = str(row.get("chord_symbol", "")).strip()
        if not symbol:
            raise ValueError(f"progression[{idx}] missing chord_symbol")

        duration_beats = float(row.get("duration_beats", 1.0))
        if duration_beats <= 0:
            raise ValueError(f"progression[{idx}] has non-positive duration_beats")
        duration_steps = max(1, round(duration_beats * steps_per_beat))

        start_beat = float(row["start_beat"]) if "start_beat" in row else cursor_beats
        start_step = max(0, round(start_beat * steps_per_beat))

        cursor_beats = max(cursor_beats, start_beat + duration_beats)
        total_steps = max(total_steps, start_step + duration_steps)
        events.append((start_step, duration_steps, symbol))

        if symbol != rest_symbol:
            midi = symbol_to_midi.get(symbol)
            if midi is None:
                unresolved.append(symbol)
            elif midi:
                max_voices = max(max_voices, len(midi))

    voices = [[-1] * total_steps for _ in range(max_voices)]
    for start, dur, symbol in sorted(events, key=lambda e: e[0]):
        if symbol == rest_symbol:
            continue
        midi = symbol_to_midi.get(symbol)
        if not midi:
            continue
        end = min(total_steps, start + dur)
        for v_idx, pitch in enumerate(midi):
            for t in range(start, end):
                voices[v_idx][t] = pitch

    return voices, total_steps, sorted(set(unresolved))


def progression_to_midi(
    voices: list[list[int]],
    *,
    meter: str = "4/4",
    tempo: int = 500_000,
    ticks_per_beat: int = 480,
    velocity: int = 80,
    program: int = 0,
    programs: list[int] | None = None,
) -> str:
    """Encode pre-rendered voice rolls to base64 MIDI via :mod:`skytnt_bridge`."""
    return skytnt_bridge.rolls_to_midi(
        voices,
        meter=meter,
        tempo=tempo,
        ticks_per_beat=ticks_per_beat,
        velocity=velocity,
        program=program,
        programs=programs,
    )
