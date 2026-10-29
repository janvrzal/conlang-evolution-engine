"""Závislosti uložených hodnocení morfologických změn."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cee.v2.language.journal import FrequencyMap

if TYPE_CHECKING:
    from cee.v2.morphology import FormAssessment
    from cee.v2.world import World


class FormAssessmentIndex:
    """Uchovává jen data a ruší hodnoty podle přírůstkových deníků."""

    def __init__(self) -> None:
        self.version = -1
        self.lexicon_version = -1
        self.dominant: dict[str, str] = {}
        self.token: int | None = None
        self.cursor = self.usage_cursor = self.dominant_cursor = 0
        self.frequency_cursor = 0
        self.frequency_object: object = None
        self.frequency_signature: object = None
        self.values: dict[str, FormAssessment | None] = {}
        self.unit_vars: dict[str, set[str]] = {}
        self.root_vars: dict[str, set[str]] = {}
        self.exponent_vars: dict[str, set[str]] = {}
        self.cell_vars: dict[tuple[str, str], set[str]] = {}
        self.cells: dict[tuple[str, str], tuple[tuple[str, int], ...]] = {}
        self.endings: dict[str, tuple[int, ...] | None] = {}

    def _sync(self, world: World, group_id: str) -> None:
        from cee.v2.morphology import class_stats

        code = world.groups[group_id].main_code
        state, store = code.phonology, code.forms
        if self.version == state.version:
            return
        frequencies = world.concept_frequencies
        reset = (self.token != store.token or self.cursor > len(store.log)
                 or self.usage_cursor > len(state.usage_log)
                 or self.dominant_cursor > len(state.dominant_log))
        dirty: set[str] = set()
        if reset:
            dirty.update(self.values)
        else:
            for unit in store.log[self.cursor:]:
                dirty.update(self.unit_vars.get(unit, ()))
                dirty.update(self.root_vars.get(unit, ()))
            for root, _, _ in state.usage_log[self.usage_cursor:]:
                dirty.update(self.root_vars.get(root, ()))
            for _, old, new in state.dominant_log[self.dominant_cursor:]:
                for changed_root in (old, new):
                    if changed_root is not None:
                        dirty.update(self.root_vars.get(changed_root, ()))
        if self.lexicon_version != state.lexicon_version:
            for concept in self.dominant.keys() | state.dominant.keys():
                old, new = self.dominant.get(concept), state.dominant.get(concept)
                if old != new:
                    for changed_root in (old, new):
                        if changed_root is not None:
                            dirty.update(self.root_vars.get(changed_root, ()))
            self.dominant = state.dominant.copy()
            self.lexicon_version = state.lexicon_version
        if isinstance(frequencies, FrequencyMap):
            if frequencies is not self.frequency_object or self.frequency_cursor > len(frequencies.log):
                dirty.update(self.values)
            else:
                for concept in frequencies.log[self.frequency_cursor:]:
                    current_root = state.dominant.get(concept)
                    if current_root is not None:
                        dirty.update(self.root_vars.get(current_root, ()))
            self.frequency_cursor = len(frequencies.log)
            self.frequency_object = frequencies
        else:
            signature = tuple(sorted(frequencies.items()))
            if self.frequency_signature != signature:
                dirty.update(self.values)
            self.frequency_signature = signature
            self.frequency_object = None
            self.frequency_cursor = 0
        if self.cell_vars or self.exponent_vars:
            stats = class_stats(world, code)
            for cell, variables in self.cell_vars.items():
                counts = tuple(sorted(stats.exponents.get(cell, {}).items()))
                if self.cells.get(cell) != counts:
                    dirty.update(variables)
                self.cells[cell] = counts
            for exponent, variables in self.exponent_vars.items():
                ending = stats.endings.get(exponent)
                if exponent not in self.endings or self.endings[exponent] != ending:
                    dirty.update(variables)
                self.endings[exponent] = ending
        for variable in dirty:
            self.values.pop(variable, None)
        self.token, self.cursor = store.token, len(store.log)
        self.usage_cursor, self.dominant_cursor = len(state.usage_log), len(state.dominant_log)
        self.version = state.version

    def assess(self, world: World, group_id: str, variable: str) -> FormAssessment | None:
        from cee.v2.morphology import _assess_reference, class_stats

        self._sync(world, group_id)
        if variable not in self.values:
            change = world.form_changes[variable]
            item = world.morphemes[change.unit]
            self.unit_vars.setdefault(change.unit, set()).add(variable)
            self.root_vars.setdefault(item.lexeme_id, set()).add(variable)
            if change.exponent is not None:
                self.exponent_vars.setdefault(change.exponent, set()).add(variable)
            if change.operation == "extend" and item.word_class is not None and item.cell is not None:
                self.cell_vars.setdefault((item.word_class, item.cell), set()).add(variable)
            self.values[variable] = _assess_reference(world, group_id, variable)
            if change.exponent is not None or change.operation == "extend":
                stats = class_stats(world, world.groups[group_id].main_code)
                if change.exponent is not None:
                    self.endings[change.exponent] = stats.endings.get(change.exponent)
                if change.operation == "extend" and item.word_class is not None and item.cell is not None:
                    cell = (item.word_class, item.cell)
                    self.cells[cell] = tuple(sorted(stats.exponents.get(cell, {}).items()))
        return self.values[variable]
