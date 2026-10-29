"""Sdílené členství tvarů slov a průběžní kandidáti analogie."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from cee.v2 import morphology
from cee.v2.language.morphology import FormChange
from cee.v2.repertoire import Variable

if TYPE_CHECKING:
    from cee.v2.changes.base import InnovationContext
    from cee.v2.world import Code, World

Cell = tuple[str, str]


class WordMembershipIndex:
    """Členství a nezávisle čitelný deník dotčených jednotek."""

    def __init__(self) -> None:
        self.token: int | None = None
        self.cursor = self.vocab_cursor = 0
        self.version = self.lexicon_version = -1
        self.generation = 0
        self.units: set[str] = set()
        self.roots: dict[str, set[str]] = {}
        self.cells: dict[Cell, set[str]] = {}
        self.metadata: dict[str, tuple[str, Cell]] = {}
        self.changes: list[str] = []

    def _add(self, world: World, unit: str) -> None:
        item = world.morphemes[unit]
        if item.kind != "word":
            return
        assert item.word_class is not None and item.cell is not None
        cell = (item.word_class, item.cell)
        self.units.add(unit)
        self.metadata[unit] = (item.lexeme_id, cell)
        self.roots.setdefault(item.lexeme_id, set()).add(unit)
        self.cells.setdefault(cell, set()).add(unit)

    def _remove(self, unit: str) -> None:
        root, cell = self.metadata.pop(unit)
        self.units.remove(unit)
        self.roots[root].remove(unit)
        self.cells[cell].remove(unit)
        if not self.roots[root]:
            del self.roots[root]
        if not self.cells[cell]:
            del self.cells[cell]

    def sync(self, world: World, code: Code) -> None:
        state, store = code.phonology, code.forms
        if self.version == state.version:
            return
        journal = state.vocabulary_log
        reset = (self.token != store.token or self.cursor > len(store.log)
                 or self.vocab_cursor > len(journal)
                 or (self.lexicon_version != state.lexicon_version and self.vocab_cursor == len(journal)))
        if reset:
            self.units.clear()
            self.roots.clear()
            self.cells.clear()
            self.metadata.clear()
            for unit in sorted(state.vocabulary):
                self._add(world, unit)
            self.generation += 1
            self.changes = []
        else:
            dirty: set[str] = set()
            for action, unit in journal[self.vocab_cursor:]:
                if action == "leave" and unit in self.units:
                    self._remove(unit)
                    dirty.add(unit)
                elif action == "enter" and unit not in self.units:
                    self._add(world, unit)
                    if unit in self.units:
                        dirty.add(unit)
            if self.lexicon_version != state.lexicon_version:
                actual = {unit for unit in state.vocabulary if world.morphemes[unit].kind == "word"}
                for unit in sorted(self.units - actual):
                    self._remove(unit)
                    dirty.add(unit)
                for unit in sorted(actual - self.units):
                    self._add(world, unit)
                    dirty.add(unit)
            for unit in store.log[self.cursor:]:
                if unit in self.units:
                    dirty.add(unit)
                dirty.update(self.roots.get(unit, ()))
            self.changes.extend(sorted(dirty))
        self.token, self.cursor = store.token, len(store.log)
        self.vocab_cursor, self.version = len(journal), state.version
        self.lexicon_version = state.lexicon_version


def membership(world: World, code: Code) -> WordMembershipIndex:
    """Vrátí jeden index sdílený konzumenty ve stavu kódu."""
    state = code.phonology
    entry = state.cache.get("word-membership-index")
    index = cast(WordMembershipIndex, entry[1]) if entry else WordMembershipIndex()
    state.cache["word-membership-index"] = (state.version, index)
    index.sync(world, code)
    return index


class MorphologyCandidateIndex:
    """Kandidáti vyrovnání a rozšíření se sdíleným členstvím."""

    def __init__(self) -> None:
        self.version = -1
        self.generation = -1
        self.cursor = 0
        self.descriptors: dict[Cell, tuple[str | None, bool]] = {}
        self.contributions: dict[str, dict[str, FormChange]] = {"leveling": {}, "extension": {}}
        self.results: dict[str, dict[str, FormChange]] = {"leveling": {}, "extension": {}}
        self.sorted_sites: dict[str, list[str] | None] = {"leveling": None, "extension": None}

    def sync(self, context: InnovationContext, kind: str) -> dict[str, FormChange]:
        from cee.v2.changes.morphology import Extension, Leveling

        state = context.code.phonology
        if self.version == state.version:
            return self.results[kind]
        words = membership(context.world, context.code)
        if self.generation != words.generation or self.cursor > len(words.changes):
            self.descriptors.clear()
            for values in (*self.contributions.values(), *self.results.values()):
                values.clear()
            self.sorted_sites["leveling"] = None
            self.sorted_sites["extension"] = None
            dirty = set(words.units)
        else:
            dirty = set(words.changes[self.cursor:])
        stats = morphology.class_stats(context.world, context.code)
        descriptors = {}
        for cell in words.cells:
            productive = stats.productive(*cell)
            descriptors[cell] = (productive, productive is not None and bool(stats.endings.get(productive)))
            if self.descriptors.get(cell) != descriptors[cell]:
                dirty.update(words.cells[cell])
        self.descriptors = descriptors
        leveling, extension = Leveling(), Extension()
        for unit in sorted(dirty):
            for name in ("leveling", "extension"):
                old = self.contributions[name].pop(unit, None)
                if old is not None:
                    self.results[name].pop(Variable("form", old.key).id, None)
                    self.sorted_sites[name] = None
            if unit not in words.units:
                continue
            for name, change in (("leveling", leveling._candidate(context, unit)),
                                 ("extension", extension._candidate(context, unit, stats))):
                if change is not None:
                    self.contributions[name][unit] = change
                    self.results[name][Variable("form", change.key).id] = change
                    self.sorted_sites[name] = None
        self.generation, self.cursor = words.generation, len(words.changes)
        self.version = state.version
        return self.results[kind]

    def sites_sorted(self, kind: str) -> list[str]:
        cached = self.sorted_sites.get(kind)
        if cached is None:
            cached = self.sorted_sites[kind] = sorted(self.results[kind])
        return cached


class WeaknessIndex:
    """Celočíselné počty všech a splynulých tvarů gramatické buňky."""

    def __init__(self) -> None:
        self.version = -1
        self.generation = -1
        self.cursor = 0
        self.contributions: dict[str, tuple[Cell, bool]] = {}
        self.counts: dict[Cell, tuple[int, int]] = {}

    def sync(self, world: World, code: Code) -> None:
        if self.version == code.phonology.version:
            return
        words = membership(world, code)
        if self.generation != words.generation or self.cursor > len(words.changes):
            self.contributions.clear()
            self.counts.clear()
            dirty = set(words.units)
        else:
            dirty = set(words.changes[self.cursor:])
        for unit in sorted(dirty):
            previous = self.contributions.pop(unit, None)
            if previous is not None:
                cell, merged = previous
                total, count = self.counts[cell]
                self.counts[cell] = (total - 1, count - int(merged))
            if unit not in words.units:
                continue
            root, cell = words.metadata[unit]
            merged = world.form_of(code, unit) == world.form_of(code, root)
            self.contributions[unit] = (cell, merged)
            total, count = self.counts.get(cell, (0, 0))
            self.counts[cell] = (total + 1, count + int(merged))
        self.generation, self.cursor = words.generation, len(words.changes)
        self.version = code.phonology.version

    def value(self, cell: Cell) -> float:
        total, merged = self.counts.get(cell, (0, 0))
        return merged / total if total else 1.0
