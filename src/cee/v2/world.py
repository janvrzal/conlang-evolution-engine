"""Svět: strom území, skupiny mluvčích, jejich kódy a síť vazeb (iterace 4)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping, Sequence, cast

from cee.v2.language.bank import FormBank
from cee.v2.language.journal import FrequencyMap
from cee.v2.language.lexicon import FormStore, Morpheme, PhonologyState, UnitForm
from cee.v2.language.morphology import FormChange, Paradigm, unit_id
from cee.v2.language.processes import Process, StressRule
from cee.v2.language.segments import SegmentTable, default_table
from cee.v2.parameters import Parameters
from cee.v2.pools import LivePools
from cee.v2.registry import RegisteredDict, Registry
from cee.v2.repertoire import Distribution, Origin, Repertoire, Variable, Variant
from cee.v2.rng import stable_id, stable_int
from cee.v2.semantics import ConceptGraph

TerritoryLevel = Literal["world", "continent", "region", "area", "settlement"]
TERRITORY_LEVELS: tuple[TerritoryLevel, ...] = ("world", "continent", "region", "area", "settlement")

LinkKind = Literal["strong", "weak"]


@dataclass(slots=True)
class Territory:
    """Uzel stromu území. Bez potomků je území „nerozepsané“."""

    id: str
    level: TerritoryLevel
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    #: Poloha těžiště v mapových jednotkách (km). Gravitační vazby ji potřebují.
    position: tuple[float, float] | None = None
    #: ``None`` = rozepsáno od začátku běhu, jinak rok zjemnění.
    refined_from_year: float | None = None
    #: Terén (klíč ``Parameters.terrain_access``): hory a ostrovy izolují.
    terrain: str = "plain"
    #: Původní jazyk území (linie), pokud ho scénář zná; obrození ho použije.
    native_language: str | None = None


@dataclass(slots=True)
class Code:
    """Jedna jazyková varieta, kterou skupina užívá."""

    id: str
    repertoire: Repertoire
    usage_share: float = 1.0
    acquisition: Literal["L1", "L2"] = "L1"
    l1_source: str | None = None
    #: Podkladové tvary morfémů, které se od výchozích liší.
    forms: FormStore = field(default_factory=FormStore)
    phonology: PhonologyState = field(default_factory=PhonologyState)
    stress_rule: StressRule = "penult"
    #: Linie jazyka (protojazyk, ze kterého kód pochází). Kontakt mezi kódy
    #: různých linií prochází filtrem přenositelnosti (M5).
    language: str = "proto"
    #: Podíl mluvčích, kteří se kód naučili až v dospělosti (0 až 1). Řídí
    #: interferenci z ``l1_source`` a tlak `Teachability`.
    l2_share: float = 0.0
    stress_strength: Literal["weak", "strong"] = "weak"

    def branch(self) -> Code:
        """Nezávislá kopie kódu (zjemnění, odštěpení)."""
        return Code(
            self.id, self.repertoire.branch(), self.usage_share, self.acquisition,
            self.l1_source, self.forms.branch(), self.phonology.branch(), self.stress_rule,
            self.language, self.l2_share, self.stress_strength,
        )


@dataclass(slots=True)
class SpeechGroup:
    """Základní jednotka simulace: lidé na jednom místě s vlastními kódy."""

    id: str
    territory: str
    population: int
    codes: list[Code]
    #: Délka generace v letech; fantasy národ může mít 500 let.
    generation_years: float = 25.0
    prestige: float = 0.5
    #: Jak velkou část vstupu nová generace bere od sousedů (0 = nic). Výchozí
    #: hodnota odpovídá venkovské skupině s převážně místními vazbami.
    openness: float = 0.1
    literacy: float = 0.0
    schooling: float = 0.0
    #: Pojmy, o kterých se ve skupině nemluví přímo (tabu); vynucují opis.
    taboo: frozenset[str] = frozenset()
    #: Souhrnná skupina zastupuje celé nerozepsané území.
    aggregate: bool = False
    internal_diversity: float = 0.0
    #: Vícejazyčná komunita je v simulaci víc skupin, jedna na kód; mají
    #: společné ``community`` (``None`` = skupina je komunitou sama).
    community: str | None = None
    #: Podíl dospělých přistěhovalců na generaci, kteří se kód učí jako druhý
    #: jazyk (obchodní město). Drží ``l2_share`` hlavního kódu.
    immigration: float = 0.0
    #: Učí se kód ještě děti? Kód pod prahem užívání v komunitě se nepředává
    #: a jeho skupina jen stárne.
    transmitted: bool = True
    #: Psaný kód (M6): obraz řeči elity v roce kodifikace. Nemá mluvčí a
    #: nevznikají v něm inovace. S nulovou otevřeností stojí (klasický psaný
    #: jazyk), s kladnou pomalu sleduje řeč svého zdroje (tisk, revize normy).
    written: bool = False
    #: ID psaného kódu, který skupina čte (gramotnost) a učí se ve škole.
    standard: str | None = None
    #: Liturgický kód (psaný kód náboženství, M6b) a podíl lidí, kteří ho čtou
    #: nebo slyší při bohoslužbě.
    liturgy: str | None = None
    devotion: float = 0.0
    #: Odpor komunity ke změně jazyka (0 až 1): zpomalí přechod na jiný kód.
    loyalty: float = 0.0
    #: Kde skupina kód užívá: ``home`` (doma; přechod na něj vytlačí starý
    #: jazyk) nebo ``public`` (trh, úřad, církev; stabilní dvojjazyčnost,
    #: děti se doma učí dál svůj jazyk).
    domain: Literal["home", "public"] = "home"
    #: Jak silně se veřejný kód (``domain="public"``) tlačí domů: škola
    #: v úředním jazyce, úřady, smíšená manželství (``cee.v2.polity``). Nula =
    #: stabilní dvojjazyčnost, děti se doma učí dál svůj jazyk. U domácí skupiny,
    #: která vznikla pronikáním veřejného kódu domů, je to tempo přechodu.
    home_pull: float = 0.0
    #: Autor jazyk skupiny zakonzervoval: nikdo z ní nepřejde na jiný jazyk
    #: (``polity.Preserve``). Jazyk se dál vyvíjí, jen nevymře.
    preserved: bool = False
    #: Síla obrozeneckého hnutí (0 až 1, ``polity.Revival``): tempo, kterým se
    #: rodiny, jež přešly na jiný jazyk, vracejí k jazyku této skupiny.
    revival: float = 0.0

    def __post_init__(self) -> None:
        if self.population <= 0:
            raise ValueError(f"Skupina '{self.id}' musí mít kladnou populaci.")
        if self.generation_years <= 0:
            raise ValueError(f"Skupina '{self.id}' musí mít kladnou délku generace.")
        if not 0.0 <= self.openness <= 1.0:
            raise ValueError(f"Otevřenost skupiny '{self.id}' musí ležet v intervalu 0 až 1.")
        if self.prestige < 0:
            raise ValueError(f"Prestiž skupiny '{self.id}' nesmí být záporná.")
        if not self.codes:
            raise ValueError(f"Skupina '{self.id}' musí mít alespoň jeden kód.")

    @property
    def main_code(self) -> Code:
        return self.codes[0]


@dataclass(frozen=True, slots=True)
class Link:
    """Směrovaná vazba: ``source`` se učí od ``target`` se sílou ``strength``."""

    source: str
    target: str
    strength: float
    kind: LinkKind = "weak"


@dataclass(slots=True)
class World:
    seed: int
    start_year: float = 0.0
    #: Číselné registry entit (morfémy, varianty, proměnné, pojmy, skupiny,
    #: procesy). Patří světu a kopíruje se s ním; viz :mod:`cee.v2.registry`.
    registry: Registry = field(default_factory=Registry)
    territories: dict[str, Territory] = field(default_factory=dict)
    groups: dict[str, SpeechGroup] = field(default_factory=dict)
    links: dict[tuple[str, str], Link] = field(default_factory=dict)
    variables: dict[str, Variable] = field(default_factory=dict)
    variants: dict[str, Variant] = field(default_factory=dict)
    #: Proměnné, ve kterých se skupiny liší; viz :mod:`cee.v2.pools`.
    live: LivePools = field(default_factory=LivePools)
    morphemes: dict[str, Morpheme] = field(default_factory=dict)
    #: ID procesní proměnné → proces. Chronologii změn drží každý kód sám.
    processes: dict[str, Process] = field(default_factory=dict)
    #: Třída slova → paradigma; ID formové proměnné → analogická změna.
    paradigms: dict[str, Paradigm] = field(default_factory=dict)
    form_changes: dict[str, FormChange] = field(default_factory=dict)
    #: Tabulka hlásek; svět bez hláskových tvarů (M1) ji nepotřebuje.
    table: SegmentTable | None = None
    #: Graf pojmů pro posun významu, odvozování a skládání (M3b).
    semantics: ConceptGraph | None = None
    #: Pojem → třída slova (``None`` = neohebné).
    concept_classes: dict[str, str | None] = field(default_factory=dict)
    #: Pojem → jak často se o něm mluví (0 až 1); vlastnost významu, ne slova.
    concept_frequencies: dict[str, float] = field(default_factory=FrequencyMap)
    #: Odvozovací přípona protojazyka (M3b).
    derivational_suffix: tuple[int, ...] = ()
    #: Podíl lidí, kteří se za generaci přestěhují k sousedům (M6b). Nula
    #: vypne migraci; podíl přistěhovalců pak určuje ``immigration`` skupin.
    migration: float = 0.0
    #: Banka různých tvarů a tabulky procesů (M6d); vzniká až při potřebě.
    bank: FormBank | None = None
    #: Výchozí tvar každého morfému (neměnný), aby se netvořil při každém čtení.
    default_units: dict[str, UnitForm] = field(default_factory=dict)
    #: Kalibrační konstanty dynamiky tohoto světa (neměnné, sdílí je kopie stavu).
    params: Parameters = field(default_factory=Parameters)
    #: Státy světa (``cee.v2.polity``) podle ID; vznikají událostí ``State``.
    states: dict[str, Any] = field(default_factory=dict)
    #: Spisovné jazyky států a regionů: ID státu či regionu → ID psaného kódu.
    standards: dict[str, str] = field(default_factory=dict)
    #: Pojmy, ze kterých se skládá vlastní jméno jazyka (``cee.v2.naming``):
    #: ID protojazyka → pojmy. Jen pro export; dynamiku neovlivní.
    endonyms: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: Vazby oslabené hranicí států: (zdroj, cíl) → použitý násobek. Základní
    #: síla vazby je síla / násobek (``polity.refresh``).
    border_factors: dict[tuple[str, str], float] = field(default_factory=dict)
    #: Základní prestiž skupin před vlivem států a spisovných jazyků.
    base_prestige: dict[str, float] = field(default_factory=dict)
    #: Skupina → skupina, jejíž prestiž přebírá (veřejná doména úředního jazyka
    #: a rodiny, které na něj přešly, mají status jeho sídla).
    prestige_mirror: dict[str, str] = field(default_factory=dict)
    #: Protojazyky už dostaly souběžnou variabilitu (``cee.v2.variation``).
    varied: bool = False

    def __post_init__(self) -> None:
        # Slovníky entit zapisují nové klíče do registru (číslo = pořadí vzniku).
        self.groups = RegisteredDict(self.registry, "group", self.groups)
        self.variables = RegisteredDict(self.registry, "variable", self.variables)
        self.variants = RegisteredDict(self.registry, "variant", self.variants)
        self.morphemes = RegisteredDict(self.registry, "morpheme", self.morphemes)
        self.processes = RegisteredDict(self.registry, "process", self.processes)
        if not isinstance(self.concept_frequencies, FrequencyMap):
            self.concept_frequencies = FrequencyMap(self.concept_frequencies)

    def distribution(self, group_id: str, variable_id: str) -> Distribution | None:
        """Jediné správné čtení stavu: živá proměnná má přednost před repertoárem."""
        if variable_id in self.live and group_id in self.live.group_index:
            return self.live.get(group_id, variable_id)
        return self.stored(group_id, variable_id)

    def dominant(self, group_id: str, variable_id: str) -> tuple[str, float] | None:
        """Nejčastější varianta a její podíl (``distribution(...).dominant()``), bez kopie rozdělení."""
        if variable_id in self.live and group_id in self.live.group_index:
            return self.live.dominant(group_id, variable_id)
        found = self.stored(group_id, variable_id)
        return None if found is None else found.dominant()

    def stored(self, group_id: str, variable_id: str) -> Distribution | None:
        """Stav z repertoáru (bez živého skladu), včetně výchozí varianty."""
        found = self.groups[group_id].main_code.repertoire.get(variable_id)
        if found is None:
            variable = self.variables.get(variable_id)
            if variable is not None and variable.default is not None:
                return Distribution.fixed(variable.default)
        return found

    def form_bank(self) -> FormBank:
        if self.bank is None:
            assert self.table is not None
            self.bank = FormBank(self.table)
        return self.bank

    def concept_frequency(self, concept: str) -> float:
        return self.concept_frequencies.get(concept, 0.3)

    def usage_frequency(self, code: Code, morpheme_id: str) -> float:
        """Jak často kód tvar užívá: součet frekvencí pojmů, které vyjadřuje.

        Slovo, které posunem významu získá další pojem, se tím stane
        častějším; slovo, které pojem ztratí, vzácnějším. Tvar buňky
        paradigmatu má navíc váhu své buňky. Bez dominantních pojmů (svět M1,
        výchozí stav) platí statická frekvence morfému.
        """
        memo = self._usage_memo(code)
        morpheme = self.morphemes[morpheme_id]
        values = memo.by_root.get(morpheme.lexeme or morpheme.id)
        if values is not None:
            found = values.get(morpheme_id)
            if found is not None:
                return found
        return self._usage_compute(code, morpheme, memo)

    def usage_frequencies(self, code: Code, morpheme_ids: Iterable[str]) -> list[float]:
        """Totéž co :meth:`usage_frequency` pro víc tvarů, s jedním ověřením paměti.

        Hodnoty a jejich pořadí jsou stejné jako při volání po jednom; hromadné
        volání jen ušetří režii (ověření verze a hledání paměti pro každý tvar).
        """
        memo = self._usage_memo(code)
        by_root = memo.by_root
        morphemes = self.morphemes
        result: list[float] = []
        append = result.append
        for morpheme_id in morpheme_ids:
            morpheme = morphemes[morpheme_id]
            values = by_root.get(morpheme.lexeme or morpheme.id)
            if values is not None:
                found = values.get(morpheme_id)
                if found is not None:
                    append(found)
                    continue
            append(self._usage_compute(code, morpheme, memo))
        return result

    def _usage_memo(self, code: Code) -> _UsageMemo:
        # Výsledek závisí jen na pojmech, pro které je kořen dominantní, a na
        # frekvencích pojmů světa. Pamatuje se po kořenech; deník dominantních
        # kořenů (``dominant_log``) zneplatní jen kořeny, kterých se změna týká.
        state = code.phonology
        held = state.cache.get("usage-frequency")
        memo = cast(_UsageMemo, held[1]) if held is not None else None
        frequencies = self.concept_frequencies
        key = (id(frequencies), getattr(frequencies, "version", None))
        log = state.dominant_log
        if memo is None or memo.key != key or memo.cursor > len(log) or key[1] is None:
            memo = _UsageMemo(key, len(log))
            state.cache["usage-frequency"] = (0, memo)
        elif memo.cursor < len(log):
            for _, old_root, new_root in log[memo.cursor:]:
                memo.by_root.pop(old_root, None)
                memo.by_root.pop(new_root, None)
            memo.cursor = len(log)
        return memo

    def _usage_compute(self, code: Code, morpheme: Morpheme, memo: _UsageMemo) -> float:
        values = memo.by_root.setdefault(morpheme.lexeme_id, {})
        concepts = _concepts_by_root(code).get(morpheme.lexeme_id)
        if not concepts:
            total = morpheme.frequency
        else:
            total = min(1.0, sum(self.concept_frequency(concept) for concept in concepts))
            if morpheme.kind == "word" and morpheme.word_class in self.paradigms and morpheme.cell:
                total *= self.paradigms[morpheme.word_class].weight(morpheme.cell)
        values[morpheme.id] = total
        return total

    def unit_of(self, code: Code, morpheme_id: str) -> UnitForm:
        """Aktuální stav tvaru slova (tvar, hranice koncovky, koncovka) v kódu."""
        # Průchod vrstvami úložiště tvarů (``FormStore.get``) bez dalšího volání.
        layer: FormStore | None = code.forms
        while layer is not None:
            stored = layer._own.get(morpheme_id)
            if stored is not None:
                return stored
            layer = layer._base
        default = self.default_units.get(morpheme_id)
        if default is None:
            morpheme = self.morphemes[morpheme_id]
            default = self.default_units[morpheme_id] = UnitForm(
                morpheme.form, morpheme.boundary, morpheme.exponent
            )
        return default

    def form_of(self, code: Code, morpheme_id: str) -> tuple[int, ...]:
        """Aktuální podkladový tvar morfému v daném kódu."""
        return self.unit_of(code, morpheme_id).form

    def materialize(self, group_id: str) -> None:
        """Zapíše živé proměnné skupiny do jejího repertoáru (před odebráním či kopií)."""
        if group_id not in self.live.group_index:
            return
        repertoire = self.groups[group_id].main_code.repertoire
        for variable_id in self.live.variable_ids:
            item = self.live.get(group_id, variable_id)
            if item is not None:
                repertoire.set(variable_id, item)

    def add_territory(self, territory: Territory) -> Territory:
        if territory.id in self.territories:
            raise ValueError(f"Území '{territory.id}' už existuje.")
        if territory.parent is not None:
            parent = self.territories.get(territory.parent)
            if parent is None:
                raise ValueError(f"Nadřazené území '{territory.parent}' neexistuje.")
            if TERRITORY_LEVELS.index(territory.level) <= TERRITORY_LEVELS.index(parent.level):
                raise ValueError(
                    f"Území '{territory.id}' musí ležet níž než '{parent.id}' ({parent.level})."
                )
            parent.children.append(territory.id)
        self.territories[territory.id] = territory
        return territory

    def add_group(self, group: SpeechGroup) -> SpeechGroup:
        if group.id in self.groups:
            raise ValueError(f"Skupina '{group.id}' už existuje.")
        if group.territory not in self.territories:
            raise ValueError(f"Území '{group.territory}' skupiny '{group.id}' neexistuje.")
        self.groups[group.id] = group
        return group

    def remove_group(self, group_id: str) -> SpeechGroup:
        group = self.groups.pop(group_id)
        for key in [key for key in self.links if group_id in key]:
            del self.links[key]
        return group

    def connect(self, first: str, second: str, strength: float, kind: LinkKind = "weak") -> None:
        """Oboustranná vazba. Sousedé se učí jeden od druhého stejně často."""
        for group_id in (first, second):
            if group_id not in self.groups:
                raise ValueError(f"Skupina '{group_id}' neexistuje.")
        if first == second:
            raise ValueError("Skupina nemůže mít vazbu sama na sebe.")
        value = max(0.0, min(1.0, float(strength)))
        self.links[(first, second)] = Link(first, second, value, kind)
        self.links[(second, first)] = Link(second, first, value, kind)

    def neighbors(self, group_id: str) -> list[Link]:
        return sorted(
            (link for (source, _), link in self.links.items() if source == group_id),
            key=lambda link: link.target,
        )

    def group_ids(self) -> list[str]:
        return sorted(self.groups)

    def position_of(self, group_id: str) -> tuple[float, float] | None:
        return self.territories[self.groups[group_id].territory].position

    def renewal(self, group_id: str, dt: float) -> float:
        """Podíl skupiny, který se za krok učí jazyk znovu (0 bez dětí)."""
        group = self.groups[group_id]
        if not group.transmitted or (group.written and group.openness == 0.0):
            return 0.0
        return min(1.0, dt / group.generation_years)

    def generation_ceiling(self) -> float:
        """Nejkratší délka generace; krok simulace nesmí být delší."""
        return min(group.generation_years for group in self.groups.values())

    def _seed_paradigm(
        self, root: Morpheme, endings: Mapping[tuple[str, str], Sequence[tuple[str, float]]],
        cells: Sequence[str] | None = None,
    ) -> None:
        assert self.table is not None and root.word_class is not None
        paradigm = self.paradigms[root.word_class]
        for cell in paradigm.cells[1:]:
            if cells is not None and cell not in cells:
                continue
            options = endings.get((root.word_class, cell))
            if not options:
                raise ValueError(f"Chybí koncovky pro {root.word_class}/{cell}.")
            ending = _choose(options, root.id + cell)
            parts = (root.word_class, cell, ending)
            affix = stable_id("affix", *parts) if root.language == "proto" else stable_id(
                "affix", root.language, *parts
            )
            if affix not in self.morphemes:
                self.morphemes[affix] = Morpheme(
                    affix, f"{root.word_class}.{cell}", self.table.parse(ending), kind="affix",
                    word_class=root.word_class, cell=cell, language=root.language,
                )
            unit = Morpheme(
                id=unit_id(root.id, cell, paradigm),
                meaning=root.meaning,
                form=root.form + self.morphemes[affix].form,
                frequency=root.frequency * paradigm.weight(cell),
                kind="word",
                word_class=root.word_class,
                lexeme=root.id,
                cell=cell,
                exponent=affix,
                boundary=len(root.form),
                language=root.language,
            )
            self.morphemes[unit.id] = unit

    def seed_lexicon(
        self,
        concepts: Sequence[str],
        forms: Mapping[str, str] | None = None,
        frequencies: Mapping[str, float] | None = None,
        classes: Mapping[str, str] | None = None,
        endings: Mapping[tuple[str, str], Sequence[tuple[str, float]]] | None = None,
        *,
        language: str = "proto",
        cells: Mapping[str, Sequence[str]] | None = None,
    ) -> Repertoire:
        """Zmrazený protojazyk: každý pojem má jedno zděděné slovo.

        Bez ``forms`` je slovo jen identifikátor lexému (svět M1). S nimi
        dostane každý pojem morfém s hláskovou podobou a svět tabulku hlásek.
        Pojmy s třídou z ``classes``, pro kterou má svět paradigma, dostanou
        také tvary ostatních buněk: kmen + koncovka vybraná z ``endings``
        podle vah (např. plurál na -i u 65 % a -an u 35 % podstatných jmen).

        Svět může mít víc protojazyků (M5): každý má vlastní ``language``,
        ze kterého se odvozují ID jeho slov a variant, a ``cells`` omezí
        buňky paradigmat, které jazyk má (paradigmata světa jsou sjednocení).
        Pojmy, jejich frekvence a třídy jsou vlastnost významu a určí je
        první zasetý jazyk.
        """
        repertoire = Repertoire()
        if forms is not None and self.table is None:
            self.table = default_table()
        for concept in dict.fromkeys(concepts):
            variable = Variable("lexical", concept)
            payload: dict[str, object] = {"lexeme": stable_id("lexeme", language, concept)}
            if forms is not None:
                assert self.table is not None
                word_class = (classes or {}).get(concept)
                if word_class not in self.paradigms:
                    word_class = None
                self.concept_classes.setdefault(concept, word_class)
                morpheme = Morpheme(
                    id=stable_id("morpheme", language, concept),
                    meaning=concept,
                    form=self.table.parse(forms[concept]),
                    frequency=self.concept_frequencies.setdefault(
                        concept, float((frequencies or {}).get(concept, 0.5))
                    ),
                    word_class=word_class,
                    language=language,
                )
                self.morphemes[morpheme.id] = morpheme
                payload["morpheme"] = morpheme.id
                payload["origin"] = "inherited"
                if word_class is not None:
                    self._seed_paradigm(
                        morpheme, endings or {}, None if cells is None else cells.get(word_class, ())
                    )
            variant = Variant(
                id=stable_id("variant", language, variable.id),
                variable=variable.id,
                payload=payload,
                origin=Origin(change=None, tick=0, year=self.start_year, group=None),
            )
            self.variables[variable.id] = variable
            self.variants[variant.id] = variant
            repertoire.set(variable.id, Distribution.fixed(variant.id))
        return repertoire.freeze()


class _UsageMemo:
    """Frekvence užití tvarů kódu po kořenech (viz ``World.usage_frequency``)."""

    __slots__ = ("key", "cursor", "by_root")

    def __init__(self, key: tuple[int, int | None], cursor: int) -> None:
        self.key = key
        self.cursor = cursor
        self.by_root: dict[str | None, dict[str, float]] = {}


def _concepts_by_root(code: Code) -> dict[str, list[str]]:
    """Kořen → pojmy, pro které je dominantní (v pořadí slovníku kódu)."""
    state = code.phonology
    cached = state.cache.get("concepts-by-root")
    if cached is not None and cached[0] == state.lexicon_version:
        return cached[1]  # type: ignore[return-value]
    index: dict[str, list[str]] = {}
    for concept, root in state.dominant.items():
        index.setdefault(root, []).append(concept)
    state.cache["concepts-by-root"] = (state.lexicon_version, index)
    return index


def _choose(options: Sequence[tuple[str, float]], key: str) -> str:
    """Deterministická volba podle vah (bez stavu generátoru)."""
    total = sum(weight for _, weight in options)
    point = (stable_int("ending", key) % 1_000_000) / 1_000_000 * total
    for value, weight in options:
        point -= weight
        if point < 0:
            return value
    return options[-1][0]


def gravity_links(
    world: World,
    *,
    scale: float = 1.0,
    reference_population: float = 1_000.0,
    reference_distance: float = 10.0,
    max_distance: float | None = None,
    groups: Sequence[str] | None = None,
) -> int:
    """Doplní vazby podle gravitačního modelu (Trudgill 1974).

    Síla roste s geometrickým průměrem populací a klesá se čtvercem
    vzdálenosti; saturace ``x / (1 + x)`` ji drží v intervalu 0 až 1.
    Referenční populace a vzdálenost jsou výchozí odhad, ne kalibrace.
    Vrací počet vytvořených oboustranných vazeb. S ``groups`` jen mezi
    vybranými skupinami (např. uvnitř jednoho jazyka).
    """
    placed = [
        (group_id, world.position_of(group_id))
        for group_id in (world.group_ids() if groups is None else sorted(groups))
        if world.position_of(group_id) is not None
    ]
    created = 0
    for index, (first, first_position) in enumerate(placed):
        for second, second_position in placed[index + 1 :]:
            assert first_position is not None and second_position is not None
            distance = math.dist(first_position, second_position)
            if distance == 0 or (max_distance is not None and distance > max_distance):
                continue
            mass = math.sqrt(world.groups[first].population * world.groups[second].population)
            pull = scale * (mass / reference_population) / (distance / reference_distance) ** 2
            world.connect(first, second, pull / (1.0 + pull))
            created += 1
    return created
