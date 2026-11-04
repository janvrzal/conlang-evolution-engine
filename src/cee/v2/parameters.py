"""Kalibrační konstanty dynamiky jako data světa (milník M7)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping

#: Pole katalogu gramatických funkcí, která lze přepsat v ``Parameters.grammar``.
GRAMMAR_FIELDS = frozenset({"need", "context", "coverage"})
#: Domény slov (``concept_data.DOMAINS``) a kanály, kterými slova přicházejí z jiného
#: kódu (``Parameters.channel_domains``): obecný kontakt sousedů, cizí elita, obchod,
#: liturgie, čtení a škola.
DOMAINS = ("core", "learned", "culture", "religion", "power")
CHANNELS = ("neighbor", "elite", "trade", "liturgy", "reading", "school")
#: Neutrální váhy domén: všechny kanály propouštějí všechny domény stejně, jako
#: před zavedením domén (spolu s ``borrowability_strength`` 0 dá dřívější výsledky).
NEUTRAL_CHANNEL_DOMAINS: Mapping[str, Mapping[str, float]] = {
    channel: {domain: 1.0 for domain in DOMAINS} for channel in CHANNELS
}


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


#: Soubor metaparametrů: jediný zdroj výchozích hodnot, druhů, popisů, skupin pro UI a mezí
#: (čte ho i Rust). Formát: ``docs/engine-v2/19-engine-v-rustu.md``, oddíl „Metaparametry“.
PARAMETERS_FILE = Path(__file__).resolve().parents[1] / "data" / "v2_parameters.json"
#: Druhy parametrů v souboru; ``level_table`` a ``level_table2`` jsou slovní úrovně.
KINDS = ("number", "table", "table2", "level_table", "level_table2")


def _load() -> dict[str, Any]:
    return json.loads(PARAMETERS_FILE.read_text(encoding="utf-8"))


#: Obsah ``v2_parameters.json`` (``format``, ``groups``, ``parameters``).
SPECS: dict[str, Any] = _load()
#: Popis parametru podle jména.
SPEC_BY_NAME: dict[str, dict[str, Any]] = {item["name"]: item for item in SPECS["parameters"]}


def _number(name: str) -> float:
    return float(SPEC_BY_NAME[name]["default"])


def _table(name: str) -> Any:
    """Výchozí tabulka parametru ze souboru (neměnná kopie)."""
    return FrozenMapping(SPEC_BY_NAME[name]["default"])


def parameter_schema() -> dict[str, Any]:
    """Parametry pro UI: skupiny a seznam parametrů s výchozí hodnotou, druhem, popisem,
    skupinou, mezemi a (u slovních úrovní) výčtem úrovní."""
    items = []
    for item in SPECS["parameters"]:
        out = dict(item)
        if item["kind"] in {"level_table", "level_table2"}:
            out["levels"] = sorted(item["default"])
        items.append(out)
    return {"groups": SPECS["groups"], "items": items}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_override(name: str, value: Any) -> list[tuple[str, str]]:
    """Chyby přepisu parametru ``name`` podle souboru: dvojice (cesta, zpráva).

    Cesta je ``parameters.<jméno>`` a u tabulek pokračuje klíči. Kontroluje jméno,
    druh a meze, které soubor uvádí (``keys``, ``inner_keys``, ``min``, ``max``).
    """
    path = f"parameters.{name}"
    spec = SPEC_BY_NAME.get(name)
    if spec is None:
        return [(path, "neznámý parametr")]
    kind = spec["kind"]
    lo, hi = spec.get("min"), spec.get("max")

    def number(where: str, item: Any) -> list[tuple[str, str]]:
        if not _is_number(item):
            return [(where, "očekáváno číslo")]
        if lo is not None and item < lo:
            return [(where, f"nesmí být menší než {lo}")]
        if hi is not None and item > hi:
            return [(where, f"nesmí být větší než {hi}")]
        return []

    def names(where: str, table: Mapping[str, Any], allowed: list[str] | None) -> list[tuple[str, str]]:
        if allowed is None:
            return []
        return [
            (f"{where}.{key}", f"neznámé jméno; možnosti: {', '.join(allowed)}")
            for key in sorted(set(table) - set(allowed))
        ]

    if kind == "number":
        return number(path, value)
    if not isinstance(value, Mapping):
        what = "jméno → číslo" if kind in {"table", "level_table"} else "jméno → jméno → číslo"
        return [(path, f"očekávána tabulka {what}")]
    issues = names(path, value, spec.get("keys"))
    for key, item in value.items():
        where = f"{path}.{key}"
        if kind in {"table", "level_table"}:
            issues += number(where, item)
        elif not isinstance(item, Mapping):
            issues.append((where, "očekávána tabulka jméno → číslo"))
        else:
            issues += names(where, item, spec.get("inner_keys"))
            for inner, number_item in item.items():
                issues += number(f"{where}.{inner}", number_item)
    return issues


#: Výchozí váhy domén v kanálech (kalibrace proti WOLD v ``19-pojmy.md``) ze souboru:
#: každý kanál zvýhodní doménu, kterou ve skutečnosti přináší; ostatní domény prochází beze změny.
DEFAULT_CHANNEL_DOMAINS: Mapping[str, Mapping[str, float]] = SPEC_BY_NAME["channel_domains"]["default"]


def _channel_domains(weights: Mapping[str, Mapping[str, float]] | None) -> FrozenMapping:
    """Tabulka kanál → doména → váha: chybějící položky z výchozích, neznámé názvy chyba."""
    given = {} if weights is None else dict(weights)
    unknown = sorted(set(given) - set(CHANNELS))
    if unknown:
        raise ValueError(f"Neznámý kanál {unknown}; možnosti: {', '.join(CHANNELS)}.")
    merged: dict[str, dict[str, float]] = {}
    for channel in CHANNELS:
        row = dict(DEFAULT_CHANNEL_DOMAINS[channel])
        extra = dict(given.get(channel, {}))
        bad = sorted(set(extra) - set(DOMAINS))
        if bad:
            raise ValueError(f"Neznámá doména {bad} v kanálu '{channel}'; možnosti: {', '.join(DOMAINS)}.")
        row.update({domain: float(value) for domain, value in extra.items()})
        negative = sorted(domain for domain, value in row.items() if value < 0.0)
        if negative:
            raise ValueError(f"Váha domény {negative} v kanálu '{channel}' nesmí být záporná.")
        merged[channel] = row
    return FrozenMapping(merged)


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
    functional_load_scale: float = _number("functional_load_scale")
    #: Násobek úspory artikulace pro redukční procesy v nepřízvučných slabikách
    #: u jazyků se silným přízvukem (stress-timed).
    #:
    #: Literatura podporuje směr (silnější redukce a afixální komprese v nepřízvučné
    #: pozici: Dauer 1983; Bybee, Chakraborti, Jung & Scheibman 1998 „Prosody and
    #: segmental effect: Some paths of evolution for word stress“, Studies in
    #: Language 22; Schiering 2010), hodnota 1,5 je autorský odhad (neladěno na WALS).
    stress_strength_multiplier: float = _number("stress_strength_multiplier")
    #: Autorský odhad míry tolerance nové kody podle stávající stavby slabik jazyka
    #: (WALS 12A, Maddieson: jazyky s povolenou kodou netrestají vznik uzavřené slabiky
    #: absolutně jako jazyky s čistě otevřenými slabikami).
    #: 0.0 = výchozí model bez tolerance (kalibrace v M7); 1.0 = plná tolerance kod.
    coda_tolerance_scale: float = _number("coda_tolerance_scale")
    #: Autorský odhad: stejná síla jako `Teachability` u tvarů. Literatura
    #: podporuje směr, ne velikost.
    learnability_strength: float = _number("learnability_strength")
    #: Cena každého slova navíc, které konstrukce přidává (tlak `Economy`).
    economy_word_cost: float = _number("economy_word_cost")
    #: Výhoda konstrukce o stupeň dál na škále gramatikalizace (tlak `Fusion`).
    fusion_bonus: float = _number("fusion_bonus")
    #: Nepatrná cena pevného slovosledu, dokud pád drží roli (tlak `Ambiguity`).
    order_rigidity: float = _number("order_rigidity")
    #: Jakou část potřeby funkce (``need``) uplatní `Expressivity`, když jazyk
    #: funkci nevyjadřuje (``zero``). Tlak podle potřeby je doložený pro obnovu
    #: zeslabeného výrazu (Hopper & Traugott 2003); nová kategorie vzniká hlavně
    #: z častého užívání a expresivních inovací mluvčích (Bybee 2003;
    #: Haspelmath 1999), ne z potřeby. 1,0 = model před M7a (potřeba táhne
    #: i vznik). 0,6 z kalibrace M7a (stacionarita WALS a obrat uvnitř rodiny,
    #: docs/engine-v2/12-kalibrace-m7a.md); tempo je předběžné, dokud ho neurčí
    #: kalibrace z prajazyků.
    emergence_need_scale: float = _number("emergence_need_scale")
    #: Populace jedné vesnice regionu při relativní hustotě osídlení 1,0
    #: (scénář `region_world`). Autor světa zadává hustotu, ne počty; převod na
    #: velikost populace, která řídí drift, je kalibrační parametr. Výchozí
    #: hodnota odpovídá vesnicím dosavadních scénářů (500).
    population_per_density: float = _number("population_per_density")
    #: Otevřenost vesnice regionu (`region_world`): podíl vstupu, který děti
    #: dostávají od sousedních vesnic. Síly vazeb se v mixing matrix normalizují,
    #: takže kolik se skupina od sousedů učí, určuje jen otevřenost. Region ji
    #: může přepsat. 0,5 z kalibrace nářečního kontinua (pásmo atlasů, jeden
    #: jazyk na 80 km, pořadí vzdáleností; docs/engine-v2/14-kalibrace-kontinua.md);
    #: od 0,35 výš zůstane jeden jazyk, při 0,1 se 80 km rozpadne na čtyři jazyky.
    #: Ostatní scénáře (`village_grid`) mají dál vlastní 0,1.
    village_openness: float = _number("village_openness")
    #: Násobek síly vazby mezi pohraničními vesnicemi sousedních regionů proti
    #: gravitační síle (`region_world`). Určuje, jakou část vstupu pohraniční
    #: vesnice dostává přes hranici, tedy propustnost hranice.
    border_link_scale: float = _number("border_link_scale")
    #: Kolikrát častěji navrhují vypuštění výrazu L2 mluvčí; stejně jako
    #: u analogie (změna `CategoryLoss`).
    category_loss_l2_boost: float = _number("category_loss_l2_boost")
    #: Kolikrát častěji navrhují regularizaci (analogii) L2 mluvčí: přehnané
    #: zobecnění. Autorský odhad.
    analogy_l2_boost: float = _number("analogy_l2_boost")
    #: Váha trestu `Clarity` za podíl slov zkrácených pod mez.
    clarity_short_factor: float = _number("clarity_short_factor")
    #: Váha odměny `Dispersion` za zaplnění mezery v soustavě vokálů.
    dispersion_factor: float = _number("dispersion_factor")
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
    entrenchment_strength: float = _number("entrenchment_strength")
    entrenchment_frequency_exponent: float = _number("entrenchment_frequency_exponent")
    entrenchment_base: float = _number("entrenchment_base")
    lexical_appeal_sd: float = _number("lexical_appeal_sd")
    #: Souběžná variabilita slovní zásoby protojazyka (``cee.v2.variation``):
    #: násobek naměřené hustoty menšinových variant (0 = protojazyk bez
    #: variability) a nejvyšší součet jejich podílů u pojmu ve vesnici, aby
    #: slovo autora zůstalo převládající.
    standing_variation: float = _number("standing_variation")
    variation_cap: float = _number("variation_cap")
    #: Jak velkou část vstupu L2 kódu tvoří první jazyk jeho mluvčích, když se
    #: ho učí všichni až v dospělosti (``l2_share`` = 1).
    interference_weight: float = _number("interference_weight")
    #: O kolik školní výuka (opravování podle normy) interferenci tlumí: kdo se
    #: kód učí ve škole, nese do něj svůj první jazyk méně než kdo na ulici.
    school_correction: float = _number("school_correction")
    #: Abrams & Strogatz (2003): rychlost přechodu je úměrná statusu cílového
    #: jazyka a podílu jeho mluvčích na ``shift_exponent``.
    shift_rate: float = _number("shift_rate")
    shift_exponent: float = _number("shift_exponent")
    #: Pod tímto podílem užívání v komunitě se kód nepředává dětem (iterace 4).
    child_threshold: float = _number("child_threshold")
    #: Jak velkou část vstupu gramotného mluvčího tvoří psaný kód (jen slova).
    reading_weight: float = _number("reading_weight")
    #: Jak moc čtení šetří častá slova: vliv psaného kódu na pojem je
    #: ``1 − reading_core_resistance · frekvence pojmu``. 1 = jako liturgie
    #: (učená slova bývají vzácná, základní slovní zásoba se čtením vrací
    #: málo; arabské dialekty si drží vlastní základní slova), 0 = čtení
    #: vrací všechna slova stejně. Rovnováha mluvené a psané řeči se liší
    #: svět od světa; autor ji ladí tímto a ``reading_weight``.
    reading_core_resistance: float = _number("reading_core_resistance")
    #: Jak velkou část vstupu dětí při plné školní docházce tvoří psaný kód.
    #: Škola učí slova, tvary a konstrukce; výslovnost si děti nesou z domova a
    #: podle písma se mění jen výjimečně (výslovnost podle pravopisu).
    school_weight: float = _number("school_weight")
    #: Jak velkou část vstupu věřícího tvoří liturgický kód (jen slova).
    liturgy_weight: float = _number("liturgy_weight")
    #: Domény slov v kanálech (``cee.v2.contact``, ``cee.v2.institutions``). Slovo
    #: přes hranici jazyka projde s váhou kanálu (kontakt sousedů, liturgie,
    #: čtení, škola) × váha jeho domény v tomto kanálu. Doména pojmu je z WOLD
    #: (``core``, ``learned``, ``culture``, ``religion``, ``power``; vlastní pojem
    #: autora má zadanou nebo ``core``). Kanály: ``neighbor`` (obecný kontakt,
    #: vazby mezi jazyky), ``elite`` (zdroj je cizí elita, ``Conquest``,
    #: ``ForeignElite``), ``trade`` (podíl vazby, který přinesla obchodní cesta:
    #: ``TradeShift``, ``Contact(trade=True)``), ``liturgy`` (``ReligiousChange``),
    #: ``reading`` a ``school`` (psaný kód). Váha 1 = beze změny proti kanálu
    #: bez domén, váha nad 1 slova domény zvýhodní (kanál není dál filtr nejvýš
    #: 1, ale podíl vstupu se u čtení, školy a liturgie ořízne na 1). Zadat
    #: stačí změněné položky, ostatní zůstanou výchozí (``NEUTRAL_CHANNEL_DOMAINS``
    #: vrátí model beze domén). Kalibrace a data: ``docs/engine-v2/19-pojmy.md``.
    channel_domains: Mapping[str, Mapping[str, float]] = field(default_factory=lambda: _table("channel_domains"))
    #: Jak silně půjčitelnost pojmu z WOLD (``concept_data.borrowed``, u vlastního
    #: pojmu hodnota autora nebo výchozí) řídí přenos slov vazbami mezi jazyky
    #: (kontakt sousedů, elita, obchod, výpůjčky); liturgie ani čtení ji nepoužívají.
    #: Váha slova je ``(1 − frekvence) ** max(0, 1 − s) · (půjčitelnost / průměr) ** s``,
    #: přepočtená tak, aby měla přes výchozích 149 pojmů stejný průměr jako
    #: ``1 − frekvence``, takže ``s`` nemění průměrnou míru výpůjček, jen které pojmy se půjčují. 0 = jen frekvence jako
    #: dřív, 1 = jen půjčitelnost, nad 1 jsou rozdíly mezi pojmy zvýrazněné.
    borrowability_strength: float = _number("borrowability_strength")
    #: Nad tímto podílem se nová koncovka zapíše do tvarů slov.
    grammar_threshold: float = _number("grammar_threshold")
    #: Lexémy aspoň tak časté si při nástupu nové koncovky drží starý tvar.
    conserved_frequency: float = _number("conserved_frequency")
    #: Nad tímto podílem si nová generace analogický tvar zapíše.
    analogy_threshold: float = _number("analogy_threshold")
    #: Nad tímto p_slovo si nová generace slovo přepíše.
    restructure_threshold: float = _number("restructure_threshold")
    #: Rozptyl sklonu jednotlivých slov; určuje podíl reliktních výjimek.
    word_bias_sd: float = _number("word_bias_sd")
    #: Jak silně frekvence předbíhá u redukčních změn (Bybee).
    frequency_lead: float = _number("frequency_lead")
    #: Po kolika generacích na 100 % proces přestane být živý.
    closure_generations: float = _number("closure_generations")
    #: Od jakého podílu ve skupině začne proces působit na slova. Většina
    #: inovací zanikne dřív, a nemusí se proto ani zařazovat do front.
    activation_share: float = _number("activation_share")
    #: Splynutí dvou buněk téhož paradigmatu (synkretismus) stojí stejně jako
    #: náhodný homofon; tvary téhož slova od sebe často odliší kontext.
    paradigm_merge_weight: float = _number("paradigm_merge_weight")
    #: Splynutí buňky s jiným tvarem téhož slova, když roli její funkce už nese
    #: jiná konstrukce (pád vedle pevného slovosledu): funkce je nadbytečná a její
    #: ztráta skoro nic nestojí.
    redundant_merge_weight: float = _number("redundant_merge_weight")
    #: --- státy, jazyková politika a lingua franca (``cee.v2.polity``) ---
    #: Autor zadává slovní úrovně (``"strong"``, ``"enforced"``…); tyto tabulky je
    #: převádějí na čísla. Všechny hodnoty jsou autorské odhady, které se kalibrují
    #: (tempo přechodu asi tři generace, Fishman 1991; přežití jazyků v odlehlých
    #: a odlišných regionech), viz docs/engine-v2/15-staty-lingua-franca.md.
    #:
    #: Kolikrát vyšší prestiž mají vesnice hlavního města. Prestiž řídí, od koho
    #: se děti učí (``mixing_matrix``), i status jazyka při přechodu.
    capital_prestige: float = _number("capital_prestige")
    #: Síla vazby vesnice k sídlu státu při centralizaci ``"moderate"`` a nulové
    #: vzdálenosti (úřady, trh, vojsko, cesty). Klesá s ``exp(-d / capital_reach)``.
    capital_link_strength: float = _number("capital_link_strength")
    capital_reach: float = _number("capital_reach")
    centralization_levels: Mapping[str, float] = field(default_factory=lambda: _table("centralization_levels"))
    #: Jazyková politika vůči regionům jiného jazyka: ``share`` = podíl dospělých,
    #: kteří úřední jazyk užívají mimo domov (veřejná doména), ``pull`` = jak silně
    #: ho tlačí i domů (škola v úředním jazyce, úřady, smíšená manželství).
    #: ``tolerant`` nechá stabilní dvojjazyčnost (diglosie, Fishman 1967).
    policy_levels: Mapping[str, Mapping[str, float]] = field(default_factory=lambda: _table("policy_levels"))
    #: Podíl dospělých, kteří se lingua francou domluví mimo domov.
    lingua_franca_levels: Mapping[str, float] = field(default_factory=lambda: _table("lingua_franca_levels"))
    #: Síla vazby mluvčích lingua franca k jejímu zdroji (obchodní město).
    lingua_franca_link: float = _number("lingua_franca_link")
    #: Tlak lingua franca domů, když ji autor nechá zdomácnět (``nativize``).
    lingua_franca_pull: float = _number("lingua_franca_pull")
    #: Obrození (``polity.Revival``): ``pace`` = tempo návratu rodin k jazyku
    #: (obousměrný přechod), ``seed`` = podíl lidí, kteří se vymřelý nebo v obci
    #: ztracený jazyk znovu naučí (noví mluvčí, hebrejština, kornština).
    revival_levels: Mapping[str, Mapping[str, float]] = field(default_factory=lambda: _table("revival_levels"))
    #: Propustnost hranice státu (``State(border=...)``): násobek vazeb mezi
    #: regiony různých států. Hranice vznikne sama tam, kde sousedí regiony
    #: různých států, a působí hned; rozcházení podél ní dělají odlišná centra
    #: a normy. Přes hranici dvou států platí méně propustná z obou.
    border_levels: Mapping[str, float] = field(default_factory=lambda: _table("border_levels"))
    #: Pozadí dějin (``cee.v2.background``): míra drobných událostí, které svět
    #: generuje sám vedle událostí autora. Násobí ``background_rates``.
    background_levels: Mapping[str, float] = field(default_factory=lambda: _table("background_levels"))
    #: Kolikrát za století v jednom kraji nastane událost pozadí při míře
    #: ``normal``: mor, přesídlení části lidí k sousedům, vzestup obchodní cesty
    #: k sousednímu kraji, změna prestiže kraje, cizí elita od souseda jiného
    #: jazyka. Autorský odhad, kalibruje se v M7 (retence slovní zásoby).
    #: Rozsahy náhodných veličin pozadí dějin (rovnoměrně mezi mezemi): podíl
    #: zemřelých při moru, podíl přesídlených, násobek obchodu a prestiže a
    #: doby v krocích po 25 letech (obnova po moru, trvání obchodní cesty,
    #: splynutí cizí elity s místními).
    background_spans: Mapping[str, Mapping[str, float]] = field(default_factory=lambda: _table("background_spans"))
    #: Cizí elita z pozadí dějin (``background.ForeignElite``): prestiž elity,
    #: síla její vazby ke každé poddané vesnici a podíl obyvatel sídla. Síla
    #: vazby kalibrovaná na svět dvou jazyků s pozadím ``normal``
    #: (``docs/engine-v2/17-pozadi-dejin.md``): 0,1 dá retenci 88 % za
    #: tisíciletí a výpůjčky v základním slovníku 13 % za 3 000 let; dřívějších
    #: 0,5 (jako ``events.Conquest``) dávalo 77 % a 25 %.
    background_elite_prestige: float = _number("background_elite_prestige")
    background_elite_link: float = _number("background_elite_link")
    background_elite_share: float = _number("background_elite_share")
    background_rates: Mapping[str, float] = field(default_factory=lambda: _table("background_rates"))
    #: Spisovný jazyk (``polity.Standard``, ``polity.Schools``): podíl gramotných
    #: při kodifikaci a podíl dětí ve škole podle úrovně; násobí se dosahem centra.
    literacy_levels: Mapping[str, float] = field(default_factory=lambda: _table("literacy_levels"))
    schooling_levels: Mapping[str, float] = field(default_factory=lambda: _table("schooling_levels"))
    #: Kolikrát vyšší prestiž dostanou mluvčí jazyka, který má vlastní spisovnou
    #: normu (literatura, úřady, škola): vlastní norma brzdí přechod na jiný
    #: jazyk (čeština, finština, katalánština). Autorský odhad.
    standard_prestige: float = _number("standard_prestige")
    #: Dostupnost regionu podle terénu: násobí vazby přes hranici regionu, vazbu
    #: k sídlu státu i dosah jazykové politiky. Hory a ostrovy izolují.
    terrain_access: Mapping[str, float] = field(default_factory=lambda: _table("terrain_access"))
    #: Loajalita k jazyku podle odlišnosti regionu (etnikum, náboženství, vlastní
    #: historie): zpomalí přechod na jiný jazyk i jeho pronikání domů.
    identity_loyalty: Mapping[str, float] = field(default_factory=lambda: _table("identity_loyalty"))
    #: Přepisy vah tlaků podle jejich ``name`` (např. ``{"clarity": 2.0}``);
    #: platí pro všechny typy proměnných, kde tlak působí. Prázdné = tabulky
    #: jednotlivých změn beze změny. Neznámý tlak odmítne ``pressures_by_kind``.
    pressure_weights: Mapping[str, float] = field(default_factory=lambda: _table("pressure_weights"))
    #: Násobky tempa inovací podle ``kind`` změny (např. ``{"periphrasis": 0.5}``);
    #: násobí očekávaný počet inovací. Prázdné = tempa změn beze změny. Neznámou
    #: změnu odmítne simulace.
    change_rates: Mapping[str, float] = field(default_factory=lambda: _table("change_rates"))
    #: Přepisy polí ``need`` a ``context`` katalogu gramatických funkcí podle
    #: funkce, např. ``{"DEFINITE": {"context": 0.4}}``. Prázdné = katalog
    #: ``v2_grammar.yaml`` beze změny.
    grammar: Mapping[str, Mapping[str, float]] = field(default_factory=lambda: _table("grammar"))

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
        object.__setattr__(self, "channel_domains", _channel_domains(self.channel_domains))
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
