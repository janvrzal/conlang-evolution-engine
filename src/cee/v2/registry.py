"""Číselné registry entit světa: textové ID ↔ pořadové číslo (krok A2 přípravy na Rust).

Pole, ve kterých bude stav kódu a jádra v Rustu, se indexují čísly, ne
řetězci. Každý druh entity (morfém, varianta, proměnná, pojem, skupina,
proces) má v registru vlastní číslování:

- číslo se přidělí v pořadí vzniku (první uložení do světa) a už se nemění;
- registr jen přibývá (nic se neodebírá ani nepřečísluje), takže číslo
  zůstává platným indexem pole po celý běh;
- registr patří světu a kopíruje se s ním (checkpoint je hluboká kopie). Dvě
  větve běhu tak mohou vytvořit různé morfémy se stejným číslem a nic se
  nesdílí;
- **čísla nikdy neurčují pořadí**. Kde engine řadí podle řetězcových ID
  (``sorted``), řadí dál podle nich; pole jen *uchovává* hodnoty pod číslem.
  Když pole musí vyjít v pořadí řetězců, dá ho :meth:`Numbering.ranks`
  (pozice čísla v seřazení řetězců, odvozené, ne uložené).

Textová ID zůstávají v historii, exportu i veřejném API.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator

import numpy as np
import numpy.typing as npt

#: Druhy entit, které registr číslováním zná.
KINDS = ("morpheme", "variant", "variable", "concept", "group", "process")
_ATTRIBUTE = {
    "morpheme": "morphemes", "variant": "variants", "variable": "variables",
    "concept": "concepts", "group": "groups", "process": "processes",
}


class Numbering:
    """Přidávací číslování jednoho druhu entity: řetězec ↔ číslo od nuly."""

    __slots__ = ("kind", "names", "numbers", "_ranks")

    def __init__(self, kind: str) -> None:
        self.kind = kind
        #: Číslo → řetězec (v pořadí vzniku) a řetězec → číslo.
        self.names: list[str] = []
        self.numbers: dict[str, int] = {}
        self._ranks: npt.NDArray[np.int32] | None = None

    def __len__(self) -> int:
        return len(self.names)

    def __contains__(self, name: object) -> bool:
        return name in self.numbers

    def __iter__(self) -> Iterator[str]:
        return iter(self.names)

    def intern(self, name: str) -> int:
        """Číslo řetězce; neznámému přidělí další volné."""
        found = self.numbers.get(name)
        if found is None:
            found = self.numbers[name] = len(self.names)
            self.names.append(name)
        return found

    def intern_many(self, names: Iterable[str]) -> list[int]:
        return [self.intern(name) for name in names]

    def get(self, name: str, default: int = -1) -> int:
        """Číslo řetězce, nebo ``default`` (−1), když ho registr nezná."""
        return self.numbers.get(name, default)

    def number(self, name: str) -> int:
        """Číslo známého řetězce; neznámý je chyba (na rozdíl od :meth:`intern`)."""
        return self.numbers[name]

    def name(self, number: int) -> str:
        return self.names[number]

    def ranks(self) -> npt.NDArray[np.int32]:
        """Pozice každého čísla v seřazení řetězců (``ranks()[n]`` = pořadí ``names[n]``).

        Odvozené pole: dovoluje seřadit čísla stejně jako řetězce (třeba
        ``np.lexsort``), aniž by pořadí určovalo samo číslo. Přepočítává se
        jen po přibytku nových řetězců.
        """
        ranks = self._ranks
        if ranks is None or len(ranks) != len(self.names):
            order = sorted(range(len(self.names)), key=self.names.__getitem__)
            ranks = np.empty(len(order), dtype=np.int32)
            ranks[order] = np.arange(len(order), dtype=np.int32)
            self._ranks = ranks
        return ranks

    def copy(self) -> Numbering:
        copied = Numbering(self.kind)
        copied.names = self.names.copy()
        copied.numbers = self.numbers.copy()
        return copied

    def __deepcopy__(self, memo: dict[int, Any]) -> Numbering:
        # Řetězce jsou neměnné, stačí zkopírovat kontejnery (rychlejší než obecný deepcopy).
        copied = memo[id(self)] = self.copy()
        return copied


class Registry:
    """Číslování všech druhů entit jednoho světa."""

    __slots__ = ("morphemes", "variants", "variables", "concepts", "groups", "processes")

    def __init__(self) -> None:
        self.morphemes = Numbering("morpheme")
        self.variants = Numbering("variant")
        self.variables = Numbering("variable")
        self.concepts = Numbering("concept")
        self.groups = Numbering("group")
        self.processes = Numbering("process")

    def of(self, kind: str) -> Numbering:
        """Číslování podle názvu druhu (viz :data:`KINDS`)."""
        return getattr(self, _ATTRIBUTE[kind])  # type: ignore[no-any-return]

    def copy(self) -> Registry:
        copied = Registry()
        for kind in KINDS:
            setattr(copied, _ATTRIBUTE[kind], self.of(kind).copy())
        return copied

    def __repr__(self) -> str:
        return "Registry(" + ", ".join(f"{_ATTRIBUTE[kind]}={len(self.of(kind))}" for kind in KINDS) + ")"


class RegisteredDict(dict):  # type: ignore[type-arg]
    """Slovník světa (morfémy, varianty, ...), který klíče při uložení zapíše do registru.

    Čtení je obyčejné čtení slovníku. Číslo klíče vzniká v okamžiku, kdy se
    entita poprvé uloží; to je pořadí vzniku. Odebrání z registru nic neubere
    (číslo zůstane obsazené). Slovník nezná pořadí čísel: iteruje se jako
    dosud, v pořadí vkládání.

    Lexikální proměnná (klíč = pojem) zapíše do registru i svůj pojem.
    """

    __slots__ = ("_registry", "_kind", "_numbering")

    def __init__(self, registry: Registry, kind: str, items: Any = ()) -> None:
        dict.__init__(self)
        self._registry = registry
        self._kind = kind
        self._numbering = registry.of(kind)
        for key, value in dict(items).items():
            self[key] = value

    def __setitem__(self, key: str, value: Any) -> None:
        self._numbering.intern(key)
        if self._kind == "variable" and getattr(value, "kind", None) == "lexical":
            self._registry.concepts.intern(value.key)
        dict.__setitem__(self, key, value)

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key not in self:
            self[key] = default
        return dict.__getitem__(self, key)

    def update(self, source: Any = (), /, **values: Any) -> None:
        for key, value in dict(source, **values).items():
            self[key] = value

    def __ior__(self, source: Any) -> RegisteredDict:  # type: ignore[override,misc]
        self.update(source)
        return self

    def copy(self) -> dict:  # type: ignore[type-arg,override]
        """Obyčejný slovník (kopie nemá vlastní registr)."""
        return dict(self)

    def __reduce__(self) -> tuple[Any, ...]:
        # Kopie (deepcopy, pickle) se skládá z registru a obsahu; registr se
        # tak v rámci jedné kopie světa sdílí s kopií slovníku.
        return (_restore, (self._registry, self._kind, dict(self)))


def _restore(registry: Registry, kind: str, items: dict[str, Any]) -> RegisteredDict:
    """Obnoví slovník ze stavu kopie; registr už čísla zná, neříká se mu nic nového."""
    restored = RegisteredDict(registry, kind)
    dict.update(restored, items)
    return restored
