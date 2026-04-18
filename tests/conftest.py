"""Shared pytest fixtures."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

import pytest


@pytest.fixture(scope="session")
def raw_corpus() -> dict[str, Any]:
    """The raw rules_combined.json as a Python dict, loaded once per test session."""
    text = files("music_rules.data").joinpath("rules_combined.json").read_text(encoding="utf-8")
    return json.loads(text)


@pytest.fixture(scope="session")
def corpus_schema() -> dict[str, Any]:
    """The JSON Schema describing rules_combined.json."""
    text = files("music_rules.data").joinpath("rules.schema.json").read_text(encoding="utf-8")
    return json.loads(text)
