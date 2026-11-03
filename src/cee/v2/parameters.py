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
    #: může přepsat. 0,5 z kalibrace nářečního kontinua (pásmo atlasů, jeden
    #: jazyk na 80 km, pořadí vzdáleností; docs/engine-v2/14-kalibrace-kontinua.md);
    #: od 0,35 výš zůstane jeden jazyk, při 0,1 se 80 km rozpadne na čtyři jazyky.
    #: Ostatní scénáře (`village_grid`) mají dál vlastní 0,1.
    village_openness: float = 0.5
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
    #: Výměna slov (``pressures.lexical.Entrenchment`` a ``Motivation``):
    #: převládající varianta pojmu má výhodu ``entrenchment_base`` +
    #: ``entrenchment_strength`` × frekvence ** ``entrenchment_frequency_exponent``,
    #: nové slovo výhodu podle druhu (odvozenina +0,15, nový kořen −0,15…)
    #: plus náhodnou přitažlivost ~ N(0, ``lexical_appeal_sd``), stálou pro
    #: variantu (expresivita, módnost, sociální hodnota slova). Bez
    #: přitažlivosti nové slovo vyhraje buď vždycky, nebo nikdy, a výměna je
    #: prahová (polovina pojmů se nemění vůbec, častá slova se vyměňují
    #: rychlostí 0,26 ostatních). Kalibrace 2026-11-02
    #: (``scripts/v2_calibrate_frequency.py``, ``v2_calibrate_retention.py``):
    #: přitažlivost 0,03 dává poměr rychlostí horních 30 % pojmů podle
    #: frekvence 0,44 (Pagel a kol. 2007: 0,70) a retenci jádra 0,785 / 0,827
    #: po tisíciletích (glotochronologie 0,81–0,86); širší přitažlivost se
    #: blíží poměru z dat, ale retence klesá (0,05: 0,68 a 0,72), základní
    #: ochrana (``entrenchment_base``) potlačí dělení jazyků a výpůjčky.
    #: Viz ``docs/engine-v2/19-pojmy.md``.
    entrenchment_strength: float = 0.3
    entrenchment_frequency_exponent: float = 1.0
    entrenchment_base: float = 0.0
    lexical_appeal_sd: float = 0.03
    #: Souběžná variabilita slovní zásoby protojazyka (``cee.v2.variation``):
    #: násobek naměřené hustoty menšinových variant (0 = protojazyk bez
    #: variability) a nejvyšší součet jejich podílů u pojmu ve vesnici, aby
    #: slovo autora zůstalo převládající.
    standing_variation: float = 1.0
    variation_cap: float = 0.4
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
    #: Jak moc čtení šetří častá slova: vliv psaného kódu na pojem je
    #: ``1 − reading_core_resistance · frekvence pojmu``. 1 = jako liturgie
    #: (učená slova bývají vzácná, základní slovní zásoba se čtením vrací
    #: málo; arabské dialekty si drží vlastní základní slova), 0 = čtení
    #: vrací všechna slova stejně. Rovnováha mluvené a psané řeči se liší
    #: svět od světa; autor ji ladí tímto a ``reading_weight``.
    reading_core_resistance: float = 1.0
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
    #: --- státy, jazyková politika a lingua franca (``cee.v2.polity``) ---
    #: Autor zadává slovní úrovně (``"strong"``, ``"enforced"``…); tyto tabulky je
    #: převádějí na čísla. Všechny hodnoty jsou autorské odhady, které se kalibrují
    #: (tempo přechodu asi tři generace, Fishman 1991; přežití jazyků v odlehlých
    #: a odlišných regionech), viz docs/engine-v2/15-staty-lingua-franca.md.
    #:
    #: Kolikrát vyšší prestiž mají vesnice hlavního města. Prestiž řídí, od koho
    #: se děti učí (``mixing_matrix``), i status jazyka při přechodu.
    capital_prestige: float = 2.0
    #: Síla vazby vesnice k sídlu státu při centralizaci ``"moderate"`` a nulové
    #: vzdálenosti (úřady, trh, vojsko, cesty). Klesá s ``exp(-d / capital_reach)``.
    capital_link_strength: float = 0.3
    capital_reach: float = 150.0
    centralization_levels: Mapping[str, float] = field(default_factory=lambda: FrozenMapping({
        "none": 0.0, "weak": 0.5, "moderate": 1.0, "strong": 2.0,
    }))
    #: Jazyková politika vůči regionům jiného jazyka: ``share`` = podíl dospělých,
    #: kteří úřední jazyk užívají mimo domov (veřejná doména), ``pull`` = jak silně
    #: ho tlačí i domů (škola v úředním jazyce, úřady, smíšená manželství).
    #: ``tolerant`` nechá stabilní dvojjazyčnost (diglosie, Fishman 1967).
    policy_levels: Mapping[str, Mapping[str, float]] = field(default_factory=lambda: FrozenMapping({
        "tolerant": {"share": 0.1, "pull": 0.0},
        "promoted": {"share": 0.3, "pull": 0.1},
        "enforced": {"share": 0.6, "pull": 1.0},
    }))
    #: Podíl dospělých, kteří se lingua francou domluví mimo domov.
    lingua_franca_levels: Mapping[str, float] = field(default_factory=lambda: FrozenMapping({
        "rare": 0.1, "common": 0.3, "universal": 0.6,
    }))
    #: Síla vazby mluvčích lingua franca k jejímu zdroji (obchodní město).
    lingua_franca_link: float = 0.3
    #: Tlak lingua franca domů, když ji autor nechá zdomácnět (``nativize``).
    lingua_franca_pull: float = 0.1
    #: Obrození (``polity.Revival``): ``pace`` = tempo návratu rodin k jazyku
    #: (obousměrný přechod), ``seed`` = podíl lidí, kteří se vymřelý nebo v obci
    #: ztracený jazyk znovu naučí (noví mluvčí, hebrejština, kornština).
    revival_levels: Mapping[str, Mapping[str, float]] = field(default_factory=lambda: FrozenMapping({
        "movement": {"pace": 0.3, "seed": 0.02},
        "national": {"pace": 1.0, "seed": 0.05},
    }))
    #: Propustnost hranice státu (``State(border=...)``): násobek vazeb mezi
    #: regiony různých států. Hranice vznikne sama tam, kde sousedí regiony
    #: různých států, a působí hned; rozcházení podél ní dělají odlišná centra
    #: a normy. Přes hranici dvou států platí méně propustná z obou.
    border_levels: Mapping[str, float] = field(default_factory=lambda: FrozenMapping({
        "open": 1.0, "normal": 0.5, "closed": 0.1,
    }))
    #: Pozadí dějin (``cee.v2.background``): míra drobných událostí, které svět
    #: generuje sám vedle událostí autora. Násobí ``background_rates``.
    background_levels: Mapping[str, float] = field(default_factory=lambda: FrozenMapping({
        "none": 0.0, "calm": 0.3, "normal": 1.0, "turbulent": 2.5,
    }))
    #: Kolikrát za století v jednom kraji nastane událost pozadí při míře
    #: ``normal``: mor, přesídlení části lidí k sousedům, vzestup obchodní cesty
    #: k sousednímu kraji, změna prestiže kraje, cizí elita od souseda jiného
    #: jazyka. Autorský odhad, kalibruje se v M7 (retence slovní zásoby).
    #: Rozsahy náhodných veličin pozadí dějin (rovnoměrně mezi mezemi): podíl
    #: zemřelých při moru, podíl přesídlených, násobek obchodu a prestiže a
    #: doby v krocích po 25 letech (obnova po moru, trvání obchodní cesty,
    #: splynutí cizí elity s místními).
    background_spans: Mapping[str, Mapping[str, float]] = field(default_factory=lambda: FrozenMapping({
        name: {"low": low, "high": high} for name, (low, high) in {
            "plague_mortality": (0.15, 0.4), "recovery_steps": (2, 4), "resettlement_share": (0.05, 0.15),
            "trade_factor": (1.5, 3.0), "trade_steps": (4, 12), "prestige_factor": (0.7, 1.4),
            "elite_steps": (4, 12),
        }.items()
    }))
    #: Cizí elita z pozadí dějin (``background.ForeignElite``): prestiž elity,
    #: síla její vazby ke každé poddané vesnici a podíl obyvatel sídla. Síla
    #: vazby kalibrovaná na svět dvou jazyků s pozadím ``normal``
    #: (``docs/engine-v2/17-pozadi-dejin.md``): 0,1 dá retenci 88 % za
    #: tisíciletí a výpůjčky v základním slovníku 13 % za 3 000 let; dřívějších
    #: 0,5 (jako ``events.Conquest``) dávalo 77 % a 25 %.
    background_elite_prestige: float = 2.0
    background_elite_link: float = 0.1
    background_elite_share: float = 0.1
    background_rates: Mapping[str, float] = field(default_factory=lambda: FrozenMapping({
        "plague": 0.08, "resettlement": 0.12, "trade": 0.12, "prestige": 0.08, "foreign_elite": 0.02,
    }))
    #: Spisovný jazyk (``polity.Standard``, ``polity.Schools``): podíl gramotných
    #: při kodifikaci a podíl dětí ve škole podle úrovně; násobí se dosahem centra.
    literacy_levels: Mapping[str, float] = field(default_factory=lambda: FrozenMapping({
        "elite": 0.05, "towns": 0.2, "mass": 0.8,
    }))
    schooling_levels: Mapping[str, float] = field(default_factory=lambda: FrozenMapping({
        "towns": 0.3, "mass": 0.8,
    }))
    #: Kolikrát vyšší prestiž dostanou mluvčí jazyka, který má vlastní spisovnou
    #: normu (literatura, úřady, škola): vlastní norma brzdí přechod na jiný
    #: jazyk (čeština, finština, katalánština). Autorský odhad.
    standard_prestige: float = 1.5
    #: Dostupnost regionu podle terénu: násobí vazby přes hranici regionu, vazbu
    #: k sídlu státu i dosah jazykové politiky. Hory a ostrovy izolují.
    terrain_access: Mapping[str, float] = field(default_factory=lambda: FrozenMapping({
        "plain": 1.0, "hills": 0.6, "mountains": 0.3, "island": 0.2,
    }))
    #: Loajalita k jazyku podle odlišnosti regionu (etnikum, náboženství, vlastní
    #: historie): zpomalí přechod na jiný jazyk i jeho pronikání domů.
    identity_loyalty: Mapping[str, float] = field(default_factory=lambda: FrozenMapping({
        "shared": 0.0, "distinct": 0.5, "strong": 0.8,
    }))
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
        object.__setattr__(self, "background_rates", FrozenMapping(self.background_rates))
        object.__setattr__(self, "background_spans", FrozenMapping(self.background_spans))
        for name in LEVEL_TABLES:
            object.__setattr__(self, name, FrozenMapping(getattr(self, name)))


#: Tabulky slovních úrovní (``Parameters``), které autor světa zadává jménem.
LEVEL_TABLES = (
    "centralization_levels", "policy_levels", "lingua_franca_levels", "terrain_access", "identity_loyalty",
    "literacy_levels", "schooling_levels", "border_levels", "revival_levels", "background_levels",
)


def level(table: Mapping[str, Any], name: str, what: str) -> Any:
    """Hodnota slovní úrovně ``name``; neznámou odmítne s výčtem možností."""
    if name not in table:
        raise ValueError(f"Neznámá {what} '{name}'; možnosti: {', '.join(sorted(table))}.")
    return table[name]
