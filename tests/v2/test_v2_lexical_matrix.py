"""Rozptyl hromadných skóre lexikální jasnosti do buněk (proměnná × skupina × slot)."""

import numpy as np
from test_v2_lexical_index import oracle

from cee.v2.pressures.base import PressureBatch
from cee.v2.pressures.lexical import LexicalClarity
from cee.v2.repertoire import Origin, Variant
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation


def test_lexical_clarity_scatter_matches_cell_reference() -> None:
    world = village_grid(3, seed=3, semantics=True)
    Simulation(world)
    group_ids = tuple(world.group_ids())
    codes = [world.groups[group].main_code for group in group_ids]
    concepts = list(codes[0].phonology.dominant)[:2]
    variants = {
        concept: [
            variant.id for variant in world.variants.values()
            if variant.variable == f"lexical:{concept}" and "morpheme" in variant.payload
        ]
        for concept in concepts
    }
    assert all(len(found) >= 2 for found in variants.values())
    plain = "variant:plain"
    world.variants[plain] = Variant(plain, f"lexical:{concepts[0]}", {"appeal": 0.2}, Origin(None, 0, 0.0, None))
    slots = tuple((*found[:2], None, plain) for found in variants.values())
    freqs = np.zeros((2, 3, 4))
    heard = np.zeros_like(freqs)
    freqs[0, 0, 0] = 0.2
    heard[0, 1, 0] = 0.3  # dosažení pouze přes slyšení
    freqs[0, 0, 1] = 0.4
    freqs[0, 2, 3] = 0.5  # slot bez morfému zůstane nulový
    heard[1, 1, 0] = 0.6
    freqs[1, 2, 1] = 0.7
    freqs[1, 0, 2] = 0.8  # prázdný slot
    heard[1, 1, 2] = 0.9
    batch = PressureBatch(
        world=world, variable_ids=tuple(f"lexical:{concept}" for concept in concepts), group_ids=group_ids,
        freqs=freqs, slots=slots, tick=0, heard=heard,
    )
    actual = LexicalClarity().scores(batch)

    expected = np.zeros_like(freqs)
    reached = (freqs > 0) | (heard > 0)
    for row, concept in enumerate(concepts):
        for slot, variant in enumerate(slots[row]):
            if variant is None or "morpheme" not in world.variants[variant].payload:
                continue
            morpheme = world.variants[variant].payload["morpheme"]
            for column in range(3):
                if reached[row, column, slot]:
                    expected[row, column, slot] = oracle(world, codes[column], morpheme, concept)

    np.testing.assert_array_equal(actual, expected)
    assert np.count_nonzero(reached[:, :, :2]) > 0
    assert actual[0, 2, 3] == 0  # slot bez morfému
    assert actual[1, 0, 2] == 0  # prázdný slot
