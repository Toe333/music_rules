"""Shared helpers for Fux checkers.

The single most common operation across checkers is "find the rules that
apply to the current fragment given its input_shape, species, and voice
count." That logic lives here so each individual checker module stays
focused on the *musical* judgment, not the dispatch plumbing.
"""

from __future__ import annotations

from music_rules.core import corpus
from music_rules.core.corpus import Rule


def applicable_rules(
    input_shape: str,
    species: int | str | None,
    voices: int | str,
) -> list[Rule]:
    """Subset of corpus rules whose input_shape matches and whose
    species/voices predicates allow the current context.

    Matching semantics
    ------------------

    * ``species`` query of ``None`` or ``"all"`` matches every rule of
      that shape (used by the evaluator for global passes).
    * A rule with ``species == "all"`` or ``species is None`` matches
      any specific species query.
    * Otherwise an exact string match on ``species`` is required (e.g.
      query ``"1"`` matches rule ``species == "1"`` but not ``"2"``).
    * Voices: a rule with ``voices == "any"`` (or ``None``) matches any
      query. A rule with ``voices == "3v,4v"`` matches queries ``"3v"``
      or ``"4v"``. The integer ``2`` is normalized to ``"2v"``.
    """
    all_rules = corpus.get_rules(input_shape=input_shape)
    species_q = _normalize_species_query(species)
    voices_q = _normalize_voice_query(voices)

    return [r for r in all_rules if _species_matches(r.species, species_q)
            and _voices_matches(r.voices, voices_q)]


def _normalize_species_query(species: int | str | None) -> str | None:
    if species is None:
        return None
    return str(species).strip()


def _normalize_voice_query(voices: int | str | None) -> str | None:
    if voices is None:
        return None
    if isinstance(voices, int):
        return f"{voices}v"
    return voices.strip()


def _species_matches(rule_species: str | None, query: str | None) -> bool:
    if query is None or query == "all":
        return True
    if rule_species is None or rule_species == "all":
        return True
    return rule_species == query


def _voices_matches(rule_voices: str | None, query: str | None) -> bool:
    if query is None or query == "any":
        return True
    if rule_voices is None or rule_voices == "any":
        return True
    if rule_voices == query:
        return True
    if "," in rule_voices:
        return query in {part.strip() for part in rule_voices.split(",")}
    return False
