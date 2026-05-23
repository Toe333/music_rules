"""Render the bundled "Dre 1990s Gangsta" style to a deterministic MIDI file.

Usage::

    uv run python examples/dre_1990s_gangsta.py [--seed N] [--out PATH]

Same ``--seed`` + same style profile → byte-identical ``.mid``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from music_rules.core.generate import generate_track, load_style

DEFAULT_OUT = Path(__file__).resolve().parent / "dre_1990s_gangsta.mid"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1990)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    style = load_style("dre_1990s_gangsta")
    result = generate_track(style, seed=args.seed)
    args.out.write_bytes(result.midi_bytes)

    print(f"wrote {args.out} ({len(result.midi_bytes)} bytes)")
    for key, value in result.summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
