"""Závislosti uložených hodnocení morfologických změn (krok B3b, čísla z registru).

Hodnocení analogické změny (``cee.v2.morphology.FormAssessment``) se drží, dokud se nezmění
něco, na čem závisí. Klíče jsou čísla z registru: hodnoty podle čísla proměnné, závislosti
(jednotka, kořen, koncovka) jako čísla morfémů, dominantní kořeny jako pole podle čísla pojmu.
Změny se hledají v deníku tvarů, užití, dominantních kořenů a frekvencí pojmů.

Rust (``cee_core.AssessIndex``) drží zrcadlo hodnot pro tlaky: ``mirror`` je dvojice
(rukojeť, token kódu). Každé zrušení hodnoty se do zrcadla hned zapíše, takže zrcadlo nikdy
nenese hodnotu, kterou by tento index už nevrátil; chybějící hodnotu si Rust vyžádá a Python
ji sem dodá (:func:`assess`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from cee.v2.language.journal import FrequencyMap

if TYPE_CHECKING:
    from cee.v2.morphology import FormAssessment
    from cee.v2.world import World


_MISSING: object = object()


def assess(world: World, group_id: str, variable_id: str) -> FormAssessment | None:
    """Uložené hodnocení analogické změny; rychlá cesta pro už platnou hodnotu.

    Totéž co ``cee.v2.morphology.assess``. Tlaky se na jedno hodnocení ptají
    pro každou dvojici (proměnná, skupina) znovu, takže v ustáleném stavu
    (index už dorovnaný na verzi kódu a hodnota uložená, i ``None``) stačí
    jedno nahlédnutí do slovníku; ostatní případy jdou původní cestou.
    """
    state = world.groups[group_id].main_code.phonology
    entry = state.cache.get("form-assessment-index")
    if entry is not None:
        index = entry[1]
        if index.version == state.version:
            number = world.registry.variables.numbers.get(variable_id)
            found = index.values.get(number, _MISSING)
            if found is not _MISSING:
                return found  # type: ignore[no-any-return]
    from cee.v2.morphology import assess as slow

    return slow(world, group_id, variable_id)


class FormAssessmentIndex:
    """Uchovává jen data a ruší hodnoty podle přírůstkových deníků."""

    def __init__(self) -> None:
        self.version = -1
        self.lexicon_version = -1
        #: Dominantní kořeny podle čísla pojmu při posledním dorovnání (−1 = žádný).
        self.dominant = np.zeros(0, dtype=np.int32)
        self.token: int | None = None
        self.cursor = self.usage_cursor = self.dominant_cursor = 0
        self.frequency_cursor = 0
        self.frequency_object: object = None
        self.frequency_signature: object = None
        #: Číslo proměnné → hodnocení (nebo ``None``, když změna nic nemění).
        self.values: dict[int, FormAssessment | None] = {}
        #: Závislosti: číslo morfému (jednotka, lexém, koncovka) → čísla proměnných.
        self.unit_vars: dict[int, set[int]] = {}
        self.root_vars: dict[int, set[int]] = {}
        self.exponent_vars: dict[int, set[int]] = {}
        self.cell_vars: dict[tuple[str, str], set[int]] = {}
        self.cells: dict[tuple[str, str], tuple[tuple[str, int], ...]] = {}
        self.endings: dict[int, tuple[int, ...] | None] = {}
        #: Zrcadlo hodnot v Rustu: (rukojeť, token kódu), nebo ``None``.
        self.mirror: tuple[Any, int] | None = None

    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()
        state["mirror"] = None
        return state

    @staticmethod
    def _roots(code: Any) -> Any:
        roots = code.phonology.dominant.roots
        return np.array(np.frombuffer(roots, dtype=np.int32)) if len(roots) else np.zeros(0, dtype=np.int32)

    def _drop(self, variables: set[int]) -> None:
        """Zruší hodnoty proměnných (i v zrcadle)."""
        for variable in variables:
            if self.values.pop(variable, _MISSING) is not _MISSING and self.mirror is not None:
                handle, token = self.mirror
                handle.form_invalidate(token, variable)

    def _sync(self, world: World, group_id: str) -> None:
        from cee.v2.morphology import class_stats

        code = world.groups[group_id].main_code
        state, store = code.phonology, code.forms
        if self.version == state.version:
            return
        morphemes = world.registry.morphemes.numbers
        frequencies = world.concept_frequencies
        reset = (self.token != store.token or self.cursor > len(store.log)
                 or self.usage_cursor > len(state.usage_log)
                 or self.dominant_cursor > len(state.dominant_log))
        dirty: set[int] = set()
        if reset:
            dirty.update(self.values)
        else:
            for unit in store.log[self.cursor:]:
                number = morphemes.get(unit, -1)
                dirty.update(self.unit_vars.get(number, ()))
                dirty.update(self.root_vars.get(number, ()))
            for root, _, _ in state.usage_log[self.usage_cursor:]:
                dirty.update(self.root_vars.get(morphemes.get(root, -1), ()))
            for _, old, new in state.dominant_log[self.dominant_cursor:]:
                for changed_root in (old, new):
                    if changed_root is not None:
                        dirty.update(self.root_vars.get(morphemes.get(changed_root, -1), ()))
        if self.lexicon_version != state.lexicon_version:
            now = self._roots(code)
            width = max(len(self.dominant), len(now))
            before = np.full(width, -1, dtype=np.int32)
            after = np.full(width, -1, dtype=np.int32)
            before[: len(self.dominant)] = self.dominant
            after[: len(now)] = now
            for concept in np.nonzero(before != after)[0].tolist():
                for changed_root in (int(before[concept]), int(after[concept])):
                    if changed_root >= 0:
                        dirty.update(self.root_vars.get(changed_root, ()))
            self.dominant = now
            self.lexicon_version = state.lexicon_version
        if isinstance(frequencies, FrequencyMap):
            if frequencies is not self.frequency_object or self.frequency_cursor > len(frequencies.log):
                dirty.update(self.values)
            else:
                concepts = world.registry.concepts.numbers
                roots = state.dominant.roots
                for concept in frequencies.log[self.frequency_cursor:]:
                    number = concepts.get(concept, -1)
                    current_root = roots[number] if 0 <= number < len(roots) else -1
                    if current_root >= 0:
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
            names = world.registry.morphemes.names
            for cell, variables in self.cell_vars.items():
                counts = tuple(sorted(stats.exponents.get(cell, {}).items()))
                if self.cells.get(cell) != counts:
                    dirty.update(variables)
                self.cells[cell] = counts
            for exponent, variables in self.exponent_vars.items():
                ending = stats.endings.get(names[exponent])
                if exponent not in self.endings or self.endings[exponent] != ending:
                    dirty.update(variables)
                self.endings[exponent] = ending
        self._drop(dirty)
        self.token, self.cursor = store.token, len(store.log)
        self.usage_cursor, self.dominant_cursor = len(state.usage_log), len(state.dominant_log)
        self.version = state.version
        if self.mirror is not None:
            handle, token = self.mirror
            handle.form_synced(token, state.version)

    def assess(self, world: World, group_id: str, variable: str) -> FormAssessment | None:
        from cee.v2.morphology import _assess_reference, class_stats

        self._sync(world, group_id)
        number = world.registry.variables.intern(variable)
        if number not in self.values:
            change = world.form_changes[variable]
            item = world.morphemes[change.unit]
            numbering = world.registry.morphemes
            self.unit_vars.setdefault(numbering.intern(change.unit), set()).add(number)
            self.root_vars.setdefault(numbering.intern(item.lexeme_id), set()).add(number)
            exponent = None
            if change.exponent is not None:
                exponent = numbering.intern(change.exponent)
                self.exponent_vars.setdefault(exponent, set()).add(number)
            if change.operation == "extend" and item.word_class is not None and item.cell is not None:
                self.cell_vars.setdefault((item.word_class, item.cell), set()).add(number)
            self.values[number] = _assess_reference(world, group_id, variable)
            if change.exponent is not None or change.operation == "extend":
                stats = class_stats(world, world.groups[group_id].main_code)
                if exponent is not None:
                    self.endings[exponent] = stats.endings.get(change.exponent)
                if change.operation == "extend" and item.word_class is not None and item.cell is not None:
                    cell = (item.word_class, item.cell)
                    self.cells[cell] = tuple(sorted(stats.exponents.get(cell, {}).items()))
        return self.values[number]
