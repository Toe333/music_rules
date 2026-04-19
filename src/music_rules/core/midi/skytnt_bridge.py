"""MIDI round-trip + SkyTNT generation bridge.

Implemented today (Phase 7)
---------------------------

* :func:`midi_to_rolls`  — decode a MIDI file (path or base64 blob)
  into per-track piano-roll lists, plus inferred meta (meter, key
  guess, tempo).
* :func:`rolls_to_midi`  — encode per-voice piano-roll lists into a
  base64-encoded MIDI file string.

Scaffolded for Phase 8
----------------------

* :func:`skytnt_generate` — call HuggingFace's
  `SkyTNT/midi-model <https://huggingface.co/skytnt/midi-model>`_
  via the ``transformers`` library to generate raw MIDI.
* :func:`skytnt_constrained_generate` — loop generation through
  :func:`music_rules.core.evaluate.evaluate_passage` and return the
  best candidate that satisfies the caller's hard / soft caps.

Both raise :class:`NotImplementedError` today with a clear pointer
to the integration plan in their docstrings; their *signatures* are
locked so MCP / OpenAI clients see the final API today.

Why a single bridge module
--------------------------

Per ``PROJECT.md`` non-negotiable #1, ``transformers`` / ``torch`` /
``huggingface_hub`` may be imported **only** under this file. That
keeps the ~3 GB SkyTNT download path out of every other code path:
``mido`` is a pure-Python ~50 KB dep, while ``transformers`` only loads
when the user actually asks for SkyTNT generation.
"""

from __future__ import annotations

import base64
import io
from collections.abc import Iterable
from typing import Any, TypedDict

import mido

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class RollsBundle(TypedDict):
    """Output of :func:`midi_to_rolls`.

    * ``voices``: one MIDI-number list per track (rests = ``-1``).
    * ``meter``:  e.g. ``"4/4"``.
    * ``tempo``:  microseconds per quarter note (mido's native unit).
    * ``key_guess``: best-guess key string (e.g. ``"C"``); ``None`` if
      the file didn't supply a key signature meta-event.
    * ``ticks_per_beat``: original PPQN, kept for round-tripping.
    """

    voices: list[list[int]]
    meter: str
    tempo: int
    key_guess: str | None
    ticks_per_beat: int


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------


def midi_to_rolls(
    midi_input: str | bytes,
    *,
    beats_per_quarter: int = 1,
) -> RollsBundle:
    """Decode a MIDI file into per-voice MIDI-number lists.

    Args:
        midi_input:        either a filesystem path or a base64-encoded
                           blob (auto-detected — base64 strings are
                           decoded if the path doesn't exist on disk).
        beats_per_quarter: downsample resolution. ``1`` (default) =
                           one event per quarter note. Higher values
                           subdivide further.

    Returns:
        :class:`RollsBundle` with one voice per non-empty MIDI track.
        Rests are represented as ``-1`` so the list lengths line up
        across voices.

    Notes:
        SkyTNT's ``midi-model`` produces single-track MIDI by default;
        for multi-voice corpora we walk every track that contains
        ``note_on`` events. Voices are reported in their on-disk track
        order so the round-trip with :func:`rolls_to_midi` is stable.
    """
    midi = _load_midi(midi_input)
    ticks_per_beat = midi.ticks_per_beat
    grid_step_ticks = max(1, ticks_per_beat // beats_per_quarter)

    voices: list[list[int]] = []
    meter = "4/4"
    tempo = 500_000  # 120 BPM default
    key_guess: str | None = None

    for track in midi.tracks:
        # First pass: extract meta events.
        for msg in track:
            if msg.type == "set_tempo":
                tempo = msg.tempo
            elif msg.type == "time_signature":
                meter = f"{msg.numerator}/{msg.denominator}"
            elif msg.type == "key_signature":
                key_guess = msg.key

        roll = _track_to_roll(track, grid_step_ticks=grid_step_ticks)
        if roll:
            voices.append(roll)

    # Pad shorter voices with rests so all lists are the same length.
    if voices:
        n = max(len(v) for v in voices)
        for v in voices:
            v.extend([-1] * (n - len(v)))

    return {
        "voices": voices,
        "meter": meter,
        "tempo": tempo,
        "key_guess": key_guess,
        "ticks_per_beat": ticks_per_beat,
    }


def _load_midi(midi_input: str | bytes) -> mido.MidiFile:
    """Auto-detect path-vs-base64 and load via :class:`mido.MidiFile`."""
    if isinstance(midi_input, bytes):
        return mido.MidiFile(file=io.BytesIO(midi_input))

    # Try path first; fall back to base64 if not a real file.
    try:
        return mido.MidiFile(midi_input)
    except (FileNotFoundError, OSError):
        try:
            blob = base64.b64decode(midi_input, validate=True)
        except Exception as exc:
            raise ValueError(
                "midi_input is neither an existing file path nor a "
                "valid base64-encoded MIDI blob."
            ) from exc
        return mido.MidiFile(file=io.BytesIO(blob))


def _track_to_roll(
    track: Iterable[mido.Message], *, grid_step_ticks: int,
) -> list[int]:
    """Reduce a MIDI track to a per-grid-step list of MIDI numbers.

    Sustained notes hold their pitch across grid steps; rests / gaps
    appear as ``-1``. We keep this a deliberately simple algorithm:
    SkyTNT outputs are mostly monophonic per track, so we don't try
    to handle full polyphony here — that's the caller's job (split
    into multiple tracks before calling).
    """
    roll: list[int] = []
    elapsed = 0
    last_step = 0
    current_pitch = -1
    for msg in track:
        elapsed += msg.time
        # Project to grid steps.
        while last_step + grid_step_ticks <= elapsed:
            roll.append(current_pitch)
            last_step += grid_step_ticks

        if msg.type == "note_on" and msg.velocity > 0:
            current_pitch = msg.note
        elif msg.type in ("note_off",) or (
            msg.type == "note_on" and msg.velocity == 0
        ):
            current_pitch = -1

    return roll


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


def rolls_to_midi(
    voices: list[list[int]],
    *,
    meter: str = "4/4",
    tempo: int = 500_000,
    ticks_per_beat: int = 480,
    velocity: int = 80,
    program: int = 0,
) -> str:
    """Encode per-voice MIDI-number lists into a base64-encoded MIDI string.

    Args:
        voices:         one MIDI-number list per track. ``-1`` = rest.
        meter:          time signature, e.g. ``"4/4"``.
        tempo:          microseconds per quarter note (default 120 BPM).
        ticks_per_beat: PPQN (default 480, GM-friendly).
        velocity:       note-on velocity (1..127).
        program:        General MIDI program for every track (0..127).

    Returns:
        A base64-encoded MIDI file ready to paste into the SkyTNT
        prompt or hand to a player. Round-trip with :func:`midi_to_rolls`
        is exact at the grid step.
    """
    if not voices or not voices[0]:
        raise ValueError("rolls_to_midi requires at least one non-empty voice")

    midi = mido.MidiFile(ticks_per_beat=ticks_per_beat)

    # Track 0 holds meta events.
    meta = mido.MidiTrack()
    midi.tracks.append(meta)
    meta.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    num, den = (int(p) for p in meter.split("/"))
    meta.append(mido.MetaMessage(
        "time_signature", numerator=num, denominator=den, time=0,
    ))

    for voice in voices:
        track = mido.MidiTrack()
        midi.tracks.append(track)
        track.append(mido.Message("program_change", program=program, time=0))

        prev_pitch = -1
        rest_ticks = 0
        for pitch in voice:
            if pitch == prev_pitch:
                rest_ticks += ticks_per_beat
                continue
            if prev_pitch != -1:
                track.append(mido.Message(
                    "note_off", note=prev_pitch, velocity=0, time=rest_ticks,
                ))
                rest_ticks = 0
            if pitch != -1:
                track.append(mido.Message(
                    "note_on", note=pitch, velocity=velocity, time=rest_ticks,
                ))
                rest_ticks = ticks_per_beat
            else:
                rest_ticks += ticks_per_beat
            prev_pitch = pitch

        if prev_pitch != -1:
            track.append(mido.Message(
                "note_off", note=prev_pitch, velocity=0, time=rest_ticks,
            ))

    buf = io.BytesIO()
    midi.save(file=buf)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ---------------------------------------------------------------------------
# Generation (Phase 8)
# ---------------------------------------------------------------------------


def skytnt_generate(
    prompt_midi: str | None = None,
    *,
    conditioning: dict[str, Any] | None = None,
    num_candidates: int = 4,
    temperature: float = 1.0,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate raw MIDI candidates with SkyTNT's ``midi-model``. **Not implemented.**

    Phase-8 implementation plan
    ---------------------------

    1. Lazy-import ``transformers`` and ``huggingface_hub``.
    2. Lazy-load ``skytnt/midi-model`` on first call (cache in module
       state so repeat calls are warm).
    3. Decode ``prompt_midi`` (base64) into the model's token format
       (the repo ships a tokenizer alongside the model).
    4. Sample ``num_candidates`` continuations at the requested
       temperature/seed.
    5. Detokenize each back to MIDI and return base64-encoded blobs.

    Returns:
        ``{"candidates": [{"midi_base64": "...", "token_count": int}, ...]}``
    """
    raise NotImplementedError(
        "SkyTNT generation (Group E / phase 8). "
        "Pip-install with `pip install music-rules[skytnt]` and see "
        "src/music_rules/core/midi/skytnt_bridge.py for the implementation plan."
    )


def skytnt_constrained_generate(
    prompt_midi: str | None = None,
    *,
    conditioning: dict[str, Any] | None = None,
    ruleset: str = "both",
    strict: bool = False,
    max_hard_violations: int = 0,
    max_total_cost: float = 10.0,
    num_candidates_per_try: int = 8,
    max_tries: int = 8,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate-and-filter loop against the music-rules corpus. **Not implemented.**

    Phase-8 implementation plan
    ---------------------------

    1. Loop up to ``max_tries`` times.
    2. Each iteration: call :func:`skytnt_generate` for
       ``num_candidates_per_try`` candidates.
    3. Convert each candidate to rolls via :func:`midi_to_rolls`.
    4. Pipe through
       :func:`music_rules.core.evaluate.evaluate_passage` with the
       requested ``ruleset`` and ``strict``.
    5. Keep candidates with
       ``len(hard_violations) <= max_hard_violations`` AND
       ``total_cost <= max_total_cost``.
    6. Return the lowest-cost survivor (along with stats), or the
       lowest-cost candidate ever seen if none satisfied the caps.

    Returns:
        ``{"best": {"midi_base64": str, "report": <PassageReport>},
           "tried": int, "accepted": int}``
    """
    raise NotImplementedError(
        "SkyTNT constrained generation (Group E / phase 8). "
        "Once skytnt_generate is implemented, this loop is ~30 lines."
    )
