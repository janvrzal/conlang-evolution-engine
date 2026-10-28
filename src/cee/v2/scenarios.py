"""Hotové světy pro validační scénáře a benchmarky (specifikace, S1–S5)."""

from __future__ import annotations

from typing import Mapping, Sequence

from cee.data.core_vocabulary import CORE_EXTENSION, SWADESH_CORE
from cee.v2.language.constructions import GRAMMATICAL_SOURCES, Construction, catalog
from cee.v2.language.morphology import Paradigm
from cee.v2.language.protoforms import protolanguage
from cee.v2.repertoire import Distribution, Origin, Repertoire
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
