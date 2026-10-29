"""Průběžné výsledky a checkpointy enginu v2 (milník M6d)."""

import pytest

from cee.v2.events import Border, Contact
from cee.v2.export import export, frame
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation, SimulationConfig


def _world():
    return village_grid(4, seed=3, syntax=True, semantics=True)


EVENTS = (Border(300.0, ("v00-00", "v00-01"), ("v00-02", "v00-03"), 0.2),)


def test_pokracovani_z_checkpointu_je_bitove_stejne():
    straight = Simulation(_world(), events=EVENTS)
    straight.run(700)
    stopped = Simulation(_world(), events=EVENTS)
    stopped.run(400)
    resumed = Simulation.resume(stopped.checkpoint(), EVENTS)
    resumed.run(700)
    assert resumed.history.digest() == straight.history.digest()
    assert export(resumed) == export(straight)


def test_branch_prepocita_jen_od_zmenene_udalosti():
    changed = (Border(300.0, ("v00-00", "v00-01"), ("v00-02", "v00-03"), 0.2),
               Contact(500.0, (("v00-00", "v00-03"),), 0.3))
    reference = Simulation(_world(), events=changed)
    reference.run(700)
    original = Simulation(_world(), SimulationConfig(checkpoint_every=100.0), events=EVENTS)
    original.run(700)
    branch = original.branch(changed)
    assert 400.0 <= branch.year < 500.0  # poslední checkpoint před změnou
    branch.run(700)
    assert branch.history.digest() == reference.history.digest()


def test_checkpoint_je_nezavisly_na_dalsim_behu():
    simulation = Simulation(_world(), events=EVENTS)
    simulation.run(200)
    point = simulation.checkpoint()
    simulation.run(500)
    first, second = Simulation.resume(point, EVENTS), Simulation.resume(point, EVENTS)
    first.run(500)
    second.run(500)
    assert first.history.digest() == second.history.digest() == simulation.history.digest()


def test_branch_bez_checkpointu_pred_zmenou_selze():
    simulation = Simulation(_world(), SimulationConfig(checkpoint_every=500.0), events=EVENTS)
    simulation.run(600)
    with pytest.raises(ValueError):
        simulation.branch((Border(100.0, ("v00-00",), ("v00-01",), 0.5),))


def test_iterace_vraci_kazdy_krok_a_snimek_pro_ui():
    simulation = Simulation(_world())
    years = [frame(step)["year"] for step in simulation.iterate(200)]
    assert years == [25.0 * index for index in range(1, 9)]
    last = frame(simulation)
    assert len(last["groups"]) == 4 and last["languages"]
