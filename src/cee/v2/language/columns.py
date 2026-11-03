"""Číselné struktury stavu kódu: příznaky a pole podle čísel z registru (krok A3).

Stav kódu, který dřív tvořily množiny a slovníky s textovými klíči, je
tady v polích indexovaných číslem morfému či pojmu (:mod:`cee.v2.registry`).
Textové rozhraní zůstává jako fasáda (``in``, ``add``, ``get``, ``items``),
takže ho stávající kód používá dál; pole jsou k dispozici číselným jádrům.

Čísla určují jen místo v poli. Pořadí, na kterém záleží, drží tyto struktury
výslovně a stejně jako dřív:

- :class:`DominantMap` si pamatuje pořadí vložení pojmů (jako slovník);
- :class:`ProcessQueue` řadí podle dvojice (potřebný logit, ID morfému),
  tedy při shodě logitů podle *řetězce* ID, ne podle čísla;
- :class:`MorphemeSet` se iteruje v pořadí čísel (pořadí vzniku); nikde, kde
  na pořadí záleží, se po množině neiteruje bez ``sorted``.
"""

from __future__ import annotations

import bisect
import itertools
from array import array
from collections.abc import Iterable, Iterator, Mapping, MutableMapping, MutableSet
from typing import Any

from cee.v2.registry import Numbering

#: V polích: položka není nastavena.
NONE = -1


class MorphemeSet(MutableSet):  # type: ignore[type-arg]
    """Množina morfémů jako příznaky (bytearray) podle čísla morfému.

    Chová se jako ``set[str]`` (včetně rozdílů a průniků s jinými množinami;
    ty vracejí obyčejné ``set``). Přidání neznámého ID ho zapíše do registru.
    Iteruje se v pořadí čísel, ne v pořadí hašů; iteruje se nad kopií, takže
    změna množiny za chodu nevadí.
    """

    __slots__ = ("_numbering", "flags", "_count", "_listing")

    def __init__(self, numbering: Numbering, items: Iterable[str] = ()) -> None:
        self._numbering = numbering
        #: 1 = morfém č. N v množině; pole je tak dlouhé, jak daleko sahá nejvyšší číslo.
        self.flags = bytearray()
        self._count = 0
        #: Jména v pořadí čísel, dokud se množina nezměnila (odvozeno, jen pro iteraci).
        self._listing: list[str] | None = None
        for item in items:
            self.add(item)

    @classmethod
    def _from_iterable(cls, iterable: Iterable[str]) -> set[str]:  # type: ignore[override]
        return set(iterable)

    @classmethod
    def from_numbers(cls, numbering: Numbering, numbers: Iterable[int]) -> MorphemeSet:
        """Množina z čísel morfémů (bez opakování), jedním zápisem příznaků."""
        found = sorted(set(numbers))
        made = cls(numbering)
        if found:
            made.flags = bytearray(found[-1] + 1)
            for number in found:
                made.flags[number] = 1
            made._count = len(found)
        return made

    def __contains__(self, name: object) -> bool:
        number = self._numbering.numbers.get(name)  # type: ignore[arg-type]
        return number is not None and number < len(self.flags) and self.flags[number] == 1

    def has(self, number: int) -> bool:
        return number < len(self.flags) and self.flags[number] == 1

    def __len__(self) -> int:
        return self._count

    def __bool__(self) -> bool:
        return self._count > 0

    def __iter__(self) -> Iterator[str]:
        listing = self._listing
        if listing is None:
            names = self._numbering.names
            listing = self._listing = [
                names[number] for number in itertools.compress(range(len(self.flags)), self.flags)
            ]
        return iter(listing)

    def numbers(self) -> list[int]:
        """Čísla morfémů v množině vzestupně."""
        return list(itertools.compress(range(len(self.flags)), self.flags))

    def add(self, name: str) -> None:
        self.add_number(self._numbering.intern(name))

    def add_number(self, number: int) -> None:
        missing = number + 1 - len(self.flags)
        if missing > 0:
            self.flags.extend(bytes(missing))
        if not self.flags[number]:
            self.flags[number] = 1
            self._count += 1
            self._listing = None

    def discard(self, name: str) -> None:
        number = self._numbering.numbers.get(name)
        if number is not None:
            self.discard_number(number)

    def discard_number(self, number: int) -> None:
        if number < len(self.flags) and self.flags[number]:
            self.flags[number] = 0
            self._count -= 1
            self._listing = None

    def clear(self) -> None:
        self.flags = bytearray()
        self._count = 0
        self._listing = None

    def update(self, items: Iterable[str]) -> None:
        for item in items:
            self.add(item)

    def copy(self) -> MorphemeSet:
        copied = MorphemeSet(self._numbering)
        copied.flags = bytearray(self.flags)
        copied._count = self._count
        return copied

    def __repr__(self) -> str:
        return f"MorphemeSet({sorted(self)!r})"


class MorphemeCounts(MutableMapping):  # type: ignore[type-arg]
    """Morfém → kladný počet (int32 podle čísla morfému); nula v poli znamená „není“.

    Chová se jako ``dict[str, int]`` s kladnými hodnotami: uložení nuly nebo
    záporného čísla položku odebere. Iteruje se v pořadí čísel morfémů.
    """

    __slots__ = ("_numbering", "counts", "_size")

    def __init__(self, numbering: Numbering) -> None:
        self._numbering = numbering
        self.counts = array("i")
        self._size = 0

    def __getitem__(self, name: str) -> int:
        number = self._numbering.numbers.get(name)
        if number is None or number >= len(self.counts) or not self.counts[number]:
            raise KeyError(name)
        return self.counts[number]  # type: ignore[no-any-return]

    def get(self, name: str, default: Any = None) -> Any:
        number = self._numbering.numbers.get(name)
        if number is None or number >= len(self.counts) or not self.counts[number]:
            return default
        return self.counts[number]

    def __contains__(self, name: object) -> bool:
        number = self._numbering.numbers.get(name)  # type: ignore[arg-type]
        return number is not None and number < len(self.counts) and self.counts[number] > 0

    def __setitem__(self, name: str, count: int) -> None:
        number = self._numbering.intern(name)
        missing = number + 1 - len(self.counts)
        if missing > 0:
            self.counts.extend(array("i", [0]) * missing)
        old = self.counts[number]
        new = count if count > 0 else 0
        self._size += (new > 0) - (old > 0)
        self.counts[number] = new

    def __delitem__(self, name: str) -> None:
        if name not in self:
            raise KeyError(name)
        self[name] = 0

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[str]:
        names = self._numbering.names
        return iter([names[number] for number in itertools.compress(range(len(self.counts)), self.counts)])

    def __repr__(self) -> str:
        return f"MorphemeCounts({dict(self.items())!r})"


class DominantMap(MutableMapping):  # type: ignore[type-arg]
    """Pojem → jeho dominantní kořen: pole čísel kořenů podle čísla pojmu.

    Chová se jako slovník ``dict[str, str]`` včetně pořadí: iteruje se
    v pořadí, v jakém pojmy do mapy přišly (znovu vložený pojem je na konci,
    přepsaný zůstává na místě). Pořadí drží ``order``, pole ``roots`` drží
    jen hodnoty.
    """

    __slots__ = ("_concepts", "_morphemes", "roots", "order")

    def __init__(self, concepts: Numbering, morphemes: Numbering) -> None:
        self._concepts = concepts
        self._morphemes = morphemes
        #: Číslo pojmu → číslo kořene, −1 = pojem nemá dominantní kořen.
        self.roots = array("i")
        #: Čísla pojmů, které kořen mají, v pořadí vložení (hodnoty se nepoužívají).
        self.order: dict[int, None] = {}

    def _number(self, concept: object) -> int:
        number = self._concepts.numbers.get(concept)  # type: ignore[arg-type]
        if number is None or number >= len(self.roots) or self.roots[number] < 0:
            return NONE
        return number

    def __getitem__(self, concept: str) -> str:
        number = self._concepts.numbers.get(concept)
        if number is not None and number < len(self.roots):
            root = self.roots[number]
            if root >= 0:
                return self._morphemes.names[root]
        raise KeyError(concept)

    def get(self, concept: str, default: Any = None) -> Any:
        number = self._concepts.numbers.get(concept)
        if number is not None and number < len(self.roots):
            root = self.roots[number]
            if root >= 0:
                return self._morphemes.names[root]
        return default

    def __contains__(self, concept: object) -> bool:
        number = self._concepts.numbers.get(concept)  # type: ignore[arg-type]
        return number is not None and number < len(self.roots) and self.roots[number] >= 0

    def __setitem__(self, concept: str, root: str) -> None:
        number = self._concepts.intern(concept)
        missing = number + 1 - len(self.roots)
        if missing > 0:
            self.roots.extend(array("i", [NONE]) * missing)
        if self.roots[number] < 0:
            self.order[number] = None
        self.roots[number] = self._morphemes.intern(root)

    def __delitem__(self, concept: str) -> None:
        number = self._number(concept)
        if number < 0:
            raise KeyError(concept)
        self.roots[number] = NONE
        del self.order[number]

    def __len__(self) -> int:
        return len(self.order)

    def __iter__(self) -> Iterator[str]:
        names = self._concepts.names
        return iter([names[number] for number in self.order])

    def items(self) -> list[tuple[str, str]]:  # type: ignore[override]
        concepts, morphemes, roots = self._concepts.names, self._morphemes.names, self.roots
        return [(concepts[number], morphemes[roots[number]]) for number in self.order]

    def values(self) -> list[str]:  # type: ignore[override]
        morphemes, roots = self._morphemes.names, self.roots
        return [morphemes[roots[number]] for number in self.order]

    def clear(self) -> None:
        self.roots = array("i")
        self.order = {}

    def copy(self) -> dict[str, str]:
        """Obyčejný slovník se stejným obsahem a pořadím."""
        return dict(self.items())

    def __repr__(self) -> str:
        return f"DominantMap({dict(self.items())!r})"


class ProcessQueue:
    """Fronta fonologizace jednoho procesu: čekající morfémy podle potřebného logitu.

    Dvě rovnoběžná pole stejné délky, seřazená vzestupně podle dvojice
    (``needed``, ID morfému): ``needed`` je logit sdíleného podílu, při
    kterém si slovo změnu zapíše (float64), ``morphemes`` číslo morfému
    (int32). Shodné logity (buňky téhož lexému) se řadí podle *řetězce* ID,
    stejně jako dřív řadila dvojice (logit, ID); číslo pořadí neurčuje.
    """

    __slots__ = ("_numbering", "needed", "morphemes")

    def __init__(self, numbering: Numbering, pairs: Iterable[tuple[float, str]] = ()) -> None:
        self._numbering = numbering
        self.needed = array("d")
        self.morphemes = array("i")
        self.replace(pairs)

    def replace(self, pairs: Iterable[tuple[float, str]]) -> None:
        """Nový obsah z dvojic (logit, ID morfému); seřadí je."""
        ordered = sorted(pairs)
        intern = self._numbering.intern
        self.needed = array("d", [needed for needed, _ in ordered])
        self.morphemes = array("i", [intern(name) for _, name in ordered])

    def __len__(self) -> int:
        return len(self.needed)

    def __bool__(self) -> bool:
        return len(self.needed) > 0

    def insert(self, needed: float, name: str) -> None:
        """Vloží morfém na místo dané dvojicí (logit, ID); stejný morfém dvakrát nevkládat."""
        number = self._numbering.intern(name)
        queue = self.needed
        low = bisect.bisect_left(queue, needed)
        high = bisect.bisect_right(queue, needed, low)
        if high > low:
            names = self._numbering.names
            morphemes = self.morphemes
            low = bisect.bisect_left(range(low, high), name, key=lambda index: names[morphemes[index]]) + low
        self.needed.insert(low, needed)
        self.morphemes.insert(low, number)

    def pop_first(self) -> int:
        """Odebere první morfém a vrátí jeho číslo."""
        number = self.morphemes[0]
        del self.needed[0]
        del self.morphemes[0]
        return number  # type: ignore[no-any-return]

    def names(self) -> list[str]:
        names = self._numbering.names
        return [names[number] for number in self.morphemes]

    def pairs(self) -> list[tuple[float, str]]:
        names = self._numbering.names
        return [(needed, names[number]) for needed, number in zip(self.needed, self.morphemes)]

    def __iter__(self) -> Iterator[tuple[float, str]]:
        return iter(self.pairs())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ProcessQueue):
            return self.pairs() == other.pairs()
        if isinstance(other, list):
            return self.pairs() == other
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return f"ProcessQueue({self.pairs()!r})"


class QueueMap(dict):  # type: ignore[type-arg]
    """Proces → jeho fronta. Přiřazený seznam dvojic (logit, ID) se převede na :class:`ProcessQueue`."""

    __slots__ = ("numbering",)

    def __init__(self, numbering: Numbering) -> None:
        dict.__init__(self)
        self.numbering = numbering

    def __setitem__(self, key: str, value: Any) -> None:
        if type(value) is list:
            value = ProcessQueue(self.numbering, value)
        dict.__setitem__(self, key, value)

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key not in self:
            self[key] = default
        return dict.__getitem__(self, key)


# --- Pohledy na stav fronty v Rustu --------------------------------------------------------
#
# S rozšířením ``cee_core`` žijí fronty, příznaky čekajících a přepsaných morfémů
# a ``fixed_since`` v ``cee_core.NativeCode`` (podle čísla procesu a morfému).
# Python je čte přes tyto pohledy (stejná textová rozhraní jako ``QueueMap`` a
# slovníky množin); pohled je snímek, zápis do něj neexistuje.


class _NativeView(Mapping):  # type: ignore[type-arg]
    """Proces (ID proměnné) → snímek jeho stavu v ``NativeCode``; jen ke čtení."""

    __slots__ = ("_code", "_registry")

    def __init__(self, code: Any, registry: Any) -> None:
        self._code = code
        self._registry = registry

    def _number(self, variable_id: object) -> int | None:
        return self._registry.processes.numbers.get(variable_id)  # type: ignore[no-any-return]

    def _numbers(self) -> list[int]:
        raise NotImplementedError

    def _has(self, number: int) -> bool:
        raise NotImplementedError

    def _snapshot(self, number: int) -> Any:
        raise NotImplementedError

    def __getitem__(self, variable_id: str) -> Any:
        number = self._number(variable_id)
        if number is None or not self._has(number):
            raise KeyError(variable_id)
        return self._snapshot(number)

    def __iter__(self) -> Iterator[str]:
        names = self._registry.processes.names
        return iter([names[number] for number in self._numbers()])

    def __len__(self) -> int:
        return len(self._numbers())

    def __contains__(self, variable_id: object) -> bool:
        number = self._number(variable_id)
        return number is not None and self._has(number)

    def __bool__(self) -> bool:
        return bool(self._numbers())


class NativePending(_NativeView):
    """Proces → fronta fonologizace (``ProcessQueue``, snímek) živých procesů."""

    __slots__ = ()

    def _numbers(self) -> list[int]:
        return self._code.live()  # type: ignore[no-any-return]

    def _has(self, number: int) -> bool:
        return bool(self._code.status(number) == 1)

    def _snapshot(self, number: int) -> ProcessQueue:
        needed, morphemes = self._code.queue(number)
        queue = ProcessQueue(self._registry.morphemes)
        queue.needed = array("d", needed)
        queue.morphemes = array("i", morphemes)
        return queue


class NativeQueued(_NativeView):
    """Proces → množina morfémů, které ve frontě čekají (snímek), pro živé procesy."""

    __slots__ = ()

    def _numbers(self) -> list[int]:
        return self._code.live()  # type: ignore[no-any-return]

    def _has(self, number: int) -> bool:
        return bool(self._code.status(number) == 1)

    def _snapshot(self, number: int) -> MorphemeSet:
        return MorphemeSet.from_numbers(self._registry.morphemes, self._code.queued(number))


class NativeRestructured(_NativeView):
    """Proces → množina morfémů, které si změnu zapsaly (snímek); jen procesy, kde nějaký je."""

    __slots__ = ()

    def _numbers(self) -> list[int]:
        return [number for number in self._code.processes() if self._code.done(number)]

    def _has(self, number: int) -> bool:
        return bool(self._code.done(number))

    def _snapshot(self, number: int) -> MorphemeSet:
        return MorphemeSet.from_numbers(self._registry.morphemes, self._code.done(number))
