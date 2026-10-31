"""Kalibrační konstanty dynamiky jako data světa (milník M7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

#: Pole katalogu gramatických funkcí, která lze přepsat v ``Parameters.grammar``.
GRAMMAR_FIELDS = frozenset({"need", "context", "coverage"})


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
    #: Jakou část potřeby funkce (``need``) uplatní `Expressivity`, když jazyk
    #: funkci nevyjadřuje (``zero``). Tlak podle potřeby je doložený pro obnovu
    #: zeslabeného výrazu (Hopper & Traugott 2003); nová kategorie vzniká hlavně
    #: z častého užívání a expresivních inovací mluvčích (Bybee 2003;
    #: Haspelmath 1999), ne z potřeby. 1,0 = model před M7a (potřeba táhne
    #: i vznik). 0,6 z kalibrace M7a (stacionarita WALS a obrat uvnitř rodiny,
    #: docs/engine-v2/12-kalibrace-m7a.md); tempo je předběžné, dokud ho neurčí
    #: kalibrace z prajazyků.
    emergence_need_scale: float = 0.6
    #: Populace jedné vesnice regionu při relativní hustotě osídlení 1,0
    #: (scénář `region_world`). Autor světa zadává hustotu, ne počty; převod na
    #: velikost populace, která řídí drift, je kalibrační parametr. Výchozí
    #: hodnota odpovídá vesnicím dosavadních scénářů (500).
    population_per_density: float = 500.0
    #: Otevřenost vesnice regionu (`region_world`): podíl vstupu, který děti
    #: dostávají od sousedních vesnic. Síly vazeb se v mixing matrix normalizují,
    #: takže kolik se skupina od sousedů učí, určuje jen otevřenost. Region ji
    #: může přepsat. Výchozí 0,1 jako ostatní scénáře; kalibruje se na nářeční
    #: kontinuum.
    village_openness: float = 0.1
    #: Násobek síly vazby mezi pohraničními vesnicemi sousedních regionů proti
    #: gravitační síle (`region_world`). Určuje, jakou část vstupu pohraniční
    #: vesnice dostává přes hranici, tedy propustnost hranice.
    border_link_scale: float = 1.0
    #: Kolikrát častěji navrhují vypuštění výrazu L2 mluvčí; stejně jako
    #: u analogie (změna `CategoryLoss`).
    category_loss_l2_boost: float = 4.0
    #: Kolikrát častěji navrhují regularizaci (analogii) L2 mluvčí: přehnané
    #: zobecnění. Autorský odhad.
    analogy_l2_boost: float = 4.0
    #: Váha trestu `Clarity` za podíl slov zkrácených pod mez.
    clarity_short_factor: float = 1.5
    #: Váha odměny `Dispersion` za zaplnění mezery v soustavě vokálů.
    dispersion_factor: float = 4.0
    #: Jak velkou část vstupu L2 kódu tvoří první jazyk jeho mluvčích, když se
    #: ho učí všichni až v dospělosti (``l2_share`` = 1).
    interference_weight: float = 0.5
    #: O kolik školní výuka (opravování podle normy) interferenci tlumí: kdo se
    #: kód učí ve škole, nese do něj svůj první jazyk méně než kdo na ulici.
    school_correction: float = 0.8
    #: Abrams & Strogatz (2003): rychlost přechodu je úměrná statusu cílového
    #: jazyka a podílu jeho mluvčích na ``shift_exponent``.
    shift_rate: float = 1.0
    shift_exponent: float = 1.31
    #: Pod tímto podílem užívání v komunitě se kód nepředává dětem (iterace 4).
    child_threshold: float = 0.2
    #: Jak velkou část vstupu gramotného mluvčího tvoří psaný kód (jen slova).
    reading_weight: float = 0.1
    #: Jak velkou část vstupu dětí při plné školní docházce tvoří psaný kód.
    #: Škola učí slova, tvary a konstrukce; výslovnost si děti nesou z domova a
    #: podle písma se mění jen výjimečně (výslovnost podle pravopisu).
    school_weight: float = 0.3
    #: Jak velkou část vstupu věřícího tvoří liturgický kód (jen slova).
    liturgy_weight: float = 0.1
    #: Nad tímto podílem se nová koncovka zapíše do tvarů slov.
    grammar_threshold: float = 0.85
    #: Lexémy aspoň tak časté si při nástupu nové koncovky drží starý tvar.
    conserved_frequency: float = 0.7
    #: Nad tímto podílem si nová generace analogický tvar zapíše.
    analogy_threshold: float = 0.85
    #: Nad tímto p_slovo si nová generace slovo přepíše.
    restructure_threshold: float = 0.85
    #: Rozptyl sklonu jednotlivých slov; určuje podíl reliktních výjimek.
    word_bias_sd: float = 1.5
    #: Jak silně frekvence předbíhá u redukčních změn (Bybee).
    frequency_lead: float = 1.0
    #: Po kolika generacích na 100 % proces přestane být živý.
    closure_generations: float = 2.0
    #: Od jakého podílu ve skupině začne proces působit na slova. Většina
    #: inovací zanikne dřív, a nemusí se proto ani zařazovat do front.
    activation_share: float = 0.05
    #: Splynutí dvou buněk téhož paradigmatu (synkretismus) stojí stejně jako
    #: náhodný homofon; tvary téhož slova od sebe často odliší kontext.
    paradigm_merge_weight: float = 1.0
    #: Splynutí buňky s jiným tvarem téhož slova, když roli její funkce už nese
    #: jiná konstrukce (pád vedle pevného slovosledu): funkce je nadbytečná a její
    #: ztráta skoro nic nestojí.
    redundant_merge_weight: float = 0.3
    #: Přepisy vah tlaků podle jejich ``name`` (např. ``{"clarity": 2.0}``);
    #: platí pro všechny typy proměnných, kde tlak působí. Prázdné = tabulky
    #: jednotlivých změn beze změny. Neznámý tlak odmítne ``pressures_by_kind``.
    pressure_weights: Mapping[str, float] = field(default_factory=FrozenMapping)
    #: Násobky tempa inovací podle ``kind`` změny (např. ``{"periphrasis": 0.5}``);
    #: násobí očekávaný počet inovací. Prázdné = tempa změn beze změny. Neznámou
    #: změnu odmítne simulace.
    change_rates: Mapping[str, float] = field(default_factory=FrozenMapping)
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
        object.__setattr__(self, "pressure_weights", FrozenMapping(self.pressure_weights))
        object.__setattr__(self, "change_rates", FrozenMapping(self.change_rates))
