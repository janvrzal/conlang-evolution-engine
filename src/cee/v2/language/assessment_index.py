"""Přírůstkové podklady pro hodnocení zvukových procesů."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, cast

import numpy as np

from cee.v2.language.journal import FrequencyMap

if TYPE_CHECKING:
    from cee.v2.assessment import _Vocabulary
    from cee.v2.world import Code, World


class AssessmentVocabularyIndex:
    """Vzorek a deník pozic, jejichž tvar se změnil."""

    def __init__(self) -> None:
        self.token: int | None = None
        self.cursor = 0
        self.lexicon_version = -1
        self.sample_size = -1
        self.frequency_token: object = None
        self.vocabulary: _Vocabulary | None = None
        self.positions: dict[str, int] = {}
        self.changes: list[int] = []
        self.generation = 0

    @staticmethod
    def frequency_key(world: World) -> object:
        frequencies = world.concept_frequencies
        if isinstance(frequencies, FrequencyMap):
            return (id(frequencies), frequencies.version)
        return tuple(sorted(frequencies.items()))

    def sync(self, world: World, code: Code) -> _Vocabulary:
        from cee.v2.assessment import SAMPLE_WORDS, _Vocabulary

        assert world.table is not None
        state, store = code.phonology, code.forms
        frequency_key = self.frequency_key(world)
        reset = (self.vocabulary is None or self.token != store.token or self.cursor > len(store.log)
                 or self.sample_size != SAMPLE_WORDS)
        lexical = self.lexicon_version != state.lexicon_version
        selected: list[str] | None = None
        if lexical:
            picked = state.cache.get("vocabulary-sample")
            if picked is not None and picked[0] == state.lexicon_version:
                selected = cast(list[str], picked[1])
            else:
                selected = sorted(
                    state.vocabulary, key=lambda unit: (-world.usage_frequency(code, unit), unit)
                )[:SAMPLE_WORDS]
                state.cache["vocabulary-sample"] = (state.lexicon_version, selected)
            # Změna slovníku, která nezmění vybraný vzorek (výpůjčka okrajového
            # slova), stačí dorovnat tvary a frekvence; stavět vzorek znovu ne.
            if not reset and self.vocabulary is not None and sorted(selected) != self.vocabulary.morphemes:
                reset = True
        if reset:
            if selected is None:
                picked = state.cache.get("vocabulary-sample")
                if picked is not None and picked[0] == state.lexicon_version:
                    selected = cast(list[str], picked[1])
                else:
                    selected = sorted(
                        state.vocabulary, key=lambda unit: (-world.usage_frequency(code, unit), unit)
                    )[:SAMPLE_WORDS]
                    state.cache["vocabulary-sample"] = (state.lexicon_version, selected)
            chosen = sorted(selected)
            forms = {unit: world.form_of(code, unit) for unit in chosen}
            frequency = {unit: max(0.01, world.usage_frequency(code, unit)) for unit in chosen}
            owners: dict[tuple[int, ...], list[str]] = {}
            vowels: Counter[int] = Counter()
            for unit, form in forms.items():
                owners.setdefault(form, []).append(unit)
                vowels.update(segment for segment in form if world.table.is_vowel(segment))
            ids = world.form_bank().ids_of(list(forms.values()))
            weights = np.array([frequency[unit] for unit in chosen], dtype=np.float64)
            self.vocabulary = _Vocabulary(forms, frequency, owners, sum(frequency.values()) or 1.0,
                                          vowels, ids, chosen, weights)
            self.positions = {unit: position for position, unit in enumerate(chosen)}
            self.generation += 1
            self.changes = []
        else:
            assert self.vocabulary is not None
            vocabulary = self.vocabulary
            dirty = sorted(set(store.log[self.cursor:]) & self.positions.keys())
            for unit in dirty:
                old, new = vocabulary.forms[unit], world.form_of(code, unit)
                if old == new:
                    continue
                members = vocabulary.owners[old]
                members.remove(unit)
                if not members:
                    del vocabulary.owners[old]
                vocabulary.owners.setdefault(new, []).append(unit)
                vocabulary.owners[new].sort()
                vocabulary.vowels.subtract(segment for segment in old if world.table.is_vowel(segment))
                vocabulary.vowels.update(segment for segment in new if world.table.is_vowel(segment))
                vocabulary.forms[unit] = new
                position = self.positions[unit]
                vocabulary.ids[position] = world.form_bank().id_of(new)
                self.changes.append(position)
            if frequency_key != self.frequency_token or lexical:
                # Výběr se nemění (frekvence pojmů, nebo změna slovníku mimo vzorek).
                frequency = {unit: max(0.01, world.usage_frequency(code, unit))
                             for unit in vocabulary.morphemes}
                vocabulary.frequency.clear()
                vocabulary.frequency.update(frequency)
                vocabulary.weights[:] = [frequency[unit] for unit in vocabulary.morphemes]
                object.__setattr__(vocabulary, "total", sum(frequency.values()) or 1.0)
        self.token, self.cursor = store.token, len(store.log)
        self.lexicon_version, self.sample_size = state.lexicon_version, SAMPLE_WORDS
        self.frequency_token = frequency_key
        assert self.vocabulary is not None
        return self.vocabulary
