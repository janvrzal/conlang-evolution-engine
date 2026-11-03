"""Deníky změn vstupů používaných při hodnocení."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any

_MISSING = object()


class FrequencyMap(dict[str, float]):
    """Dict konceptových frekvencí s verzí a ID změněných konceptů.

    Inicializace a deepcopy zachovávají obsah bez záznamu falešných mutací.
    Běžné mutace mapy zaznamenávají jen hodnoty, které se skutečně změnily.
    """

    __slots__ = ("version", "log")

    def __init__(
        self,
        source: Mapping[str, float] | Iterable[tuple[str, float]] = (),
        **values: float,
    ) -> None:
        dict.__init__(self, source, **values)
        self.version = 0
        self.log: list[str] = []

    def _record(self, concept: str) -> None:
        self.version += 1
        self.log.append(concept)

    def __setitem__(self, concept: str, value: float) -> None:
        old = self.get(concept, _MISSING)
        dict.__setitem__(self, concept, value)
        if old is _MISSING or old != value:
            self._record(concept)

    def __delitem__(self, concept: str) -> None:
        dict.__delitem__(self, concept)
        self._record(concept)

    def update(self, source: Any = (), /, **values: float) -> None:
        incoming = dict(source, **values)
        for concept, value in incoming.items():
            self[concept] = value

    def setdefault(self, concept: str, default: Any = None) -> Any:
        if concept in self:
            return self[concept]
        self[concept] = default
        return default

    def pop(self, concept: str, default: Any = _MISSING) -> float | Any:
        if concept not in self:
            if default is _MISSING:
                raise KeyError(concept)
            return default
        value = dict.__getitem__(self, concept)
        del self[concept]
        return value

    def popitem(self) -> tuple[str, float]:
        if not self:
            raise KeyError("popitem(): dictionary is empty")
        concept = next(reversed(self))
        value = self[concept]
        del self[concept]
        return concept, value

    def clear(self) -> None:
        concepts = list(self)
        dict.clear(self)
        for concept in concepts:
            self._record(concept)

    def __ior__(self, source: Any) -> FrequencyMap:  # type: ignore[override,misc]
        self.update(source)
        return self

    def __copy__(self) -> FrequencyMap:
        return self.__deepcopy__({})

    def __deepcopy__(self, memo: dict[int, Any]) -> FrequencyMap:
        found = memo.get(id(self))
        if found is not None:
            return found
        copied = type(self)()
        memo[id(self)] = copied
        for concept, value in self.items():
            dict.__setitem__(copied, deepcopy(concept, memo), deepcopy(value, memo))
        copied.version = self.version
        copied.log = self.log.copy()
        return copied

    def __reduce__(self) -> tuple[Any, ...]:
        # Pickle by obsah obnovil přes ``__setitem__`` dřív, než existuje
        # ``version``; obnova proto jde přes :func:`_restore_frequencies`.
        return (_restore_frequencies, (dict(self), self.version, list(self.log)))


def _restore_frequencies(items: dict[str, float], version: int, log: list[str]) -> FrequencyMap:
    """Obnoví mapu frekvencí z pickle bez záznamu falešných změn."""
    restored = FrequencyMap(items)
    restored.version = version
    restored.log = log
    return restored
