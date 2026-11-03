"""Vzorek slov pro hodnocení zvukových procesů jako pole čísel (krok B3b, Python reference).

Hodnocení procesu (:mod:`cee.v2.assessment`) se dívá na ``SAMPLE_WORDS`` nejčastějších
slov kódu. Vzorek je v plochých polích podle čísel z registru:

- ``morphemes`` (``int32``): čísla morfémů ve vzorku, **v pořadí jmen morfémů** (řazení podle
  řetězců, na kterém stojí pořadí součtů hodnocení; číslo pořadí neurčuje);
- ``ids`` (``int64``): číslo aktuálního tvaru každého slova v bance tvarů;
- ``weights`` (``float64``): frekvence užití, nejméně 0,01, a ``total`` jejich součet (1, když je 0);
- ``vowels`` (``int64`` podle čísla hlásky): kolikrát se která samohláska ve vzorku vyskytuje.

Co se kdy přepočítá, určuje :class:`SampleKeeper` (výběr, váhy a jejich klíče) a
:class:`AssessmentVocabularyIndex` (čísla tvarů a samohlásky podle deníku tvarů). Pravidla
(přepočet jen při změně verze kódu, váhy jen při změně slovní zásoby či frekvencí pojmů)
jsou stejná jako dřív; Rust (``cee_core.AssessIndex``) drží totéž a výběr a váhy
od :class:`SampleKeeper` dostává jako pole.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, cast

import numpy as np
import numpy.typing as npt

from cee.v2.language.journal import FrequencyMap

if TYPE_CHECKING:
    from cee.v2.world import Code, World


def top_words(world: World, code: Code, count: int) -> list[str]:
    """``count`` nejčastějších tvarů slovní zásoby; shodní se řadí podle ID.

    Řazení je podle dvojice (−frekvence, ID), tedy úplné: pořadí, ve kterém
    množina slovní zásoby vydává tvary, na výsledku nic nemění.
    """
    units = list(code.phonology.vocabulary)
    keyed = sorted(zip([-value for value in world.usage_frequencies(code, units)], units))
    return [unit for _, unit in keyed[:count]]


def clipped_frequencies(world: World, code: Code, units: Iterable[str]) -> dict[str, float]:
    """Tvar → frekvence užití, nejméně 0,01 (ve stejném pořadí jako ``units``)."""
    units = list(units)
    return {unit: max(0.01, value) for unit, value in zip(units, world.usage_frequencies(code, units))}


@dataclass(slots=True)
class Vocabulary:
    """Vzorek slov jednoho kódu v polích (viz popis modulu)."""

    morphemes: npt.NDArray[np.int32]
    ids: npt.NDArray[np.int64]
    weights: npt.NDArray[np.float64]
    total: float
    vowels: npt.NDArray[np.int64]

    def names(self, world: World) -> list[str]:
        """Jména morfémů vzorku (pozice jako v polích)."""
        names = world.registry.morphemes.names
        return [names[number] for number in self.morphemes.tolist()]


def frequency_key(world: World) -> object:
    """Klíč frekvencí pojmů: když se nezmění, váhy vzorku se nepřepočítávají."""
    frequencies = world.concept_frequencies
    if isinstance(frequencies, FrequencyMap):
        return (id(frequencies), frequencies.version)
    return tuple(sorted(frequencies.items()))


def selection(world: World, code: Code, size: int) -> list[str]:
    """Výběr vzorku podle slovní zásoby, zapamatovaný pro verzi slovní zásoby kódu."""
    state = code.phonology
    picked = state.cache.get("vocabulary-sample")
    if picked is not None and picked[0] == state.lexicon_version:
        return cast(list[str], picked[1])
    chosen = top_words(world, code, size)
    state.cache["vocabulary-sample"] = (state.lexicon_version, chosen)
    return chosen


class SampleKeeper:
    """Které slovo je ve vzorku a s jakou váhou: výběr (v pořadí jmen) a frekvence užití.

    ``refresh`` se volá při změně verze kódu a vrátí, zda se výběr nebo váhy změnily.
    Výběr se přepočítává, když se změní verze slovní zásoby, váhy když se změní slovní zásoba
    nebo frekvence pojmů (nebo je úložiště tvarů jiné); jinak zůstávají, jaké byly.
    """

    __slots__ = ("token", "cursor", "lexicon_version", "size", "frequency", "morphemes", "weights", "total")

    def __init__(self) -> None:
        self.token: int | None = None
        self.cursor = 0
        self.lexicon_version = -1
        self.size = -1
        self.frequency: object = None
        self.morphemes = np.zeros(0, dtype=np.int32)
        self.weights = np.zeros(0, dtype=np.float64)
        self.total = 1.0

    def refresh(self, world: World, code: Code, size: int, dirty: bool = False) -> bool:
        """Dorovná výběr a váhy; ``True``, když se výběr změnil (``dirty`` ho vynutí)."""
        state, store = code.phonology, code.forms
        key = frequency_key(world)
        reset = dirty or self.token != store.token or self.cursor > len(store.log) or self.size != size
        lexical = self.lexicon_version != state.lexicon_version
        selected: list[str] | None = None
        numbering = world.registry.morphemes
        if lexical:
            selected = selection(world, code, size)
            # Změna slovníku, která nezmění vybraný vzorek (výpůjčka okrajového slova), stačí dorovnat
            # tvary a frekvence; stavět vzorek znovu ne.
            if not reset and sorted(selected) != [numbering.names[number] for number in self.morphemes.tolist()]:
                reset = True
        if reset:
            if selected is None:
                selected = selection(world, code, size)
            chosen = sorted(selected)
            self.morphemes = np.array([numbering.intern(unit) for unit in chosen], dtype=np.int32)
            self._weights(world, code, chosen)
        elif key != self.frequency or lexical:
            # Výběr se nemění (frekvence pojmů, nebo změna slovníku mimo vzorek).
            self._weights(world, code, [numbering.names[number] for number in self.morphemes.tolist()])
        self.token, self.cursor = store.token, len(store.log)
        self.lexicon_version, self.size, self.frequency = state.lexicon_version, size, key
        return reset

    def _weights(self, world: World, code: Code, chosen: list[str]) -> None:
        frequency = clipped_frequencies(world, code, chosen)
        self.weights = np.array([frequency[unit] for unit in chosen], dtype=np.float64)
        self.total = sum(frequency.values()) or 1.0


class AssessmentVocabularyIndex:
    """Vzorek jednoho kódu (reference v Pythonu): :class:`SampleKeeper` a čísla tvarů se samohláskami.

    Čísla tvarů a samohlásky se dorovnávají podle deníku přepsaných tvarů (``FormStore.log``):
    mění se jen slova, která se změnila. ``changes`` jsou pozice slov změněných od posledního
    přestavění vzorku (pro testy).
    """

    def __init__(self) -> None:
        self.keeper = SampleKeeper()
        self.vocabulary: Vocabulary | None = None
        self.token: int | None = None
        self.cursor = 0
        self.positions: dict[int, int] = {}
        self.changes: list[int] = []
        self.generation = 0

    def sync(self, world: World, code: Code) -> Vocabulary:
        from cee.v2.assessment import SAMPLE_WORDS

        table = world.table
        assert table is not None
        store, keeper = code.forms, self.keeper
        stale = self.vocabulary is None or self.token != store.token or self.cursor > len(store.log)
        rebuilt = keeper.refresh(world, code, SAMPLE_WORDS, dirty=stale)
        names = world.registry.morphemes.names
        bank = world.form_bank()
        if rebuilt or self.vocabulary is None:
            ids = np.array([world.form_id_of(code, names[number]) for number in keeper.morphemes.tolist()],
                           dtype=np.int64)
            vowels = np.zeros(len(table.vowel_mask), dtype=np.int64)
            for form_id in ids.tolist():
                _count_vowels(vowels, bank.forms[form_id], table.vowel_mask, 1)
            self.vocabulary = Vocabulary(keeper.morphemes, ids, keeper.weights, keeper.total, vowels)
            self.positions = {number: position for position, number in enumerate(keeper.morphemes.tolist())}
            self.generation += 1
            self.changes = []
        else:
            vocabulary = self.vocabulary
            vocabulary.weights, vocabulary.total = keeper.weights, keeper.total
            numbers = world.registry.morphemes.numbers
            dirty = sorted({numbers[unit] for unit in store.log[self.cursor:]} & self.positions.keys())
            for number in dirty:
                position = self.positions[number]
                new = world.form_id_of(code, names[number])
                old = int(vocabulary.ids[position])
                if old == new:
                    continue
                _count_vowels(vocabulary.vowels, bank.forms[old], table.vowel_mask, -1)
                _count_vowels(vocabulary.vowels, bank.forms[new], table.vowel_mask, 1)
                vocabulary.ids[position] = new
                self.changes.append(position)
        self.token, self.cursor = store.token, len(store.log)
        assert self.vocabulary is not None
        return self.vocabulary


def _count_vowels(
    counts: npt.NDArray[np.int64], form: tuple[int, ...], vowel_mask: npt.NDArray[np.bool_], sign: int
) -> None:
    """Přičte (``sign`` = 1) či odečte (−1) samohlásky tvaru k počtům podle čísla hlásky."""
    for segment in form:
        if vowel_mask[segment]:
            counts[segment] += sign
