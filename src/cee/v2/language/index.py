"""Průběžné indexy nad slovní zásobou kódu: počítá se jen to, co se změnilo.

Statistiky skupiny (prostředí hlásek pro zvukové změny, koncovky tříd slov
pro analogii) se dřív stavěly znovu z celé slovní zásoby po každé změně
jakéhokoli tvaru, a ta při probíhající zvukové změně nastává skoro každý
krok. Index si pamatuje příspěvek každého slova a při dotazu dorovná jen:

- slova, která od minula přibyla do slovní zásoby nebo z ní ubyla
  (rozdíl množin),
- slova, jejichž tvar se od minula přepsal (deník úložiště tvarů).

Když deník nesouhlasí (jiné úložiště, třeba po kopii stavu), index se
postaví znovu celý. Výsledek je vždy stejný jako výpočet od nuly.

Index nedrží odkazy na svět ani funkce, jen data: kopie stavu (checkpoint)
tak nikdy nepočítá nad cizím světem.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from typing import TYPE_CHECKING, Generic, Hashable, TypeVar

if TYPE_CHECKING:
    from cee.v2.world import Code, World

Contribution = TypeVar("Contribution", bound=Hashable)


class VocabularyIndex(ABC, Generic[Contribution]):
    """Součet příspěvků slov slovní zásoby, udržovaný podle změn."""

    def __init__(self) -> None:
        self._token: int | None = None
        self._cursor = 0
        self._vocab_cursor = 0
        self._lexicon_version = -1
        self._counted: dict[str, Contribution | None] = {}

    @abstractmethod
    def contribution(self, world: World, code: Code, unit: str) -> Contribution | None: ...

    @abstractmethod
    def add(self, value: Contribution) -> None: ...

    @abstractmethod
    def remove(self, value: Contribution) -> None: ...

    @abstractmethod
    def reset(self) -> None: ...

    def sync(self, world: World, code: Code) -> bool:
        """Dorovná změny; vrací ``True``, když se součet změnil."""
        state, forms = code.phonology, code.forms
        vocabulary = state.vocabulary
        reset = (
            self._token != forms.token
            or self._cursor > len(forms.log)
            or self._vocab_cursor > len(state.vocabulary_log)
        )
        if reset:
            self.reset()
            self._counted = {}
            for unit in sorted(vocabulary):
                self._counted[unit] = value = self.contribution(world, code, unit)
                self._give(value)
            self._token, self._cursor = forms.token, len(forms.log)
            self._vocab_cursor = len(state.vocabulary_log)
            self._lexicon_version = state.lexicon_version
            return True

        changed = set(forms.log[self._cursor :])
        self._cursor = len(forms.log)
        counted = self._counted
        touched = False

        vocab_unchanged = (
            self._vocab_cursor == len(state.vocabulary_log)
            and self._lexicon_version == state.lexicon_version
            and len(counted) == len(vocabulary)
        )

        if vocab_unchanged:
            for unit in sorted(u for u in changed if u in counted):
                new = self.contribution(world, code, unit)
                if new != counted[unit]:
                    self._take(counted[unit])
                    self._give(new)
                    counted[unit] = new
                    touched = True
        else:
            for unit in sorted(counted.keys() - vocabulary):
                touched |= self._take(counted.pop(unit))
            for unit in sorted(changed & counted.keys()):
                new = self.contribution(world, code, unit)
                if new != counted[unit]:
                    self._take(counted[unit])
                    self._give(new)
                    counted[unit] = new
                    touched = True
            for unit in sorted(vocabulary - counted.keys()):
                counted[unit] = value = self.contribution(world, code, unit)
                touched |= self._give(value)
            self._vocab_cursor = len(state.vocabulary_log)
            self._lexicon_version = state.lexicon_version

        return touched

    def _give(self, value: Contribution | None) -> bool:
        if value is None:
            return False
        self.add(value)
        return True

    def _take(self, value: Contribution | None) -> bool:
        if value is None:
            return False
        self.remove(value)
        return True


Key = TypeVar("Key", bound=Hashable)


def _decrement(counter: Counter[Key], key: Key) -> None:
    counter[key] -= 1
    if counter[key] <= 0:
        del counter[key]


Context = tuple[int, int, int, bool, int]


class ContextIndex(VocabularyIndex[tuple[Context, ...]]):
    """Kolikrát se ve slovní zásobě vyskytuje (předchozí, hláska, následující, přízvuk, za-následující)."""

    def __init__(self) -> None:
        super().__init__()
        self.counts: Counter[Context] = Counter()
        self.segment_counts: Counter[int] = Counter()
        self.generation: int = 0
        self.deltas: list[tuple[Context, int]] = []
        self._step_delta: Counter[Context] = Counter()
        self._in_reset: bool = False

    def inventory(self) -> tuple[int, ...]:
        return tuple(sorted(self.segment_counts))

    def contribution(self, world: World, code: Code, unit: str) -> tuple[Context, ...]:
        from cee.v2.changes.sound import form_contexts

        assert world.table is not None
        return form_contexts(world.form_of(code, unit), world.table, code.stress_rule)

    def add(self, value: tuple[Context, ...]) -> None:
        for key in value:
            old = self.counts[key]
            self.counts[key] = old + 1
            if old == 0:
                self.segment_counts[key[1]] += 1
            if not self._in_reset:
                self._step_delta[key] += 1

    def remove(self, value: tuple[Context, ...]) -> None:
        for key in value:
            old = self.counts[key]
            if old <= 1:
                if old == 1:
                    del self.counts[key]
                    self.segment_counts[key[1]] -= 1
                    if self.segment_counts[key[1]] <= 0:
                        del self.segment_counts[key[1]]
            else:
                self.counts[key] = old - 1
            if not self._in_reset:
                self._step_delta[key] -= 1

    def reset(self) -> None:
        self.counts.clear()
        self.segment_counts.clear()
        self.generation += 1
        self.deltas.clear()
        self._step_delta.clear()

    def sync(self, world: World, code: Code) -> bool:
        state, forms = code.phonology, code.forms
        reset_needed = (
            self._token != forms.token
            or self._cursor > len(forms.log)
            or self._vocab_cursor > len(state.vocabulary_log)
        )
        self._step_delta.clear()
        self._in_reset = reset_needed
        try:
            touched = super().sync(world, code)
        finally:
            self._in_reset = False

        if not reset_needed and self._step_delta:
            for ctx, diff in sorted(self._step_delta.items()):
                if diff != 0:
                    self.deltas.append((ctx, diff))
            self._step_delta.clear()
        return touched
        return touched


Exponent = tuple[str, str, str, tuple[int, ...]]


class ExponentIndex(VocabularyIndex[Exponent]):
    """Koncovky tvarů slov: (třída, buňka) → koncovka → počet, a jejich podoby."""

    def __init__(self) -> None:
        super().__init__()
        self.exponents: dict[tuple[str, str], Counter[str]] = {}
        self.shapes: dict[str, Counter[tuple[int, ...]]] = {}

    def contribution(self, world: World, code: Code, unit: str) -> Exponent | None:
        morpheme = world.morphemes[unit]
        if morpheme.kind != "word" or morpheme.word_class is None or morpheme.cell is None:
            return None
        state = world.unit_of(code, unit)
        if state.exponent is None:
            return None
        return (morpheme.word_class, morpheme.cell, state.exponent, state.ending)

    def add(self, value: Exponent) -> None:
        word_class, cell, exponent, ending = value
        self.exponents.setdefault((word_class, cell), Counter())[exponent] += 1
        self.shapes.setdefault(exponent, Counter())[ending] += 1

    def remove(self, value: Exponent) -> None:
        word_class, cell, exponent, ending = value
        _decrement(self.exponents[(word_class, cell)], exponent)
        if not self.exponents[(word_class, cell)]:
            del self.exponents[(word_class, cell)]
        _decrement(self.shapes[exponent], ending)
        if not self.shapes[exponent]:
            del self.shapes[exponent]

    def reset(self) -> None:
        self.exponents, self.shapes = {}, {}
