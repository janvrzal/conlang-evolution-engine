"""Hotové světy pro validační scénáře a benchmarky (specifikace, S1–S5)."""

from __future__ import annotations

from typing import Sequence

from cee.data.core_vocabulary import CORE_EXTENSION, SWADESH_CORE
from cee.v2.language.protoforms import protolanguage
from cee.v2.world import Code, SpeechGroup, Territory, World, gravity_links

DEFAULT_CONCEPTS: tuple[str, ...] = tuple(dict.fromkeys((*SWADESH_CORE, *CORE_EXTENSION)))


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
) -> World:
    """Mřížka stejných vesnic s gravitačními vazbami na nejbližší sousedy.

    S jedním řádkem je to scénář S1 (dialektové kontinuum). Vazby sahají jen
    do ``link_reach`` násobku rozestupu, takže vzdálené vesnice spolu mluví
    jen přes prostředníky. S ``phonology`` dostanou slova hláskové tvary
    vygenerovaného protojazyka (M2).
    """
    world = World(seed=seed)
    world.add_territory(Territory("world", "world"))
    world.add_territory(
        Territory("valley", "area", parent="world",
                  position=((columns - 1) * spacing / 2, (rows - 1) * spacing / 2))
    )
    if phonology:
        forms, frequencies = protolanguage(concepts, seed=seed)
        base = world.seed_lexicon(concepts, forms, frequencies)
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
