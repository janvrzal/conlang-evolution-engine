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
        vocabulary, forms = code.phonology.vocabulary, code.forms
        if self._token != forms.token or self._cursor > len(forms.log):
            self.reset()
            self._counted = {}
            for unit in sorted(vocabulary):
                self._counted[unit] = value = self.contribution(world, code, unit)
                self._give(value)
            self._token, self._cursor = forms.token, len(forms.log)
            return True
        changed = set(forms.log[self._cursor :])
        self._cursor = len(forms.log)
        counted = self._counted
        touched = False
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


Context = tuple[int, int, int, bool]


class ContextIndex(VocabularyIndex[tuple[Context, ...]]):
    """Kolikrát se ve slovní zásobě vyskytuje (předchozí, hláska, následující, přízvuk)."""

    def __init__(self) -> None:
        super().__init__()
        self.counts: Counter[Context] = Counter()

    def contribution(self, world: World, code: Code, unit: str) -> tuple[Context, ...]:
        from cee.v2.changes.sound import form_contexts

        assert world.table is not None
        return form_contexts(world.form_of(code, unit), world.table, code.stress_rule)

    def add(self, value: tuple[Context, ...]) -> None:
        self.counts.update(value)

    def remove(self, value: tuple[Context, ...]) -> None:
        for key in value:
            _decrement(self.counts, key)

    def reset(self) -> None:
        self.counts = Counter()


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
