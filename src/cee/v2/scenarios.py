"""Hotové světy pro validační scénáře a benchmarky (specifikace, S1–S5)."""

from __future__ import annotations

from typing import Sequence

from cee.data.core_vocabulary import CORE_EXTENSION, SWADESH_CORE
from cee.v2.language.morphology import Paradigm
from cee.v2.language.protoforms import protolanguage
from cee.v2.world import Code, SpeechGroup, Territory, World, gravity_links

DEFAULT_CONCEPTS: tuple[str, ...] = tuple(dict.fromkeys((*SWADESH_CORE, *CORE_EXTENSION)))


#: Slovesa základní slovní zásoby; ostatní ohebná slova jsou podstatná jména.
VERBS = frozenset("""
drink eat bite see hear know sleep die kill swim fly walk come lie sit stand give say burn
speak write read work make carry open close
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
) -> World:
    """Mřížka stejných vesnic s gravitačními vazbami na nejbližší sousedy.

    S jedním řádkem je to scénář S1 (dialektové kontinuum). Vazby sahají jen
    do ``link_reach`` násobku rozestupu, takže vzdálené vesnice spolu mluví
    jen přes prostředníky. S ``phonology`` dostanou slova hláskové tvary
    vygenerovaného protojazyka (M2), s ``morphology`` navíc podstatná jména
    plurál a slovesa minulý čas (M3).
    """
    world = World(seed=seed)
    world.add_territory(Territory("world", "world"))
    world.add_territory(
        Territory("valley", "area", parent="world",
                  position=((columns - 1) * spacing / 2, (rows - 1) * spacing / 2))
    )
    if morphology:
        world.paradigms.update(PROTO_PARADIGMS)
    if phonology or morphology:
        forms, frequencies = protolanguage(concepts, seed=seed)
        classes = (
            {concept: found for concept in concepts if (found := word_class(concept)) is not None}
            if morphology else None
        )
        base = world.seed_lexicon(
            concepts, forms, frequencies, classes, PROTO_ENDINGS if morphology else None
        )
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
                )
            )
    gravity_links(world, max_distance=spacing * link_reach)
    return world
