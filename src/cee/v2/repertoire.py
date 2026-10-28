"""Repertoár: proměnné, varianty a jejich frekvence (iterace 1 a 2).

Jazyk kódu *je* jeho repertoár. Neexistuje žádný další „stav jazyka“, který
by se s ním mohl rozejít.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

import numpy as np
import numpy.typing as npt

VariableKind = Literal["process", "lexical", "form", "construction"]

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Variable:
    """Místo, kde může existovat variace, například slovo pro pojem WATER."""

    kind: VariableKind
    key: str

    @property
    def id(self) -> str:
        return f"{self.kind}:{self.key}"


@dataclass(frozen=True, slots=True)
class Origin:
    """Původ varianty; ``change=None`` znamená zděděnou z protojazyka."""

    change: str | None
    tick: int
    year: float
    group: str | None
    parent: str | None = None


@dataclass(frozen=True, slots=True)
class Variant:
    """Jedna možná hodnota proměnné. Obsah ``payload`` určuje typ proměnné."""

    id: str
    variable: str
    payload: Mapping[str, Any]
    origin: Origin


class Distribution:
    """Frekvence soutěžících variant jedné proměnné v jednom kódu.

    Varianty jsou vždy seřazené podle ID, takže stejný stav má vždy stejný
    tvar. ``previous`` je klouzavý stav zhruba o generaci zpět, z něhož
    přenos počítá inkrementaci (Labov).
    """

    __slots__ = ("variants", "freqs", "previous")

    def __init__(
        self,
        variants: tuple[str, ...],
        freqs: FloatArray,
        previous: FloatArray | None = None,
    ):
        if len(variants) != len(freqs):
            raise ValueError("Počet variant a frekvencí se musí shodovat.")
        if list(variants) != sorted(variants):
            raise ValueError("Varianty musí být seřazené podle ID.")
        self.variants = variants
        self.freqs = freqs
        self.previous = freqs.copy() if previous is None else previous

    @classmethod
    def fixed(cls, variant_id: str) -> Distribution:
        return cls((variant_id,), np.ones(1))

    @property
    def is_fixed(self) -> bool:
        return len(self.variants) == 1

    def frequency(self, variant_id: str) -> float:
        try:
            return float(self.freqs[self.variants.index(variant_id)])
        except ValueError:
            return 0.0

    def dominant(self) -> tuple[str, float]:
        """Nejčastější varianta; shodu rozhodne pořadí ID, ne náhoda."""
        index = int(np.argmax(self.freqs))
        return self.variants[index], float(self.freqs[index])

    def as_dict(self) -> dict[str, float]:
        return {variant: float(freq) for variant, freq in zip(self.variants, self.freqs)}

    def with_innovation(self, variant_id: str, share: float) -> Distribution:
        """Nová varianta vstoupí s podílem ``share``; ostatní se úměrně zmenší.

        Inovace nemá při vzniku žádný „trend“: ``previous`` se nastaví na
        stejné hodnoty, jinak by ji inkrementace hned při narození postrčila.
        """
        if variant_id in self.variants:
            raise ValueError(f"Varianta {variant_id} už v rozdělení je.")
        merged = sorted((*self.variants, variant_id))
        freqs = np.zeros(len(merged))
        for variant, freq in zip(self.variants, self.freqs):
            freqs[merged.index(variant)] = freq * (1.0 - share)
        freqs[merged.index(variant_id)] = share
        return Distribution(tuple(merged), freqs, freqs.copy())


class Repertoire:
    """Mapa proměnná → rozdělení s copy-on-write vrstvami.

    Skupiny pocházející z jednoho protojazyka sdílejí zmrazenou základní
    vrstvu a ukládají jen to, v čem se od ní liší (specifikace, Datové
    struktury).
    """

    __slots__ = ("_base", "_own", "_frozen", "_ids", "_by_kind")

    def __init__(self, base: Repertoire | None = None):
        self._base = base
        self._own: dict[str, Distribution] = {}
        self._frozen = False
        self._ids: list[str] | None = None
        self._by_kind: dict[str, list[str]] = {}

    def get(self, variable_id: str) -> Distribution | None:
        layer: Repertoire | None = self
        while layer is not None:
            distribution = layer._own.get(variable_id)
            if distribution is not None:
                return distribution
            layer = layer._base
        return None

    def set(self, variable_id: str, distribution: Distribution) -> None:
        if self._frozen:
            raise RuntimeError("Zmrazený repertoár nelze měnit; použij branch().")
        if self._ids is not None and variable_id not in self._own and self.get(variable_id) is None:
            self._ids = None
            self._by_kind = {}
        self._own[variable_id] = distribution

    def variable_ids(self) -> list[str]:
        """Seřazená ID proměnných; výsledek se drží, dokud nepřibude nová."""
        if self._ids is None:
            ids: set[str] = set()
            layer: Repertoire | None = self
            while layer is not None:
                ids.update(layer._own)
                layer = layer._base
            self._ids = sorted(ids)
        return self._ids

    def variable_ids_of(self, kind: VariableKind) -> list[str]:
        """Seřazená ID proměnných jednoho typu (drží se stejně jako ``variable_ids``)."""
        ids = self.variable_ids()
        cached = self._by_kind.get(kind)
        if cached is None:
            prefix = f"{kind}:"
            cached = self._by_kind[kind] = [item for item in ids if item.startswith(prefix)]
        return cached

    def freeze(self) -> Repertoire:
        self._frozen = True
        return self

    def branch(self) -> Repertoire:
        """Vrátí nezávislého potomka.

        Nezmrazený repertoár nejdřív přesune svůj obsah do nové zmrazené
        vrstvy a dál pokračuje nad ní. Potomek tak vidí přesně dnešní stav a
        pozdější změny rodiče ani potomka se navzájem neovlivní.
        """
        if self._frozen:
            return Repertoire(self)
        snapshot = Repertoire(self._base)
        snapshot._own = self._own
        snapshot._ids = self._ids
        snapshot._by_kind = self._by_kind
        snapshot._frozen = True
        self._base = snapshot
        self._own = {}
        return Repertoire(snapshot)
