"""Form expansion: ``StyleProfile.form`` → flat bar-by-bar chord schedule."""

from __future__ import annotations

from dataclasses import dataclass

from music_rules.core.generate.style import StyleProfile


@dataclass(frozen=True)
class BarSlot:
    """One bar of the rendered piece."""

    bar_index: int
    section_label: str
    chord_symbol: str
    is_first_bar_of_chord: bool
    is_last_bar_of_chord: bool


def expand_form(style: StyleProfile) -> list[BarSlot]:
    """Flatten the form + chord vamp into one :class:`BarSlot` per bar."""
    vamp = style.harmony.chord_vamp
    section_bars = style.form.bars_per_section

    # Pre-roll the vamp out to a per-bar sequence so we can index by
    # (bar-within-section), wrapping if the vamp is shorter than the section.
    vamp_per_bar: list[tuple[str, bool, bool]] = []
    for entry in vamp:
        for offset in range(entry.bars):
            vamp_per_bar.append((entry.chord, offset == 0, offset == entry.bars - 1))
    if not vamp_per_bar:
        raise ValueError("chord vamp expanded to zero bars")

    slots: list[BarSlot] = []
    bar = 0
    for label in style.form.structure:
        for i in range(section_bars):
            chord, first, last = vamp_per_bar[i % len(vamp_per_bar)]
            slots.append(
                BarSlot(
                    bar_index=bar,
                    section_label=label,
                    chord_symbol=chord,
                    is_first_bar_of_chord=first,
                    is_last_bar_of_chord=last,
                )
            )
            bar += 1
    return slots
