"""MIDI subpackage — round-trip helpers and the SkyTNT bridge.

* :mod:`music_rules.core.midi.skytnt_bridge` — MIDI ↔ piano-roll
  conversion (implemented today using :mod:`mido`) plus scaffolds for
  ``skytnt_generate`` and ``skytnt_constrained_generate`` that will
  call HuggingFace's ``midi-model`` once Phase 8 wires it in.

This is the **only** place under ``core/`` allowed to import
``transformers`` / ``huggingface_hub`` / ``torch`` (see
``PROJECT.md`` non-negotiable constraints).
"""
