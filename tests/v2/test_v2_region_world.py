"""Regiony jako sítě vesnic (scénář ``region_world``)."""

from __future__ import annotations

import numpy as np
import pytest

from cee.v2.observe import code_distances
from cee.v2.parameters import Parameters
from cee.v2.scenarios import Region, region_world
from cee.v2.simulation import Simulation

CHAIN = (
    Region("a", (0.0, 0.0), density=2.0, neighbours=("b",)),
    Region("b", (40.0, 0.0), neighbours=("a", "c")),
    Region("c", (80.0, 0.0), density=0.5, neighbours=("b",), villages=3),
)
PAIR = (Region("a", (0.0, 0.0), neighbours=("b",)), Region("b", (40.0, 0.0), neighbours=("a",)))


def _region(world, group_id):
    return world.territories[group_id].parent


def test_vesnice_hustota_a_uzemi():
    world = region_world(CHAIN)
    assert sorted(world.group_ids()) == [*(f"a-v{i}" for i in range(4)), *(f"b-v{i}" for i in range(4)),
                                         *(f"c-v{i}" for i in range(3))]
    assert world.territories["a"].level == "region"
    assert world.groups["a-v0"].population == 1000
    assert world.groups["b-v1"].population == 500
    assert world.groups["c-v2"].population == 250
    dense = region_world(CHAIN, params=Parameters(population_per_density=200.0))
    assert dense.groups["a-v0"].population == 400


def test_regiony_spojuji_jen_pohranicni_vesnice():
    world = region_world(CHAIN)
    crossing = sorted({tuple(sorted((link.source, link.target))) for link in world.links.values()
                       if _region(world, link.source) != _region(world, link.target)})
    regions = [tuple(sorted((_region(world, a), _region(world, b)))) for a, b in crossing]
    assert sorted(regions) == [("a", "b"), ("b", "c")]
    # Uvnitř regionu je každá vesnice spojená aspoň s jednou jinou.
    for group_id in world.group_ids():
        assert any(_region(world, link.target) == _region(world, group_id) for link in world.neighbors(group_id))


def test_neplatne_regiony_se_odmitnou():
    with pytest.raises(ValueError, match="neznámými"):
        region_world([Region("a", (0.0, 0.0), neighbours=("x",))])
    with pytest.raises(ValueError, match="jedinečná"):
        region_world([Region("a", (0.0, 0.0)), Region("a", (40.0, 0.0))])
    with pytest.raises(ValueError, match="hustotu"):
        region_world([Region("a", (0.0, 0.0), density=0.0)])


def test_stejny_seed_da_stejnou_historii():
    def digest():
        simulation = Simulation(region_world(PAIR, seed=3, phonology=True))
        simulation.run(300)
        return simulation.history.digest()

    assert digest() == digest()


def test_hranice_regionu_brzdi_sireni():
    """Po 1 500 letech jsou si vesnice téhož regionu bližší než vesnice přes hranici."""
    world = region_world(PAIR, seed=2, phonology=True)
    Simulation(world).run(1500)
    distances = code_distances(world)
    ids = world.live.group_ids
    same, across = [], []
    for i, first in enumerate(ids):
        for j in range(i + 1, len(ids)):
            (same if _region(world, first) == _region(world, ids[j]) else across).append(distances[i, j])
    assert np.mean(same) < np.mean(across)
