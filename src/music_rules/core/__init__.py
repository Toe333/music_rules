"""Pure-Python core: corpus, checkers, evaluator, MIDI helpers.

By convention nothing under this subpackage may import an AI-framework
SDK (``mcp``, ``openai``, ``anthropic``, ``langchain``, ``litellm``, ...).
The single permitted exception is ``music_rules.core.midi.skytnt_bridge``,
which may import ``transformers`` and ``huggingface_hub`` because it is
the SkyTNT integration point. Adapters belong in ``music_rules.adapters``.
"""
