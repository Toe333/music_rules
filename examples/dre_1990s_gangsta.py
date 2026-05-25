"""Render the bundled "Dre 1990s Gangsta" style to a deterministic MIDI file.

Usage::

    uv run python examples/dre_1990s_gangsta.py [--seed N] [--out PATH] [--player]

Same ``--seed`` + same style profile → byte-identical ``.mid``. With
``--player``, the MIDI is bounced to MP3 (timidity → ffmpeg) and handed
to the local ``webplayer`` CLI for browser preview.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from music_rules.core.generate import generate_track, load_style

DEFAULT_OUT = Path(__file__).resolve().parent / "dre_1990s_gangsta.mid"


def _bounce_and_preview(mid_path: Path, *, label: str, group: str, desc: str) -> None:
    needed = ("timidity", "ffmpeg", "webplayer")
    missing = [b for b in needed if shutil.which(b) is None]
    if missing:
        print(f"--player skipped (missing on PATH: {', '.join(missing)})")
        return
    wav = mid_path.with_suffix(".wav")
    mp3 = mid_path.with_suffix(".mp3")
    subprocess.run(
        ["timidity", str(mid_path), "-Ow", "-o", str(wav)], check=True, capture_output=True
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "192k", str(mp3)],
        check=True,
        capture_output=True,
    )
    wav.unlink()
    subprocess.run(
        ["webplayer", "add", str(mp3), "--label", label, "--group", group, "--desc", desc],
        check=True,
    )
    subprocess.run(["webplayer", "open"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1990)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--player", action="store_true", help="bounce to MP3 and load into the webplayer"
    )
    args = parser.parse_args()

    style = load_style("dre_1990s_gangsta")
    result = generate_track(style, seed=args.seed)
    args.out.write_bytes(result.midi_bytes)

    print(f"wrote {args.out} ({len(result.midi_bytes)} bytes)")
    for key, value in result.summary.items():
        print(f"  {key}: {value}")

    if args.player:
        _bounce_and_preview(
            args.out,
            label=f"{style.name} seed={args.seed}",
            group="dre",
            desc=f"{style.tempo_bpm} BPM {style.key.tonic} {style.key.mode}",
        )


if __name__ == "__main__":
    main()
