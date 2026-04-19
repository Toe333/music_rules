"""Test fixtures for Fux 2-voice 1st-species checkers.

Notation: each passage is a dict with two MIDI sequences indexed by voice
name. ``cf`` = cantus firmus, ``cp`` = counterpoint. Both have equal
length; the n-th element of each is the simultaneous note at beat n.

These are *synthesized* fixtures we can verify by inspection — every
interval and motion type is documented in the comment above each one.
We deliberately don't transcribe Fux *Gradus* examples from memory;
when we add real Gradus passages later they'll be checked against the
1943 Mann edition page-by-page.
"""

from __future__ import annotations

from typing import Final, TypedDict


class FuxPassage(TypedDict):
    name: str
    source: str
    species: int
    voices: int
    cf: list[int]
    cp: list[int]


# ---------------------------------------------------------------------------
# CLEAN_2V_1S_C_MAJOR — a 7-note 2v 1st-species passage that satisfies
# every Phase-3 hard rule we currently check.
#
# CF (lower): C4 D4 E4 F4 E4 D4 C4   — stepwise, m6 max (no leaps at all).
# CP (upper): G4 F4 G4 A4 G4 F4 G4   — stepwise, m6 max.
#
# Vertical intervals (CP - CF, in semitones):
#   beat 0: 67-60 = 7  (P5)   — opening P5 ✓ H2_1
#   beat 1: 65-62 = 3  (m3)
#   beat 2: 67-64 = 3  (m3)
#   beat 3: 69-65 = 4  (M3)
#   beat 4: 67-64 = 3  (m3)
#   beat 5: 65-62 = 3  (m3)
#   beat 6: 67-60 = 7  (P5)   — closing P5 ✓ H3_1
#
# Motion pairs (between successive verticalities):
#   0->1: CF +2, CP -2 → contrary into m3       (no P1 violation)
#   1->2: CF +2, CP +2 → parallel into m3       (parallel imperfect = OK)
#   2->3: CF +1, CP +2 → similar into M3        (similar into imperfect = OK)
#   3->4: CF -1, CP -2 → similar into m3        (OK)
#   4->5: CF -2, CP -2 → parallel into m3       (OK)
#   5->6: CF -2, CP +2 → contrary into P5       (contrary into perfect = OK)
# Every downbeat sonority is a 3rd or 5th — H1_1 ✓.
CLEAN_2V_1S_C_MAJOR: Final[FuxPassage] = {
    "name": "Synthesized clean 2v 1st-species in C major",
    "source": "music-rules tests/fixtures/fux_passages.py",
    "species": 1,
    "voices": 2,
    "cf": [60, 62, 64, 65, 64, 62, 60],
    "cp": [67, 65, 67, 69, 67, 65, 67],
}


# Failing fixture: same CF but CP has parallel 5ths C-G to D-A.
PARALLEL_FIFTHS_FAIL: Final[FuxPassage] = {
    "name": "Constructed failing fixture: parallel 5ths in 2v 1st species",
    "source": "music-rules tests/fixtures/fux_passages.py (textbook violation example)",
    "species": 1,
    "voices": 2,
    "cf": [60, 62, 64, 60, 62, 60],   # C D E C D C
    "cp": [67, 69, 71, 67, 69, 67],   # G A B G A G — every interval is P5
}


# Failing fixture: opens on a non-perfect interval (M3) — H2_1 violation.
WRONG_OPENING_INTERVAL_FAIL: Final[FuxPassage] = {
    "name": "Constructed failing fixture: opens on M3 (H2_1 violation)",
    "source": "music-rules tests/fixtures/fux_passages.py",
    "species": 1,
    "voices": 2,
    "cf": [60, 62, 64, 65, 64, 62, 60],
    "cp": [64, 65, 67, 69, 67, 65, 64],  # opens M3 above CF — wrong
}


# Failing fixture: closes on a M6 — H3_1 violation.
WRONG_CLOSING_INTERVAL_FAIL: Final[FuxPassage] = {
    "name": "Constructed failing fixture: closes on M6 (H3_1 violation)",
    "source": "music-rules tests/fixtures/fux_passages.py",
    "species": 1,
    "voices": 2,
    "cf": [60, 62, 64, 65, 64, 62, 60],
    "cp": [67, 69, 71, 72, 71, 69, 69],  # closes 60+9=M6 — wrong
}
