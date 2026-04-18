"""MIDI I/O and SkyTNT bridge.

This is the **only** subpackage under ``music_rules.core`` that may import
heavyweight third-party libraries beyond ``mido`` and ``pydantic``.
Specifically, ``skytnt_bridge`` may import ``transformers`` and
``huggingface_hub`` (via the optional ``[skytnt]`` extra) — see
``pyproject.toml``.
"""
