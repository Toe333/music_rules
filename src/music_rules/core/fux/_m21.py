"""music21-backed musical primitives for the Fux checkers.

The Fux checker modules used to compute interval / motion / consonance /
triad facts by hand (the pure-stdlib ``core.pitch``). That musical
*detection* now delegates to **music21** — :class:`music21.interval.Interval`,
:class:`music21.chord.Chord`, and :class:`music21.voiceLeading.VoiceLeadingQuartet`.

What stays in the checker modules is Fux *policy*, not generic theory:
which corpus rule fires, the minor-sixth melodic-leap ceiling, the
"P4 is a dissonance in 2-voice writing" convention, and the soft-cost
weights. This file only answers primitive questions, and answers them
via music21 so there is one source of truth for music theory.

Note: music21's :meth:`Interval.isConsonant` already treats the perfect
fourth as dissonant, which happens to match strict 2-voice Fux. The
3+-voice "P4 becomes consonant" exception is applied here on top.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from music21 import chord as m21chord
from music21 import interval as m21interval
from music21 import note as m21note
from music21 import pitch as m21pitch
from music21 import voiceLeading

# Fux policy constants (NOT music21's call to make).
MAX_MELODIC_LEAP_SEMITONES: int = 8  # m6 ceiling (M1_1_* in FuxCP5)
OCTAVE: int = 12

# Human-readable interval names for *messages only* (judgments go through
# music21). Kept as a tiny table because music21's ``simpleName`` collapses
# the octave to "P1", which would mislabel P8 in user-facing strings.
_NAME: dict[int, str] = {
    0: "P1", 1: "m2", 2: "M2", 3: "m3", 4: "M3", 5: "P4",
    6: "TT", 7: "P5", 8: "m6", 9: "M6", 10: "m7", 11: "M7", 12: "P8",
}


@lru_cache(maxsize=256)
def _note(midi: int) -> m21note.Note:
    return m21note.Note(midi=midi)


@lru_cache(maxsize=1024)
def _iv(a: int, b: int) -> m21interval.Interval:
    return m21interval.Interval(noteStart=_note(a), noteEnd=_note(b))


# ---------------------------------------------------------------------------
# Single-interval primitives
# ---------------------------------------------------------------------------


def semitones(a: int, b: int) -> int:
    """Absolute semitone distance (music21-derived)."""
    return abs(_iv(a, b).semitones)


def signed_semitones(prev: int, curr: int) -> int:
    """Signed semitone delta; positive = ascending."""
    return _iv(prev, curr).semitones


def _reduce(s: int) -> int:
    s = abs(s)
    if s == 0:
        return 0
    r = s % OCTAVE
    return OCTAVE if r == 0 else r


def interval_name(semitones_val: int) -> str:
    """Human-readable simple-interval name for a semitone count."""
    return _NAME[_reduce(semitones_val)]


def name_pitch(midi: int) -> str:
    """Pitch name with octave (e.g. ``'F#4'``), via music21."""
    return m21pitch.Pitch(midi=midi).nameWithOctave


def is_tritone(semitones_val: int) -> bool:
    return _reduce(semitones_val) == 6


def is_p4(semitones_val: int) -> bool:
    return _reduce(semitones_val) == 5


def is_stepwise(prev: int, curr: int) -> bool:
    """True iff the melodic interval is a half- or whole-step."""
    return semitones(prev, curr) in (1, 2)


# ---------------------------------------------------------------------------
# Consonance (music21's judgment + the Fux voice-count P4 exception)
# ---------------------------------------------------------------------------


def is_consonant(a: int, b: int, *, voice_count: int = 2) -> bool:
    """True iff the harmonic interval is consonant *in this voice context*.

    music21 already calls P4 dissonant (strict 2-voice Fux). The only
    contextual twist is that the P4 becomes a consonance once a third
    voice supports it (3+-voice writing).
    """
    if voice_count >= 3 and is_p4(semitones(a, b)):
        return True
    return _iv(a, b).isConsonant()


def is_dissonant(a: int, b: int, *, voice_count: int = 2) -> bool:
    return not is_consonant(a, b, voice_count=voice_count)


def is_perfect_consonance(a: int, b: int) -> bool:
    """P1 / P5 / P8 (and their compounds) — the 'approach-by-direct-
    motion is forbidden' set, and the required opening/closing sonority."""
    return _reduce(_iv(a, b).semitones) in (0, 7, OCTAVE)


# ---------------------------------------------------------------------------
# Two-voice motion (music21 VoiceLeadingQuartet)
# ---------------------------------------------------------------------------


def motion_type(cf_prev: int, cf_curr: int, cp_prev: int, cp_curr: int) -> str:
    """``'parallel'`` | ``'similar'`` | ``'contrary'`` | ``'oblique'``."""
    q = voiceLeading.VoiceLeadingQuartet(
        _note(cf_prev), _note(cf_curr), _note(cp_prev), _note(cp_curr)
    )
    return q.motionType().name


def direct_into_perfect(
    cf_prev: int, cf_curr: int, cp_prev: int, cp_curr: int
) -> bool:
    """True iff the pair moves by direct (parallel *or* similar) motion
    into a perfect consonance — the P1_* prohibition, as detected by
    music21's parallel/hidden fifth/octave/unison predicates."""
    q = voiceLeading.VoiceLeadingQuartet(
        _note(cf_prev), _note(cf_curr), _note(cp_prev), _note(cp_curr)
    )
    return bool(
        q.parallelUnison()
        or q.parallelFifth()
        or q.parallelOctave()
        or q.hiddenFifth()
        or q.hiddenOctave()
    )


# ---------------------------------------------------------------------------
# Vertical sonority (music21 Chord)
# ---------------------------------------------------------------------------


def is_complete_triad(midis: Iterable[int]) -> bool:
    """True iff the simultaneous notes form a tertian triad (root/3rd/5th)."""
    notes = sorted(set(midis))
    if len(notes) < 3:
        return False
    return m21chord.Chord(notes).isTriad()
