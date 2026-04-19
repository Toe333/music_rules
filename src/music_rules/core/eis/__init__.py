"""EIS subpackage — Equal Interval System helpers.

Currently implemented (Phase 7):

* :mod:`music_rules.core.eis.roots`  — E1..E6 cycles, ``pick_root_line``.
* :mod:`music_rules.core.eis.scales` — registry of EIS scales with the
  scales explicitly documented in the master rules doc filled in.

Scaffolded for Phase 8:

* :mod:`music_rules.core.eis.chords`         — vertical chord builders.
* :mod:`music_rules.core.eis.voice_leading`  — V-001..V-015 enforcement.
* :mod:`music_rules.core.eis.nct`            — PT/CA/RT/CT/Sus/Ant insertion.

The Phase-8 modules exist as importable scaffolds so any caller (MCP /
OpenAI / CLI) can already see "this surface is coming" rather than
discovering missing modules later.
"""

from music_rules.core.eis import chords, nct, roots, scales, voice_leading

__all__ = ["chords", "nct", "roots", "scales", "voice_leading"]
