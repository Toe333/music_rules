"""Corpus loader + JSON Schema sanity tests.

These tests are intentionally conservative and structural — they protect
the rule corpus from drift, not from semantic mistakes (those are caught
by the per-checker tests in Phase 3+).

What we verify here:

1. The shipped ``rules_combined.json`` loads without error and round-trips
   through the Pydantic ``Rule`` model.
2. Every rule object validates against ``rules.schema.json``.
3. Rule IDs are unique.
4. Every rule's ``input_shape`` (when set) is one of the declared shapes
   in the corpus' ``input_shapes`` dict.
5. Every checkable rule (kind in {hard, soft, hybrid}) has an
   ``input_shape``; every informational rule does NOT.
6. The convenience filters in ``corpus`` match the documented semantics.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import jsonschema
import pytest

from music_rules import Rule, corpus


# ---------------------------------------------------------------------------
# Structural / schema tests
# ---------------------------------------------------------------------------


def test_corpus_loads_and_has_158_rules() -> None:
    rules = corpus.get_rules()
    assert len(rules) == 158, (
        f"Expected 158 rules in the corpus (119 EIS + 39 Fux); got {len(rules)}. "
        "If you added or removed rules intentionally, update this test."
    )


def test_corpus_split_matches_spec() -> None:
    by_system = Counter(r.system for r in corpus.get_rules())
    assert by_system == {"EIS": 119, "Fux": 39}


def test_every_rule_validates_against_pydantic_model() -> None:
    # corpus.get_rules() already returns Rule instances, so a successful
    # call here is equivalent to "every JSON entry passed Pydantic validation".
    for rule in corpus.get_rules():
        assert isinstance(rule, Rule)


def test_every_rule_validates_against_jsonschema(
    raw_corpus: dict[str, Any], corpus_schema: dict[str, Any]
) -> None:
    # Validate the whole document at once — gives us the best error messages
    # if a rule is malformed.
    jsonschema.validate(instance=raw_corpus, schema=corpus_schema)


def test_rule_ids_are_unique() -> None:
    ids = [r.id for r in corpus.get_rules()]
    dupes = [rid for rid, count in Counter(ids).items() if count > 1]
    assert not dupes, f"Duplicate rule IDs found: {dupes}"


# ---------------------------------------------------------------------------
# Cross-field invariants
# ---------------------------------------------------------------------------


def test_input_shape_values_are_in_declared_vocabulary() -> None:
    declared = set(corpus.list_input_shapes())
    for rule in corpus.get_rules():
        if rule.input_shape is not None:
            assert rule.input_shape in declared, (
                f"Rule {rule.id} has input_shape {rule.input_shape!r} "
                f"which is not in the declared vocabulary."
            )


def test_checkable_rules_have_input_shape() -> None:
    for rule in corpus.get_rules():
        if rule.kind in {"hard", "soft", "hybrid"}:
            assert rule.input_shape is not None, (
                f"Rule {rule.id} is {rule.kind} but has no input_shape — "
                "no checker would ever fire on it."
            )


def test_informational_rules_have_no_input_shape() -> None:
    for rule in corpus.get_rules():
        if rule.kind == "informational":
            assert rule.input_shape is None, (
                f"Rule {rule.id} is informational but has input_shape "
                f"{rule.input_shape!r} — the corpus disagrees with itself."
            )


# ---------------------------------------------------------------------------
# Public-API / filter behavior
# ---------------------------------------------------------------------------


def test_list_systems() -> None:
    assert corpus.list_systems() == ["EIS", "Fux"]


def test_list_categories_partitions_correctly() -> None:
    all_cats = set(corpus.list_categories())
    eis_cats = set(corpus.list_categories(system="EIS"))
    fux_cats = set(corpus.list_categories(system="Fux"))
    assert eis_cats <= all_cats
    assert fux_cats <= all_cats
    assert all_cats == eis_cats | fux_cats


def test_get_rule_returns_correct_rule() -> None:
    rule = corpus.get_rule("H1_1")
    assert rule.id == "H1_1"
    assert rule.system == "Fux"
    assert rule.kind == "hard"


def test_get_rule_unknown_id_raises_keyerror_with_helpful_message() -> None:
    with pytest.raises(KeyError, match="Unknown rule id"):
        corpus.get_rule("NOPE-9999")


def test_filter_by_system() -> None:
    fux = corpus.get_rules(system="Fux")
    assert len(fux) == 39
    assert all(r.system == "Fux" for r in fux)


def test_filter_by_kind_returns_only_hard_for_hard() -> None:
    hard = corpus.get_rules(kind="hard")
    assert len(hard) > 0
    assert all(r.kind == "hard" for r in hard)


def test_filter_by_input_shape_returns_only_matching() -> None:
    motion = corpus.get_rules(input_shape="motion-pair")
    assert len(motion) > 0
    assert all(r.input_shape == "motion-pair" for r in motion)


def test_filter_by_voices_int_matches_v_string() -> None:
    # voices=2 should match rules with voices "2v" or "any" or "2v,..." etc.
    twovoice = corpus.get_rules(voices=2)
    assert len(twovoice) > 0
    for r in twovoice:
        assert r.voices in {"2v", "any"} or "2v" in r.voices.split(",")


def test_filter_by_species_int_matches_string() -> None:
    species1 = corpus.get_rules(species=1)
    for r in species1:
        assert r.species == "1"


def test_filter_combines_with_AND() -> None:
    # System=Fux AND kind=soft AND input_shape=melodic-interval should only
    # return G7 (the soft "prefer small intervals / tritone last-resort" rule).
    hits = corpus.get_rules(
        system="Fux", kind="soft", input_shape="melodic-interval"
    )
    assert len(hits) >= 1
    assert any(r.id == "G7" for r in hits)


def test_filter_by_ids() -> None:
    hits = corpus.get_rules(ids=["G6", "H1_1", "H1_1"])  # duplicate is fine
    assert {r.id for r in hits} == {"G6", "H1_1"}


def test_limit_caps_result_count() -> None:
    assert len(corpus.get_rules(limit=5)) == 5


# ---------------------------------------------------------------------------
# Input-shape vocabulary self-documentation
# ---------------------------------------------------------------------------


def test_input_shape_signatures_documented() -> None:
    for shape in corpus.list_input_shapes():
        sig = corpus.get_input_shape_signature(shape)
        assert sig.startswith("signature:"), (
            f"Input shape {shape!r} signature should start with 'signature:'; "
            f"got {sig!r}"
        )


def test_get_input_shape_signature_unknown_raises() -> None:
    with pytest.raises(KeyError, match="Unknown input_shape"):
        corpus.get_input_shape_signature("does-not-exist")


# ---------------------------------------------------------------------------
# Rule.is_checkable convenience
# ---------------------------------------------------------------------------


def test_is_checkable_aligns_with_kind_and_input_shape() -> None:
    for r in corpus.get_rules():
        expected = r.input_shape is not None and r.kind in {"hard", "soft", "hybrid"}
        assert r.is_checkable is expected, f"Rule {r.id}: is_checkable disagrees"


# ---------------------------------------------------------------------------
# Reload behavior
# ---------------------------------------------------------------------------


def test_reload_returns_fresh_corpus() -> None:
    c1 = corpus.reload()
    c2 = corpus.reload()
    # Same content, but the cache was rebuilt — both should be valid Corpus
    # instances with the expected rule count.
    assert len(c1.rules) == 158
    assert len(c2.rules) == 158
