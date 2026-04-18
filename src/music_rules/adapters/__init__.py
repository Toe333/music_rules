"""Thin adapters connecting the pure-Python core to AI frontends.

Each adapter is intentionally small (~50–100 lines) and re-uses
``music_rules.core`` directly. Adding a new AI vendor should never
require changes under ``music_rules.core``.
"""
