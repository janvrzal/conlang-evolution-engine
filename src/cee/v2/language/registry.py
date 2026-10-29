"""Převod stabilních řetězcových ID na interní čísla pro pole."""

from __future__ import annotations

from bisect import insort


class IdRegistry:
    """Registr pouze přidává ID; jejich čísla nikdy nemění.

    Čísla odrážejí pořadí registrace, a proto nesmějí určovat pořadí
    výpočtu. K tomu slouží :meth:`sorted_indices`, seřazené podle ID.
    Hluboká kopie registru má vlastní data a může růst nezávisle.
    """

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._indices: dict[str, int] = {}
        self._sorted: list[tuple[str, int]] = []

    def __len__(self) -> int:
        return len(self._ids)

    def register(self, identifier: str) -> int:
        """Vrátí stávající číslo, nebo přidá nové ID na konec registru."""
        found = self._indices.get(identifier)
        if found is None:
            found = len(self._ids)
            self._ids.append(identifier)
            self._indices[identifier] = found
            insort(self._sorted, (identifier, found))
        return found

    def index_of(self, identifier: str) -> int:
        """Číslo již registrovaného ID; neznámé ID vyvolá KeyError."""
        return self._indices[identifier]

    def id_of(self, index: int) -> str:
        """ID pod daným číslem; záporná a neznámá čísla jsou neplatná."""
        if index < 0:
            raise IndexError(index)
        return self._ids[index]

    def sorted_indices(self) -> tuple[int, ...]:
        """Čísla v lexikografickém pořadí odpovídajících řetězcových ID."""
        return tuple(index for _, index in self._sorted)
