"""Brána milníku M1 (specifikace, oddíl Milníky).

S1 dialektové kontinuum, metriky 7–9 a 12, determinismus přiblížení a
výkon režimu údolí.
"""

import os
import statistics
import time

import numpy as np
import pytest

from cee.v2.events import Border
from cee.v2.metrics import establishment_fraction, isolation_by_distance, logistic_r2
from cee.v2.repertoire import Distribution, Origin, Variable, Variant
from cee.v2.scenarios import synthetic_concepts, village_grid
from cee.v2.simulation import Simulation, SimulationConfig
from cee.v2.world import Code, SpeechGroup, Territory, World


def run_continuum(seed: int = 2):
    """S1: řada 20 vesnic, 3 000 let, s trajektoriemi pro metriku 7."""
    world = village_grid(20, seed=seed)
    simulation = Simulation(world, SimulationConfig(record_trajectories=True, keep_distances=True))
    simulation.run(3000)
    return world, simulation.history


def run_bordered(seed: int = 2):
    """S1 s hranicí státu mezi 10. a 11. vesnicí od roku 1000."""
    world = village_grid(20, seed=seed)
    ids = world.group_ids()
    simulation = Simulation(world, SimulationConfig(keep_distances=True),
                            events=[Border(1000, tuple(ids[:10]), tuple(ids[10:]), 0.05)])
    simulation.run(3000)
    return simulation.history


def check_s1_kontinuum(world, history):
    snapshot = history.snapshots[-1]
    distances = snapshot.distances
    neighbours = [distances[index, index + 1] for index in range(19)]

    # Žádná ostrá hranice: žádný sousední pár nevyčnívá nad ostatní.
    assert max(neighbours) < 3 * statistics.median(neighbours)
    assert distances[0, 19] > 3 * statistics.mean(neighbours)
    assert len(snapshot.dialects) > 1
    fit = isolation_by_distance(distances, [world.position_of(group) for group in snapshot.group_ids])
    assert fit.correlation > 0.8


def check_s1_hranice(bordered):
    distances = bordered.snapshots[-1].distances
    neighbours = [distances[index, index + 1] for index in range(19)]
    across = neighbours[9]
    others = neighbours[:9] + neighbours[10:]
    assert across > 2 * max(others)


def check_metrika_7(history):
    fits = [
        fit
        for trajectory in history.trajectories.values()
        if trajectory[-1][1] == 1.0
        for fit in [logistic_r2(trajectory)]
        if fit is not None
    ]
    assert len(fits) > 50
    assert statistics.median(fits) > 0.9


def check_metrika_8(history):
    assert 0 < establishment_fraction(history) < 0.2
    assert len(history.of_kind("extinct")) > len(history.of_kind("innovation")) / 2


@pytest.fixture(scope="module")
def continuum():
    return run_continuum(2)


@pytest.fixture(scope="module")
def bordered():
    return run_bordered(2)


def test_s1_kontinuum_je_plynule_a_vzdalenost_roste_se_vzdalenosti(continuum):
    world, history = continuum
    check_s1_kontinuum(world, history)


def test_s1_hranice_vytvori_svazek_izoglos(bordered):
    check_s1_hranice(bordered)


def test_metrika_7_usalene_zmeny_se_siri_po_s_krivce(continuum):
    _, history = continuum
    check_metrika_7(history)


def test_metrika_8_vetsina_inovaci_zanikne(continuum):
    _, history = continuum
    check_metrika_8(history)


# Metrika 9 (Séguyho zákon) se ověřuje v plném modelu na mapě: test_v2_m6b_gate.py.


def test_metrika_12_stejny_seed_da_stejny_log_a_jiny_seed_jiny():
    def digest(seed):
        world = village_grid(6, seed=seed)
        simulation = Simulation(world)
        simulation.run(1000)
        return simulation.history.digest()

    assert digest(4) == digest(4)
    assert digest(4) != digest(5)


def _two_regions(refine_west: bool) -> World:
    world = World(seed=9)
    world.add_territory(Territory("world", "world"))
    base = world.seed_lexicon([f"c{index}" for index in range(40)])
    world.add_territory(Territory("west", "region", parent="world", position=(0.0, 0.0)))
    world.add_territory(Territory("east", "region", parent="world", position=(100.0, 0.0)))
    if refine_west:
        for index in range(2):
            village = f"west-{index}"
            world.add_territory(Territory(village, "settlement", parent="west", position=(index * 10.0, 0)))
            world.add_group(SpeechGroup(village, village, 1_500, [Code("main", base.branch())]))
        world.connect("west-0", "west-1", 0.8, "strong")
    else:
        world.add_group(SpeechGroup("west", "west", 3_000, [Code("main", base.branch())], aggregate=True))
    for index in range(3):
        village = f"east-{index}"
        world.add_territory(Territory(village, "settlement", parent="east", position=(100.0 + index * 10, 0)))
        world.add_group(SpeechGroup(village, village, 500, [Code("main", base.branch())]))
    world.connect("east-0", "east-1", 0.6)
    world.connect("east-1", "east-2", 0.6)
    return world


def test_priblizeni_nezmeni_historii_nepropojene_oblasti():
    """Přepočet od začátku: zjemnění západu nesmí pohnout s východem."""

    def east_history(refine_west):
        world = _two_regions(refine_west)
        simulation = Simulation(world)
        simulation.run(2000)
        east = {group for group in world.groups if group.startswith("east")}
        events = [
            event for event in simulation.history.events
            if event.get("group") in east
            or (event["kind"] == "extinct" and world.variants[event["variant"]].origin.group in east)
        ]
        state = {
            (group, variable): world.distribution(group, variable).as_dict()
            for group in sorted(east) for variable in world.variables
        }
        return events, state

    coarse_events, coarse_state = east_history(False)
    fine_events, fine_state = east_history(True)
    assert coarse_events and coarse_events == fine_events
    assert coarse_state == fine_state


def test_vykon_rezimu_udoli():
    """Údolí: 50 vesnic, 500 pojmů, 2 000 let do 5 s (specifikace).

    ``CEE_PERF_FACTOR`` dovolí pomalejším strojům CI větší rezervu.
    """
    factor = float(os.environ.get("CEE_PERF_FACTOR", "2.0"))
    world = village_grid(10, 5, concepts=synthetic_concepts(500), seed=1)
    started = time.perf_counter()
    Simulation(world).run(2000)
    elapsed = time.perf_counter() - started
    assert elapsed < 5.0 * factor, f"{elapsed:.1f} s"


def _drift(population: int, seed: int = 3) -> float:
    world = World(seed=seed)
    world.add_territory(Territory("world", "world"))
    world.add_territory(Territory("place", "area", parent="world"))
    base = world.seed_lexicon([])
    world.add_group(SpeechGroup("place", "place", population, [Code("main", base.branch())],
                                aggregate=population > 10_000))
    world.live.sync_groups(world)
    for index in range(200):
        variable = Variable("lexical", f"c{index}")
        world.variables[variable.id] = variable
        pair = tuple(sorted(f"{variable.id}/{side}" for side in "ab"))
        for variant_id in pair:
            world.variants[variant_id] = Variant(
                variant_id, variable.id, {}, Origin("test", 0, 0.0, "place")
            )
        world.live.load(variable.id, [Distribution(pair, np.array([0.5, 0.5]))])
    Simulation(world, changes=()).run(1000)
    return float(np.mean([
        abs(world.distribution("place", variable).frequency(f"{variable}/a") - 0.5)
        for variable in world.variables
    ]))


def run_drift_pair(seed: int = 3) -> tuple[float, float]:
    return _drift(1_000_000, seed=seed), _drift(200, seed=seed)


def check_velka_souhrnna_skupina(drift_large: float, drift_small: float):
    assert drift_large < 0.01 < drift_small


def test_velka_souhrnna_skupina_driftuje_mene_nez_mala_vesnice():
    """Neutrální varianty 50 : 50 bez inovací a tlaků: zbývá jen drift."""
    drift_large, drift_small = run_drift_pair(3)
    check_velka_souhrnna_skupina(drift_large, drift_small)
