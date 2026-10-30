"""Kalibrační konstanty dynamiky jako data světa (milník M7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

#: Pole katalogu gramatických funkcí, která lze přepsat v ``Parameters.grammar``.
GRAMMAR_FIELDS = frozenset({"need", "context"})


class FrozenMapping(Mapping[str, Any]):
    """Neměnné, hashovatelné mapování (řazené podle klíče), aby ``Parameters`` zůstaly hashovatelné."""

    __slots__ = ("_items", "_hash")
    _items: tuple[tuple[str, Any], ...]
    _hash: int

    def __init__(self, items: Mapping[str, Any] | None = None) -> None:
        pairs = tuple(sorted(
            (str(key), value if isinstance(value, FrozenMapping) else
             FrozenMapping(value) if isinstance(value, Mapping) else float(value))
            for key, value in (items or {}).items()
        ))
        object.__setattr__(self, "_items", pairs)
        object.__setattr__(self, "_hash", hash(pairs))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("FrozenMapping je neměnné.")

    def __getitem__(self, key: str) -> Any:
        for name, value in self._items:
            if name == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (name for name, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __hash__(self) -> int:
        return self._hash

    def __repr__(self) -> str:
        return f"FrozenMapping({dict(self._items)!r})"

    def __reduce__(self) -> tuple[object, ...]:
        return (FrozenMapping, (dict(self._items),))


@dataclass(frozen=True)
class Parameters:
    """Kalibrační konstanty dynamiky jazyka; patří světu, ne modulu.

    Výchozí hodnoty jsou dosavadní konstanty; kalibrují se v M7. Každý svět
    má vlastní sadu, takže se v jednom procesu dá spustit mnoho světů
    s různými hodnotami.
    """

    #: Jak silně zvýhodňuje funkční zátěž zachování kontrastu. Je to sklon, ne
    #: zákaz (Wedel a kol. 2013): eroze pádových koncovek se v reálných jazycích
    #: děje i přes splynutí tvarů (latinské koncové -m).
    functional_load_scale: float = 5.0
    #: Násobek úspory artikulace pro redukční procesy v nepřízvučných slabikách
    #: u jazyků se silným přízvukem (stress-timed).
    #:
    #: Literatura podporuje směr (silnější redukce a afixální komprese v nepřízvučné
    #: pozici: Dauer 1983; Bybee, Chakraborti, Jung & Scheibman 1998 „Prosody and
    #: segmental effect: Some paths of evolution for word stress“, Studies in
    #: Language 22; Schiering 2010), hodnota 1,5 je autorský odhad (neladěno na WALS).
    stress_strength_multiplier: float = 1.5
    #: Autorský odhad míry tolerance nové kody podle stávající stavby slabik jazyka
    #: (WALS 12A, Maddieson: jazyky s povolenou kodou netrestají vznik uzavřené slabiky
    #: absolutně jako jazyky s čistě otevřenými slabikami).
    #: 0.0 = výchozí model bez tolerance (kalibrace v M7); 1.0 = plná tolerance kod.
    coda_tolerance_scale: float = 0.0
    #: Autorský odhad: stejná síla jako `Teachability` u tvarů. Literatura
    #: podporuje směr, ne velikost.
    learnability_strength: float = 1.0
    #: Cena každého slova navíc, které konstrukce přidává (tlak `Economy`).
    economy_word_cost: float = 0.15
    #: Výhoda konstrukce o stupeň dál na škále gramatikalizace (tlak `Fusion`).
    fusion_bonus: float = 0.25
    #: Nepatrná cena pevného slovosledu, dokud pád drží roli (tlak `Ambiguity`).
    order_rigidity: float = 0.05
    #: Kolikrát častěji navrhují vypuštění výrazu L2 mluvčí; stejně jako
    #: u analogie (změna `CategoryLoss`).
    category_loss_l2_boost: float = 4.0
    #: Přepisy polí ``need`` a ``context`` katalogu gramatických funkcí podle
    #: funkce, např. ``{"DEFINITE": {"context": 0.4}}``. Prázdné = katalog
    #: ``v2_grammar.yaml`` beze změny.
    grammar: Mapping[str, Mapping[str, float]] = field(default_factory=FrozenMapping)

    def __post_init__(self) -> None:
        grammar = FrozenMapping(self.grammar)
        for function, fields in grammar.items():
            unknown = set(fields) - GRAMMAR_FIELDS
            if unknown:
                raise ValueError(
                    f"Funkci '{function}' lze přepsat jen v polích {sorted(GRAMMAR_FIELDS)}, "
                    f"ne {sorted(unknown)}."
                )
        object.__setattr__(self, "grammar", grammar)
