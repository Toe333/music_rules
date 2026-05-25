"""Pydantic schema + loader for ``data/styles/*.json`` style profiles.

A style profile is a self-contained recipe: meter, tempo, key, chord
vamp, per-instrument rules and rhythm cells. The generator modules
under :mod:`music_rules.core.generate` consume validated profiles
without re-parsing JSON.
"""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class KeySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tonic: str
    mode: Literal["natural_minor", "dorian", "major", "minor_pentatonic", "blues"]


class ChordVampEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chord: str
    bars: int = Field(gt=0)


class HarmonySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chord_vamp: list[ChordVampEntry]
    voicing: dict[str, list[int]]
    chord_roots: dict[str, str]

    @field_validator("chord_vamp")
    @classmethod
    def _vamp_not_empty(cls, value: list[ChordVampEntry]) -> list[ChordVampEntry]:
        if not value:
            raise ValueError("chord_vamp must contain at least one entry")
        return value


class DrumsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern_resolution: Literal["8th", "16th"]
    pattern_spec: str
    pattern: dict[str, list[int]]
    midi_notes: dict[str, int]
    velocity: dict[str, int]
    humanize_velocity: int = 0


class BassRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    downbeat_must_be_chord_root: bool = True
    approach_downbeat_with_chromatic_step: bool = True
    chromatic_approach_direction: Literal["below", "above", "below_or_above"] = "below_or_above"
    syncopation_probability: float = Field(ge=0.0, le=1.0, default=0.0)
    rest_probability: float = Field(ge=0.0, le=1.0, default=0.0)
    max_leap_semitones: int = Field(gt=0, default=12)


class BassSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    program: int = Field(ge=0, le=127)
    octave: int
    scale_pool: list[str]
    rules: BassRules
    rhythm_cells_beats: list[list[float]]
    velocity: int = Field(ge=1, le=127, default=95)


class LeadRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active_on_bars_in_phrase: list[int]
    phrase_length_beats: list[int]
    max_leap_semitones: int = Field(gt=0, default=7)
    emphasize_blue_note: str | None = None
    rest_probability_per_bar: float = Field(ge=0.0, le=1.0, default=0.0)


class LeadSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    program: int = Field(ge=0, le=127)
    octave: int
    scale_pool: list[str]
    rules: LeadRules
    rhythm_cells_beats: list[list[float]]
    velocity: int = Field(ge=1, le=127, default=88)


class ChordPadSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    program: int = Field(ge=0, le=127)
    velocity: int = Field(ge=1, le=127, default=55)
    octave_offset: int = 0


class FormSectionB(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lead_active_on_all_bars: bool = False
    drum_velocity_boost: int = 0


class FormSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    structure: list[str]
    bars_per_section: int = Field(gt=0)
    B_section: FormSectionB = Field(default_factory=FormSectionB)


class StyleProfile(BaseModel):
    """Validated style profile consumed by the generator pipeline."""

    model_config = ConfigDict(extra="forbid")
    name: str
    description: str = ""
    tempo_bpm: int = Field(gt=0)
    swing: float = Field(ge=0.5, le=0.75, default=0.5)
    meter: str
    key: KeySpec
    harmony: HarmonySpec
    drums: DrumsSpec
    bass: BassSpec
    lead: LeadSpec
    chord_pad: ChordPadSpec
    form: FormSpec


def load_style(name_or_path: str | Path) -> StyleProfile:
    """Load and validate a style profile.

    Accepts either a bare profile name (resolved against the packaged
    ``music_rules.data.styles`` resource directory) or an explicit
    filesystem path.
    """
    path = Path(name_or_path)
    if path.suffix == ".json" and path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        resource_name = (
            f"{name_or_path}.json" if not str(name_or_path).endswith(".json") else str(name_or_path)
        )
        text = files("music_rules.data.styles").joinpath(resource_name).read_text(encoding="utf-8")
    return StyleProfile.model_validate(json.loads(text))
