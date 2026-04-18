"""music-rules — AI-agnostic music theory constraint system.

Quickstart::

    from music_rules import corpus

    print(corpus.list_systems())             # ['EIS', 'Fux']
    print(len(corpus.get_rules()))           # 158
    rule = corpus.get_rule("H1_1")
    print(rule.rule, rule.input_shape)

The runtime is organized in two layers:

* ``music_rules.core`` — pure-Python rule corpus, checkers, and the
  ``evaluate_passage`` orchestrator. Imports nothing from any AI-framework
  SDK (the single exception is ``core.midi.skytnt_bridge``, which is
  allowed to import ``transformers`` / ``huggingface_hub``).

* ``music_rules.adapters`` — thin shims (~50–100 lines each) exposing the
  core to MCP, OpenAI function-calling, FastAPI, and a typer CLI.

See ``PROJECT.md`` for the full design rationale.
"""

from __future__ import annotations

from music_rules.core import corpus
from music_rules.core.corpus import Rule

try:
    from music_rules._version import __version__  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - editable install before hatch-vcs runs
    __version__ = "0.1.0"

__all__ = [
    "Rule",
    "__version__",
    "corpus",
]
