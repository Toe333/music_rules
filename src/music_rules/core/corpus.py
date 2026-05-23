"""Rule corpus loader — single entry point to ``rules_combined.json``.

The corpus is the **single source of truth** for every checker, generator,
and adapter. Every public function here treats the on-disk JSON as
authoritative and never hardcodes rule IDs.

Public API
==========

* :class:`Rule`                 — Pydantic model, one per JSON entry.
* :class:`Corpus`               — eager-loaded snapshot with cached indexes.
* :func:`get_rules`             — filtered list of :class:`Rule` objects.
* :func:`get_rule`              — single :class:`Rule` by ID, or raise.
* :func:`list_systems`          — ``["EIS", "Fux"]``.
* :func:`list_categories`       — categories present in the corpus.
* :func:`list_input_shapes`     — declared input-shape vocabulary.
* :func:`get_input_shape_signature` — docstring for a given input shape.
* :func:`reload`                — re-read the JSON (test / hot-reload helper).

Design notes
------------

* The JSON is loaded **once** at import time via :mod:`importlib.resources`,
  so a wheel install works without filesystem assumptions.
* :class:`Corpus` builds an ID index and a per-(system, category, kind,
  input_shape, species, voices) dispatch index. Filtering is O(1) lookups
  + a single intersection.
* Filter values are matched flexibly: ``species=1`` matches the string
  ``"1"``, ``voices=2`` matches ``"2v"``, etc. Pass ``"any"`` or ``"all"``
  explicitly to match those literal corpus values.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from functools import lru_cache
from importlib.resources import files
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Vocabulary (mirrored from rules_combined.json — kept here for type checkers)
# ---------------------------------------------------------------------------

System = Literal["EIS", "Fux"]
Kind = Literal["hard", "soft", "hybrid", "informational"]

# Species and voices are represented as strings in the corpus to handle
# values like "all", "any", and combined forms like "3v,4v". We keep them
# as strings here and provide convenience matching in get_rules().
Species = str  # "1" | "2" | "3" | "4" | "5" | "all" | None
Voices = str  # "2v" | "3v" | "4v" | "3v,4v" | "any" | None

_RULES_JSON_RESOURCE: Final = "rules_combined.json"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Rule(BaseModel):
    """A single rule from ``rules_combined.json``.

    Every field maps 1:1 to a JSON key. Optional fields are exactly those
    that appear as ``null`` in the corpus (``input_shape``, ``species``,
    ``voices``) — typically because the rule is a principle / definition
    rather than a mechanically checkable constraint.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., description="Stable rule identifier, e.g. 'H1_1', 'V-014', 'P-001'.")
    system: System = Field(..., description="Which rule corpus this belongs to.")
    category: str = Field(..., description="Free-form category bucket (e.g. 'voice-leading').")
    rule: str = Field(..., description="Human-readable rule statement.")
    scope: str = Field(..., description="Where the rule applies (e.g. 'all writing').")
    exceptions: str = Field(default="", description="Documented exceptions; empty if none.")
    tier: str = Field(..., description="Difficulty / character tier.")
    source: str = Field(..., description="Provenance citation (e.g. 'TG p.34', 'FuxCP5 H1_1').")
    kind: Kind = Field(..., description="hard | soft | hybrid | informational.")
    input_shape: str | None = Field(
        default=None,
        description="Canonical fragment shape this rule's checker consumes. "
        "Null for principles / definitions / informational rules.",
    )
    species: Species | None = Field(
        default=None,
        description="Counterpoint species ('1'..'5' | 'all') the rule applies to.",
    )
    voices: Voices | None = Field(
        default=None,
        description="Voice-count specifier ('2v' | '3v' | '4v' | '3v,4v' | 'any').",
    )

    @field_validator("id")
    @classmethod
    def _id_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Rule.id must be a non-empty string")
        return v

    @property
    def is_checkable(self) -> bool:
        """True iff this rule has a mechanical input shape (so a checker can run on it)."""
        return self.input_shape is not None and self.kind in {"hard", "soft", "hybrid"}


# ---------------------------------------------------------------------------
# Corpus container
# ---------------------------------------------------------------------------


class Corpus(BaseModel):
    """Eagerly-loaded snapshot of ``rules_combined.json``.

    Most callers shouldn't construct this directly — use the module-level
    functions (:func:`get_rules`, :func:`get_rule`, ...) which operate on
    a cached singleton. Tests can construct alternative :class:`Corpus`
    instances by passing a different ``rules`` list.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    description: str
    systems: dict[str, str]
    kinds: dict[str, str]
    input_shapes: dict[str, str]
    rules: tuple[Rule, ...]

    # ----- factory ----------------------------------------------------------

    @classmethod
    def from_json_text(cls, text: str) -> Corpus:
        """Parse the corpus from a JSON string."""
        raw = json.loads(text)
        return cls(
            description=raw.get("description", ""),
            systems=raw.get("systems", {}),
            kinds=raw.get("kinds", {}),
            input_shapes=raw.get("input_shapes", {}),
            rules=tuple(Rule.model_validate(r) for r in raw["rules"]),
        )

    @classmethod
    def load_default(cls) -> Corpus:
        """Load the corpus shipped inside the package (``music_rules.data``)."""
        text = files("music_rules.data").joinpath(_RULES_JSON_RESOURCE).read_text(encoding="utf-8")
        return cls.from_json_text(text)

    # ----- queries ----------------------------------------------------------

    def by_id(self, rule_id: str) -> Rule:
        try:
            return self._id_index[rule_id]
        except KeyError as exc:
            raise KeyError(
                f"Unknown rule id: {rule_id!r}. "
                f"Try one of: {', '.join(sorted(self._id_index)[:5])}, ..."
            ) from exc

    def filter(
        self,
        *,
        system: System | None = None,
        category: str | None = None,
        species: int | str | None = None,
        voices: int | str | None = None,
        kind: Kind | None = None,
        tier: str | None = None,
        input_shape: str | None = None,
        ids: Iterable[str] | None = None,
    ) -> list[Rule]:
        """Return rules matching ALL of the supplied filters.

        Convenience matching:

        * ``species=1``    matches the literal string ``"1"``.
        * ``voices=2``     matches the literal string ``"2v"``.
        * ``species="all"`` matches only rules whose ``species`` field is ``"all"``.
          (Pass ``None`` — the default — to skip the filter entirely.)
        * ``ids=[...]``    restricts to a specific set of rule IDs.
        """
        species_str = _normalize_species(species)
        voices_str = _normalize_voices(voices)
        ids_set = set(ids) if ids is not None else None

        out: list[Rule] = []
        for r in self.rules:
            if system is not None and r.system != system:
                continue
            if category is not None and r.category != category:
                continue
            if kind is not None and r.kind != kind:
                continue
            if tier is not None and r.tier != tier:
                continue
            if input_shape is not None and r.input_shape != input_shape:
                continue
            if species_str is not None and r.species != species_str:
                continue
            if voices_str is not None and not _voices_match(r.voices, voices_str):
                continue
            if ids_set is not None and r.id not in ids_set:
                continue
            out.append(r)
        return out

    # ----- introspection ----------------------------------------------------

    def systems_present(self) -> list[str]:
        return sorted({r.system for r in self.rules})

    def categories(self, *, system: System | None = None) -> list[str]:
        return sorted({r.category for r in self.rules if system is None or r.system == system})

    def kinds_present(self) -> list[str]:
        return sorted({r.kind for r in self.rules})

    # ----- private indexes --------------------------------------------------

    @property
    def _id_index(self) -> dict[str, Rule]:
        # Lazy attribute on a frozen pydantic model — stash on the instance dict.
        cached = self.__dict__.get("__id_index_cache")
        if cached is None:
            cached = {r.id: r for r in self.rules}
            object.__setattr__(self, "__id_index_cache", cached)
        return cached


# ---------------------------------------------------------------------------
# Module-level singleton + convenience API (the part most callers will use)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _default_corpus() -> Corpus:
    return Corpus.load_default()


def reload() -> Corpus:
    """Discard the cached corpus and reload from disk. Mostly for tests."""
    _default_corpus.cache_clear()
    return _default_corpus()


def get_rules(
    *,
    system: System | None = None,
    category: str | None = None,
    species: int | str | None = None,
    voices: int | str | None = None,
    kind: Kind | None = None,
    tier: str | None = None,
    input_shape: str | None = None,
    ids: Iterable[str] | None = None,
    limit: int | None = None,
) -> list[Rule]:
    """Return rules matching ALL filters (AND-combined). At most ``limit`` results."""
    out = _default_corpus().filter(
        system=system,
        category=category,
        species=species,
        voices=voices,
        kind=kind,
        tier=tier,
        input_shape=input_shape,
        ids=ids,
    )
    if limit is not None:
        out = out[:limit]
    return out


def get_rule(rule_id: str) -> Rule:
    """Return a single :class:`Rule` by ID. Raises :class:`KeyError` if missing."""
    return _default_corpus().by_id(rule_id)


def list_systems() -> list[str]:
    """List rule systems present in the corpus, e.g. ``['EIS', 'Fux']``."""
    return _default_corpus().systems_present()


def list_categories(system: System | None = None) -> list[str]:
    """List categories, optionally filtered to one system."""
    return _default_corpus().categories(system=system)


def list_kinds() -> list[str]:
    """List rule kinds present in the corpus."""
    return _default_corpus().kinds_present()


def list_input_shapes() -> list[str]:
    """List the canonical input-shape vocabulary declared at the top of the JSON."""
    return sorted(_default_corpus().input_shapes.keys())


def get_input_shape_signature(input_shape: str) -> str:
    """Return the documented Python signature for a given input shape."""
    shapes = _default_corpus().input_shapes
    try:
        return shapes[input_shape]
    except KeyError as exc:
        raise KeyError(
            f"Unknown input_shape: {input_shape!r}. Known shapes: {', '.join(sorted(shapes))}"
        ) from exc


# ---------------------------------------------------------------------------
# Filter normalization helpers
# ---------------------------------------------------------------------------


def _normalize_species(species: int | str | None) -> str | None:
    if species is None:
        return None
    s = str(species).strip()
    return s or None


def _normalize_voices(voices: int | str | None) -> str | None:
    if voices is None:
        return None
    if isinstance(voices, int):
        return f"{voices}v"
    s = voices.strip()
    return s or None


def _voices_match(rule_voices: str | None, query: str) -> bool:
    """Match a rule's voices spec against a query.

    A rule voices field of ``"3v,4v"`` matches queries ``"3v"`` or ``"4v"``.
    A rule voices field of ``"any"`` matches any specific query.
    """
    if rule_voices is None:
        return False
    if rule_voices == query:
        return True
    if rule_voices == "any":
        return True
    if "," in rule_voices:
        return query in {part.strip() for part in rule_voices.split(",")}
    return False
