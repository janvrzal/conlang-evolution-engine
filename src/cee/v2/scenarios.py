"""Hotové světy pro validační scénáře a benchmarky (specifikace, S1–S5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from cee.data.core_vocabulary import CORE_EXTENSION, SWADESH_CORE
from cee.v2.events import (
    Border,
    Codification,
    Conquest,
    Contact,
    LanguageShift,
    Printing,
    ReligiousChange,
    Schooling,
    WorldEvent,
)
from cee.v2.language.constructions import GRAMMATICAL_SOURCES, Construction, catalog
from cee.v2.language.morphology import Paradigm
from cee.v2.language.protoforms import DEFAULT_CONSONANTS, DEFAULT_VOWELS, protolanguage
from cee.v2.repertoire import Distribution, Origin, Repertoire
from cee.v2.rng import stable_int
from cee.v2.semantics import core_graph
from cee.v2.syntax import register as register_construction
from cee.v2.world import Code, SpeechGroup, Territory, World, gravity_links

DEFAULT_CONCEPTS: tuple[str, ...] = tuple(dict.fromkeys((*SWADESH_CORE, *CORE_EXTENSION)))


#: Slovesa základní slovní zásoby; ostatní ohebná slova jsou podstatná jména.
VERBS = frozenset("""
drink eat bite see hear know sleep die kill swim fly walk come lie sit stand give say burn
speak write read work make carry open close have finish go want
""".split())
#: Neohebná slova: zájmena, číslovky, přídavná jména a částice.
UNINFLECTED = frozenset("""
i you we this that who what not all many one two big long small red green yellow white black
hot cold full new good round dry near far old young fast slow
""".split())

PROTO_PARADIGMS = {
    "noun": Paradigm("noun", ("SG", "PL"), (1.0, 0.4)),
    "verb": Paradigm("verb", ("PRES", "PAST"), (1.0, 0.5)),
}
#: Dvě koncovky pro každou buňku: větší a menší vzor, jako v reálných jazycích.
PROTO_ENDINGS = {
    ("noun", "PL"): (("i", 0.65), ("an", 0.35)),
    ("verb", "PAST"): (("ta", 0.7), ("u", 0.3)),
}


#: Gramatika protojazyka se syntaxí (M4): minulý čas, plurál a pád předmětu
#: koncovkou, zápor částicí před slovesem a role argumentů pádem. Funkce
#: katalogu, které v profilu nejsou, jazyk nemá a ani je nevyvine; funkce
#: s konstrukcí ``zero`` nevyjadřuje, ale může je vyvinout.
SYNTAX_GRAMMAR: Mapping[str, Construction] = {
    "PAST": Construction("PAST", "synthetic"),
    "PL": Construction("PL", "synthetic"),
    "OBJ": Construction("OBJ", "synthetic"),
    "NEG": Construction("NEG", "pre", "not"),
    "ORDER": Construction("ORDER", "free"),
}
#: Úplná gramatika pro typologické pokusy (C1): SYNTAX_GRAMMAR plus všechny
#: zbývající funkce katalogu nastavené na ``zero``, aby je jazyk mohl vyvinout.
FULL_GRAMMAR: Mapping[str, Construction] = {
    **SYNTAX_GRAMMAR,
    "FUTURE": Construction("FUTURE", "zero"),
    "DEFINITE": Construction("DEFINITE", "zero"),
}
#: Citační buňka každé třídy slov.
CITATION_CELLS = {"noun": "SG", "verb": "PRES"}
#: Koncovky buněk, které protojazyk se syntaxí může mít; předmět typu
#: latinského akuzativu -m (snadno eroduje).
SYNTAX_ENDINGS = {
    ("noun", "OBJ"): (("m", 0.6), ("ne", 0.4)),
    ("noun", "DEF"): (("le", 0.7), ("n", 0.3)),
    ("verb", "FUT"): (("sa", 0.6), ("bo", 0.4)),
}


def grammar_paradigms(grammar: Mapping[str, Construction]) -> dict[str, Paradigm]:
    """Paradigmata podle profilu: buňka pro každou funkci vyjádřenou koncovkou."""
    cells: dict[str, list[tuple[str, float]]] = {word_class: [] for word_class in CITATION_CELLS}
    for name, entry in catalog().items():  # pořadí katalogu
        construction = grammar.get(name)
        if construction is None or construction.kind != "synthetic" or entry.cell is None:
            continue
        assert entry.word_class is not None
        cells[entry.word_class].append((entry.cell, entry.weight))
    return {
        word_class: Paradigm(
            word_class,
            (CITATION_CELLS[word_class], *(cell for cell, _ in found)),
            (1.0, *(weight for _, weight in found)),
        )
        for word_class, found in cells.items()
    }


def _seed_constructions(world: World, base: Repertoire, grammar: Mapping[str, Construction]) -> Repertoire:
    """Každá funkce profilu dostane konstrukční proměnnou s výchozí konstrukcí."""
    layer = Repertoire(base)
    origin = Origin(None, 0, world.start_year, None)
    for name, construction in grammar.items():
        if construction.function != name or name not in catalog():
            raise ValueError(f"Neznámá nebo nesouhlasná funkce profilu: {name}.")
        variable, variant = register_construction(world, construction, origin)
        layer.set(variable, Distribution.fixed(variant.id))
    return layer.freeze()


#: Odvozovací přípona protojazyka (jmenná, typ *-ka*).
DERIVATIONAL_SUFFIX = "ka"


def word_class(concept: str) -> str | None:
    if concept in UNINFLECTED or concept.startswith("concept-"):
        return None
    return "verb" if concept in VERBS else "noun"


def synthetic_concepts(count: int) -> tuple[str, ...]:
    return tuple(f"concept-{index:04d}" for index in range(count))


def village_grid(
    columns: int,
    rows: int = 1,
    *,
    seed: int = 1,
    concepts: Sequence[str] = DEFAULT_CONCEPTS,
    spacing: float = 10.0,
    population: int = 500,
    generation_years: float = 25.0,
    openness: float = 0.1,
    link_reach: float = 2.0,
    phonology: bool = False,
    morphology: bool = False,
    semantics: bool = False,
    syntax: bool = False,
    grammar: Mapping[str, Construction] | None = None,
    taboo: Sequence[str] = (),
) -> World:
    """Mřížka stejných vesnic s gravitačními vazbami na nejbližší sousedy.

    S jedním řádkem je to scénář S1 (dialektové kontinuum). Vazby sahají jen
    do ``link_reach`` násobku rozestupu, takže vzdálené vesnice spolu mluví
    jen přes prostředníky. S ``phonology`` dostanou slova hláskové tvary
    vygenerovaného protojazyka (M2), s ``morphology`` navíc podstatná jména
    plurál a slovesa minulý čas (M3), se ``semantics`` graf pojmů pro posun
    významu, odvozování a skládání (M3b), se ``syntax`` pádová koncovka
    předmětu, konstrukce minulého času, záporu a slovosledu a zdrojové pojmy
    gramatikalizace (M4). Profil ``grammar`` (funkce → výchozí konstrukce)
    nahradí výchozí gramatiku :data:`SYNTAX_GRAMMAR` a zapne syntax (M4b).
    """
    world = World(seed=seed)
    world.add_territory(Territory("world", "world"))
    world.add_territory(
        Territory("valley", "area", parent="world",
                  position=((columns - 1) * spacing / 2, (rows - 1) * spacing / 2))
    )
    if grammar is not None:
        syntax = True
    grammar = SYNTAX_GRAMMAR if grammar is None else grammar
    if syntax:
        morphology = phonology = True
        concepts = tuple(dict.fromkeys((*concepts, *GRAMMATICAL_SOURCES)))
        world.paradigms.update(grammar_paradigms(grammar))
    elif morphology:
        world.paradigms.update(PROTO_PARADIGMS)
    if semantics:
        world.semantics = core_graph()
    if phonology or morphology or semantics:
        forms, frequencies = protolanguage(concepts, seed=seed)
        classes = (
            {concept: found for concept in concepts if (found := word_class(concept)) is not None}
            if morphology else None
        )
        endings = {**PROTO_ENDINGS, **SYNTAX_ENDINGS} if syntax else PROTO_ENDINGS if morphology else None
        base = world.seed_lexicon(concepts, forms, frequencies, classes, endings)
        if syntax:
            base = _seed_constructions(world, base, grammar)
        if semantics and world.table is not None:
            world.derivational_suffix = world.table.parse(DERIVATIONAL_SUFFIX)
    else:
        base = world.seed_lexicon(concepts)
    for row in range(rows):
        for column in range(columns):
            village = f"v{row:02d}-{column:02d}"
            world.add_territory(
                Territory(village, "settlement", parent="valley",
                          position=(column * spacing, row * spacing))
            )
            world.add_group(
                SpeechGroup(
                    id=village,
                    territory=village,
                    population=population,
                    codes=[Code("main", base.branch())],
                    generation_years=generation_years,
                    openness=openness,
                    taboo=frozenset(taboo),
                )
            )
    gravity_links(world, max_distance=spacing * link_reach)
    return world


@dataclass(frozen=True)
class Place:
    """Skupina mluvčích v :func:`contact_world`."""

    id: str
    position: tuple[float, float]
    population: int = 500
    prestige: float = 0.5
    openness: float = 0.1
    immigration: float = 0.0


@dataclass(frozen=True)
class Language:
    """Jeden protojazyk světa s víc jazyky a skupiny, které jím mluví."""

    id: str
    places: tuple[Place, ...]
    grammar: Mapping[str, Construction] = field(default_factory=lambda: dict(SYNTAX_GRAMMAR))
    consonants: tuple[str, ...] = DEFAULT_CONSONANTS
    vowels: tuple[str, ...] = DEFAULT_VOWELS
    #: Vazby uvnitř jazyka sahají do této vzdálenosti (km).
    link_reach: float = 25.0


def contact_world(
    languages: Sequence[Language],
    *,
    seed: int = 1,
    concepts: Sequence[str] = DEFAULT_CONCEPTS,
    semantics: bool = True,
    generation_years: float = 25.0,
) -> World:
    """Svět s několika nepříbuznými jazyky (M5).

    Každý jazyk má vlastní protojazyk (tvary podle svého inventáře a seedu),
    vlastní profil gramatiky a vlastní skupiny. Vazby vzniknou jen uvnitř
    jazyka; kontakt mezi jazyky zakládá až událost
    :class:`cee.v2.events.Contact`, takže jazyky do té doby žijí odděleně.
    Paradigmata světa jsou sjednocení buněk všech jazyků; každý jazyk
    dostane koncovky jen ve svých buňkách.
    """
    world = World(seed=seed)
    world.add_territory(Territory("world", "world"))
    concepts = tuple(dict.fromkeys((*concepts, *GRAMMATICAL_SOURCES)))
    cells: dict[str, dict[str, tuple[str, ...]]] = {}
    union: dict[str, set[str]] = {}
    for language in languages:
        cells[language.id] = {
            kind: paradigm.cells[1:] for kind, paradigm in grammar_paradigms(language.grammar).items()
        }
        for kind, found in cells[language.id].items():
            union.setdefault(kind, set()).update(found)
    order = {entry.cell: index for index, entry in enumerate(catalog().values())}
    weights = {entry.cell: entry.weight for entry in catalog().values()}
    for kind, citation in CITATION_CELLS.items():
        ordered = sorted(union.get(kind, ()), key=lambda cell: order[cell])
        world.paradigms[kind] = Paradigm(
            kind, (citation, *ordered), (1.0, *(weights[cell] for cell in ordered))
        )
    if semantics:
        world.semantics = core_graph()
    classes = {concept: cls for concept in concepts if (cls := word_class(concept)) is not None}
    for language in languages:
        forms, frequencies = protolanguage(
            concepts, seed=stable_int(seed, "language", language.id) % (1 << 31),
            consonants=language.consonants, vowels=language.vowels,
        )
        base = world.seed_lexicon(
            concepts, forms, frequencies, classes, {**PROTO_ENDINGS, **SYNTAX_ENDINGS},
            language=language.id, cells=cells[language.id],
        )
        base = _seed_constructions(world, base, language.grammar)
        territory = f"area-{language.id}"
        world.add_territory(Territory(territory, "area", parent="world", position=language.places[0].position))
        for place in language.places:
            world.add_territory(Territory(place.id, "settlement", parent=territory, position=place.position))
            world.add_group(
                SpeechGroup(
                    id=place.id, territory=place.id, population=place.population,
                    codes=[Code("main", base.branch(), language=language.id)],
                    generation_years=generation_years, prestige=place.prestige,
                    openness=place.openness, immigration=place.immigration,
                )
            )
            world.groups[place.id].main_code.l2_share = place.immigration
        gravity_links(world, max_distance=language.link_reach, groups=[place.id for place in language.places])
    if semantics and world.table is not None:
        world.derivational_suffix = world.table.parse(DERIVATIONAL_SUFFIX)
    return world


def island_and_city(seed: int = 1, *, immigration: float = 0.3) -> World:
    """Scénář S2: izolovaný ostrov a obchodní město se stejným protojazykem.

    Ostrov je malá vesnice bez vazeb. Město je velké, otevřené, obklopené
    čtyřmi vesnicemi a každou generaci do něj přichází ``immigration``
    dospělých, kteří se jeho jazyk učí jako druhý.
    """
    places = (
        Place("island", (-200.0, 0.0), population=300, openness=0.0),
        Place("city", (0.0, 0.0), population=5000, openness=0.3, immigration=immigration),
        *(
            Place(f"v{index}", (15.0 * x, 15.0 * y), population=500)
            for index, (x, y) in enumerate(((1, 0), (-1, 0), (0, 1), (0, -1)))
        ),
    )
    return contact_world([Language("proto", places)], seed=seed)


#: Gramatika menšinového jazyka scénáře S3: zápor za slovesem (konec
#: Jespersenova cyklu) a pevný slovosled SOV, kdežto většinový jazyk má zápor
#: před slovesem a volný slovosled.
SUBSTRATE_GRAMMAR: Mapping[str, Construction] = {
    **SYNTAX_GRAMMAR,
    "NEG": Construction("NEG", "post", "step"),
    "ORDER": Construction("ORDER", "fixed", order="SOV"),
}


def language_shift(seed: int = 1, *, start: float = 1500.0) -> tuple[World, list[WorldEvent]]:
    """Scénář S3: menšinový region přejde na prestižní jazyk souseda.

    Tři vesnice jazyka ``x`` (prestiž 0,3) a tři vesnice jazyka ``y``
    (prestiž 1) se do roku ``start`` vyvíjejí odděleně. Pak se pohraniční
    vesnice obou jazyků propojí a vesnice ``x`` jedna po druhé (od hranice)
    začnou přecházet na ``y``.
    """
    world = contact_world([
        Language(
            "x", tuple(Place(f"x{index}", (index * 10.0, 0.0), population=500, prestige=0.3)
                       for index in range(3)),
            grammar=SUBSTRATE_GRAMMAR,
            consonants=("t", "k", "q", "s", "n", "m", "l", "ʃ", "x", "r", "j", "ts"),
        ),
        Language(
            "y", tuple(Place(f"y{index}", (40.0 + index * 10.0, 0.0), population=1000, prestige=1.0)
                       for index in range(3)),
        ),
    ], seed=seed)
    events: list[WorldEvent] = [Contact(start, (("x2", "y0"),), 0.5)]
    events += [LanguageShift(start + 25.0 * step, f"x{2 - step}", "y0") for step in range(3)]
    return world, events


def diglossia(
    seed: int = 1, *, writing: float = 500.0, school: float | None = 1500.0, printing: bool = True,
    literacy: float = 0.05, diglossic: bool = False,
) -> tuple[World, list[WorldEvent]]:
    """Scénář S4: písmo v roce ``writing``, škola (a tisk) v roce ``school``.

    Šest vesnic jednoho jazyka; prostřední vesnice je sídlo elity, jejíž řeč
    se zapíše. Do zavedení školy čte jen ``literacy`` lidí a psaný kód stojí.
    Škola zasáhne všechny vesnice; s ``printing`` se psaná norma od té doby
    obnovuje podle řeči elity, jak to bylo u moderních spisovných jazyků.
    S ``diglossic`` se psaný kód ve škole učí jako samostatná vysoká varieta
    a nikdy se neobnovuje (typ arabské diglosie, Ferguson 1959).
    """
    world = village_grid(6, seed=seed, syntax=True, semantics=True)
    groups = tuple(world.group_ids())
    elite = groups[2]
    events: list[WorldEvent] = [Codification(writing, elite, groups, literacy)]
    if school is not None:
        events.append(Schooling(school, groups, diglossic=diglossic))
        if printing and not diglossic:
            events.append(Printing(school, f"written:{elite}"))
    return world, events


def conquest(seed: int = 1, *, year: float = 1000.0) -> tuple[World, list[WorldEvent]]:
    """Dobytí a přechod elity: superstrát (typ Normané v Anglii).

    Čtyři vesnice jazyka ``l`` (prestiž 0,5). V roce ``year`` se mezi nimi
    usadí elita jazyka ``e`` (sto lidí, prestiž 2) a o sto let později se
    začne učit jazyk poddaných. Elita je v menšině, takže nakonec přejde
    sama; v jazyce poddaných po ní zůstanou hlavně slova.
    """
    world = contact_world([
        Language("l", tuple(Place(f"l{index}", ((index % 2) * 10.0, (index // 2) * 10.0),
                                  population=1000, prestige=0.5) for index in range(4))),
        Language("e", (Place("e0", (300.0, 0.0), population=2000, prestige=1.0),),
                 grammar=SUBSTRATE_GRAMMAR,
                 consonants=("t", "k", "s", "n", "m", "l", "ʃ", "f", "x", "v", "r", "j")),
    ], seed=seed)
    events: list[WorldEvent] = [
        Conquest(year, "e0", "l0", ("l0", "l1", "l2", "l3")),
        LanguageShift(year + 100.0, "l0+e0", "l0"),
    ]
    return world, events


def market_town(seed: int = 1, *, start: float = 500.0) -> tuple[World, list[WorldEvent]]:
    """Stabilní dvojjazyčnost: vesnice užívá jazyk trhu jen mimo domov.

    Dvě vesnice jazyka ``a`` a trhové město jazyka ``b``. Od roku ``start``
    se třetina dospělých z pohraniční vesnice ``a1`` domlouvá na trhu jazykem
    ``b``; děti se doma dál učí ``a``.
    """
    world = contact_world([
        Language("a", tuple(Place(f"a{index}", (index * 10.0, 0.0), population=500, prestige=0.5)
                            for index in range(2))),
        Language("b", (Place("b0", (30.0, 0.0), population=3000, prestige=1.0),)),
    ], seed=seed)
    events: list[WorldEvent] = [
        Contact(start, (("a1", "b0"),), 0.5),
        LanguageShift(start, "a1", "b0", initial_share=0.3, domain="public"),
    ]
    return world, events


def migration_region(seed: int = 1, *, migration: float = 0.1) -> World:
    """Město, čtyři trhová městečka a osm vesnic s gravitační migrací.

    Podíl přistěhovalců (a tedy L2 mluvčích) se nenastavuje: vyplyne z toho,
    kam lidé za generaci táhnou.
    """
    places = [Place("city", (0.0, 0.0), population=5000, prestige=1.0)]
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
    places += [Place(f"t{index}", (25.0 * x, 25.0 * y), population=1500, prestige=0.7)
               for index, (x, y) in enumerate(directions)]
    offsets = [(offset, direction) for offset in ((1, 1), (-1, -1)) for direction in directions]
    places += [Place(f"v{index}", (12.0 * dx + 25.0 * x, 12.0 * dy + 25.0 * y), population=300)
               for index, ((dx, dy), (x, y)) in enumerate(offsets)]
    world = contact_world([Language("proto", tuple(places))], seed=seed)
    world.migration = migration
    return world


def conversion(seed: int = 1, *, year: float = 500.0, devotion: float = 0.3) -> tuple[World, list[WorldEvent]]:
    """Náboženská změna: vesnice přijmou víru s cizím liturgickým jazykem.

    Čtyři vesnice jazyka ``v`` a vzdálené náboženské centrum jazyka ``r``,
    jehož řeč se v roce 100 zapíše. V roce ``year`` vesnice přijmou
    náboženství s liturgií v jazyce ``r`` (typ latiny ve střední Evropě);
    přímý kontakt s mluvčími ``r`` nemají.
    """
    world = contact_world([
        Language("v", tuple(Place(f"v{index}", (index * 10.0, 0.0), population=600) for index in range(4))),
        Language("r", (Place("r0", (500.0, 0.0), population=5000, prestige=1.0),),
                 consonants=("t", "k", "s", "n", "m", "l", "r", "f", "x", "kʷ", "j", "d")),
    ], seed=seed)
    villages = tuple(f"v{index}" for index in range(4))
    events: list[WorldEvent] = [
        Codification(100.0, "r0", ("r0",), 0.1),
        ReligiousChange(year, "written:r0", villages, devotion),
    ]
    return world, events


def known_tree(seed: int = 1, *, first: float = 300.0, second: float = 1800.0) -> tuple[World, list[WorldEvent]]:
    """Rozpad jazyka se známou historií pro ověření stromu jazyků.

    Řada devíti vesnic jednoho protojazyka, rozdělená na skupinky A, B a C.
    V roce ``first`` hranice oddělí C od ostatních, v roce ``second`` se
    oddělí A a B. Strom jazyků má vyjít ((A, B), C).
    """
    places = tuple(
        Place(f"{cluster}{index}", ((3 * position + index) * 10.0, 0.0))
        for position, cluster in enumerate("abc")
        for index in range(3)
    )
    world = contact_world([Language("proto", places)], seed=seed)
    side = {cluster: tuple(f"{cluster}{index}" for index in range(3)) for cluster in "abc"}
    events: list[WorldEvent] = [
        Border(first, side["a"] + side["b"], side["c"], factor=0.0),
        Border(second, side["a"], side["b"], factor=0.0),
    ]
    return world, events
