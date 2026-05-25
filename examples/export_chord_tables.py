#!/usr/bin/env python3
"""Export a chord dictionary file into JSON/CSV tables for MCP/SkyTNT.

The source file must define:
    - note_to_midi: dict[str, int]
    - chord_to_notes: dict[str, list[str]]

This script writes:
    - note_to_midi.json
    - chord_lexicon.json
    - chord_notes_long.csv
    - chord_voicings_wide.csv
    - progression_template.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import runpy
from pathlib import Path
from typing import Any


def _normalize_symbol(text: str) -> str:
    return text.replace("♯", "#").replace("-", "b").replace("+", "#")


_BASE_PITCH_CLASS: dict[str, int] = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}

_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]*)(-?\d+)$")


def _parse_note_name_to_midi(note_name: str) -> int | None:
    """Resolve spellings like Cb4 / Fb4 / E#5 into MIDI when absent in lookup."""
    match = _NOTE_RE.match(note_name)
    if not match:
        return None
    letter, accidentals, octave_text = match.groups()
    octave = int(octave_text)
    base_pc = _BASE_PITCH_CLASS[letter.upper()]
    accidental_delta = accidentals.count("#") - accidentals.count("b")
    midi = (octave + 1) * 12 + base_pc + accidental_delta
    if 0 <= midi <= 127:
        return midi
    return None


def _load_source(path: Path) -> tuple[dict[str, int], dict[str, list[str]]]:
    namespace = runpy.run_path(str(path))
    if "note_to_midi" not in namespace or "chord_to_notes" not in namespace:
        raise ValueError("Source file must define both `note_to_midi` and `chord_to_notes`.")
    note_to_midi = namespace["note_to_midi"]
    chord_to_notes = namespace["chord_to_notes"]
    if not isinstance(note_to_midi, dict) or not isinstance(chord_to_notes, dict):
        raise ValueError("`note_to_midi` and `chord_to_notes` must both be dicts.")

    clean_note_to_midi: dict[str, int] = {}
    for key, value in note_to_midi.items():
        if not isinstance(key, str) or not isinstance(value, int):
            continue
        clean_note_to_midi[_normalize_symbol(key)] = value

    clean_chord_to_notes: dict[str, list[str]] = {}
    for chord_symbol, notes in chord_to_notes.items():
        if not isinstance(chord_symbol, str) or not isinstance(notes, list):
            continue
        normalized_notes = [n for n in (_normalize_symbol(str(x)) for x in notes)]
        clean_chord_to_notes[_normalize_symbol(chord_symbol)] = normalized_notes

    return clean_note_to_midi, clean_chord_to_notes


def _build_lexicon(
    note_to_midi: dict[str, int],
    chord_to_notes: dict[str, list[str]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    lexicon: dict[str, Any] = {"chords": {}}
    long_rows: list[dict[str, Any]] = []
    unresolved_notes: list[str] = []

    for chord_symbol in sorted(chord_to_notes):
        notes = chord_to_notes[chord_symbol]
        midi_notes: list[int] = []
        for idx, note_name in enumerate(notes):
            midi_number = note_to_midi.get(note_name)
            if midi_number is None:
                midi_number = _parse_note_name_to_midi(note_name)
            if midi_number is None:
                unresolved_notes.append(f"{chord_symbol}:{note_name}")
                continue
            midi_notes.append(midi_number)
            long_rows.append(
                {
                    "chord_symbol": chord_symbol,
                    "voice_index": idx,
                    "note_name": note_name,
                    "midi": midi_number,
                }
            )
        lexicon["chords"][chord_symbol] = {
            "notes": notes,
            "midi": midi_notes,
            "note_count": len(notes),
            "resolved_midi_count": len(midi_notes),
        }
    return lexicon, long_rows, sorted(set(unresolved_notes))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_outputs(
    out_dir: Path,
    note_to_midi: dict[str, int],
    lexicon: dict[str, Any],
    long_rows: list[dict[str, Any]],
    unresolved_tokens: list[str],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_json(out_dir / "note_to_midi.json", note_to_midi)
    _write_json(out_dir / "chord_lexicon.json", lexicon)

    _write_csv(
        out_dir / "chord_notes_long.csv",
        long_rows,
        ["chord_symbol", "voice_index", "note_name", "midi"],
    )

    wide_rows: list[dict[str, Any]] = []
    for chord_symbol, payload in lexicon["chords"].items():
        notes = payload["notes"]
        midi = payload["midi"]
        wide_rows.append(
            {
                "chord_symbol": chord_symbol,
                "note_count": payload["note_count"],
                "resolved_midi_count": payload["resolved_midi_count"],
                "notes_pipe": "|".join(notes),
                "midi_pipe": "|".join(str(n) for n in midi),
            }
        )

    _write_csv(
        out_dir / "chord_voicings_wide.csv",
        sorted(wide_rows, key=lambda row: row["chord_symbol"]),
        [
            "chord_symbol",
            "note_count",
            "resolved_midi_count",
            "notes_pipe",
            "midi_pipe",
        ],
    )

    template_rows = [
        {"bar": 1, "start_beat": 0.0, "duration_beats": 4.0, "chord_symbol": "Cmaj7"},
        {"bar": 2, "start_beat": 4.0, "duration_beats": 4.0, "chord_symbol": "Am7"},
        {"bar": 3, "start_beat": 8.0, "duration_beats": 4.0, "chord_symbol": "Dm7"},
        {"bar": 4, "start_beat": 12.0, "duration_beats": 4.0, "chord_symbol": "G7"},
    ]
    _write_csv(
        out_dir / "progression_template.csv",
        template_rows,
        ["bar", "start_beat", "duration_beats", "chord_symbol"],
    )

    unresolved_rows = []
    for token in unresolved_tokens:
        chord_symbol, note_name = token.split(":", maxsplit=1)
        unresolved_rows.append({"chord_symbol": chord_symbol, "note_name": note_name})
    _write_csv(
        out_dir / "unresolved_notes.csv",
        unresolved_rows,
        ["chord_symbol", "note_name"],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export chord dictionaries to machine-usable tables."
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to source Python file that defines note_to_midi and chord_to_notes.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/chord_tables"),
        help="Directory where exported files are written.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    note_to_midi, chord_to_notes = _load_source(args.source)
    lexicon, long_rows, unresolved = _build_lexicon(note_to_midi, chord_to_notes)
    _write_outputs(args.out_dir, note_to_midi, lexicon, long_rows, unresolved)

    print(f"Exported chord tables to: {args.out_dir}")
    print(f"Chords exported: {len(lexicon['chords'])}")
    print(f"Chord-note rows: {len(long_rows)}")
    if unresolved:
        print(f"Unresolved note tokens ({len(unresolved)}):")
        for token in unresolved[:20]:
            print(f"  - {token}")
        if len(unresolved) > 20:
            print("  - ...")
    else:
        print("All note tokens resolved to MIDI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
