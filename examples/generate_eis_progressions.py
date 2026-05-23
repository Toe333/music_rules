#!/usr/bin/env python3
"""Generate harmonized EIS progression examples.

Creates one MIDI per EIS progression type (E1..E6 + TT alias) where:
- Harmony changes once per bar (whole notes in 4/4).
- Melody is all quarter notes.
- Chord-to-chord movement uses the EIS voice-leading engine.
"""

from __future__ import annotations

import base64
import csv
import json
from pathlib import Path
from typing import Any

from music_rules.core.eis.chords import build_chord, pitch_classes
from music_rules.core.eis.nct import insert_nct
from music_rules.core.eis.roots import CYCLE_LENGTHS, cycle_root_names
from music_rules.core.eis.voice_leading import check_progression, voice_lead
from music_rules.core.midi.skytnt_bridge import rolls_to_midi

OUTPUT_DIR = Path("examples")
CHORD_CLASS = "triad-7"
PARTS = 4
BASE_OCTAVE = 3
BEATS_PER_BAR = 4


def _note_name(midi: int) -> str:
    names = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
    octave = (midi // 12) - 1
    return f"{names[midi % 12]}{octave}"


def _bar_melody(curr_chord: list[int], next_chord: list[int] | None, root: str) -> list[int]:
    """Build a 4-quarter-note melody cell for one bar."""
    soprano = curr_chord[-1]
    beat1 = soprano

    if next_chord is None:
        return [beat1, beat1, beat1, beat1]

    try:
        # Passing tone between current and next soprano (EIS NCT PT).
        event = insert_nct(
            curr_chord,
            next_chord,
            voice=len(curr_chord) - 1,
            nct_type="PT",
            scale_id="EIS-18-01",
            scale_root=root,
        )
        beat2 = int(event["midi"])
    except ValueError:
        # Fallback when geometry isn't suitable for PT.
        beat2 = beat1 + 1 if next_chord[-1] >= beat1 else beat1 - 1

    beat3 = next_chord[-1]
    beat4 = next_chord[-1]
    return [beat1, beat2, beat3, beat4]


def generate_progression(kind_label: str, cycle_id: str) -> dict[str, Any]:
    roots = cycle_root_names(cycle_id, start="C")
    bars = len(roots)
    steps = bars * BEATS_PER_BAR

    first = build_chord(
        roots[0],
        CHORD_CLASS,
        parts=PARTS,
        voicing="close",
        base_octave=BASE_OCTAVE,
    )
    chords: list[list[int]] = [first]
    reports: list[dict[str, Any]] = []

    for root in roots[1:]:
        pcs = pitch_classes(root, CHORD_CLASS)
        nxt = voice_lead(chords[-1], pcs, style="normal", keep_bass_in_bass=True)
        reports.append(check_progression(chords[-1], nxt))
        chords.append(nxt)

    harmony_voices = [[-1] * steps for _ in range(PARTS)]
    melody_voice = [-1] * steps

    bar_rows: list[dict[str, Any]] = []
    for bar_idx, (root, chord) in enumerate(zip(roots, chords, strict=True), start=1):
        start = (bar_idx - 1) * BEATS_PER_BAR
        end = start + BEATS_PER_BAR
        for vidx in range(PARTS):
            for t in range(start, end):
                harmony_voices[vidx][t] = chord[vidx]

        next_chord = chords[bar_idx] if bar_idx < bars else None
        mel = _bar_melody(chord, next_chord, root)
        for ofs, midi in enumerate(mel):
            melody_voice[start + ofs] = midi

        bar_rows.append(
            {
                "kind": kind_label,
                "cycle": cycle_id,
                "bar": bar_idx,
                "root": root,
                "chord_midis": "|".join(str(n) for n in chord),
                "chord_notes": "|".join(_note_name(n) for n in chord),
                "melody_qn_midis": "|".join(str(n) for n in mel),
                "melody_qn_notes": "|".join(_note_name(n) for n in mel),
            }
        )

    voices = [*harmony_voices, melody_voice]
    midi_b64 = rolls_to_midi(
        voices,
        meter="4/4",
        tempo=500_000,
        programs=[0, 0, 0, 0, 65],  # piano stack + lead
    )
    midi_bytes = base64.b64decode(midi_b64)

    midi_path = OUTPUT_DIR / f"eis_{kind_label.lower()}_harmonized.mid"
    midi_path.write_bytes(midi_bytes)

    csv_path = OUTPUT_DIR / f"eis_{kind_label.lower()}_harmonized.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "kind",
                "cycle",
                "bar",
                "root",
                "chord_midis",
                "chord_notes",
                "melody_qn_midis",
                "melody_qn_notes",
            ],
        )
        writer.writeheader()
        writer.writerows(bar_rows)

    hard_vl_violations = sum(len(r["violations"]) for r in reports)
    return {
        "kind": kind_label,
        "cycle": cycle_id,
        "bars": bars,
        "cycle_length": CYCLE_LENGTHS[cycle_id],
        "roots": roots,
        "midi": str(midi_path),
        "csv": str(csv_path),
        "voice_leading_pairs": len(reports),
        "voice_leading_violations": hard_vl_violations,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    progression_types = [
        ("E1", "E1"),
        ("E2", "E2"),
        ("E3", "E3"),
        ("E4", "E4"),
        ("E5", "E5"),
        ("E6", "E6"),
        ("TT", "E6"),  # tritone alias
    ]

    manifest = {
        "description": (
            "EIS progression examples with whole-note harmony and quarter-note melody."
        ),
        "chord_class": CHORD_CLASS,
        "parts": PARTS,
        "meter": "4/4",
        "tempo_bpm": 120,
        "items": [generate_progression(label, cycle) for label, cycle in progression_types],
    }

    manifest_path = OUTPUT_DIR / "eis_all_progressions_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {manifest_path}")
    for item in manifest["items"]:
        print(
            f"{item['kind']}: {item['midi']} | {item['csv']} | "
            f"bars={item['bars']} VL_violations={item['voice_leading_violations']}"
        )


if __name__ == "__main__":
    main()
