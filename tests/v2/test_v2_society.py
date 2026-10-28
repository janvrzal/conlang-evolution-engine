"""Společnost enginu v2 (milník M6b): události, migrace a vitalita jazyka."""

import pytest

from cee.v2 import contact
from cee.v2.events import (
    Codification,
    Conquest,
    Epidemic,
    Migration,
    ReligiousChange,
    Schooling,
    StateCollapse,
    War,
)
from cee.v2.history import History
from cee.v2.scenarios import conquest, conversion, migration_region, village_grid
from cee.v2.simulation import Simulation


def test_migrace_do_noveho_sidla_ho_zalozi_s_vazbami_a_l2_mluvcimi():
    world = village_grid(3, seed=1, phonology=True)
    Simulation(world)
    Migration(0.0, (("v00-00", 0.2), ("v00-01", 0.1)), "colony", position=(5.0, 8.0)).apply(world, History(), 0)
    colony = world.groups["colony"]
    assert colony.population == 150 and world.groups["v00-00"].population == 400
    assert world.neighbors("colony")
    assert abs(colony.main_code.l2_share - 50 / 150) < 1e-9
    assert colony.main_code.phonology.vocabulary == world.groups["v00-00"].main_code.phonology.vocabulary


def test_migrace_do_existujiciho_sidla_zvysi_podil_l2():
    world = village_grid(2, seed=1)
    Migration(0.0, (("v00-00", 0.5),), "v00-01").apply(world, History(), 0)
    target = world.groups["v00-01"]
    assert target.population == 750 and abs(target.main_code.l2_share - 250 / 750) < 1e-9


def test_valka_epidemie_a_kolaps():
    world = village_grid(4, seed=1, link_reach=4.0)
    War(0.0, ("v00-00", "v00-01"), ("v00-02", "v00-03"), factor=0.5, losses=0.2).apply(world, History(), 0)
    assert world.groups["v00-00"].population == 400
    before = world.links[("v00-01", "v00-03")].strength
    Epidemic(0.0, ("v00-03",), mortality=0.5).apply(world, History(), 0)
    assert world.groups["v00-03"].population == 200
    world.groups["v00-00"].schooling, world.groups["v00-00"].literacy = 0.8, 0.5
    StateCollapse(0.0, ("v00-00",), reach=15.0).apply(world, History(), 0)
    assert ("v00-00", "v00-02") not in world.links and ("v00-00", "v00-01") in world.links
    assert world.groups["v00-00"].schooling == 0.0 and world.groups["v00-00"].literacy == 0.1
    assert before > 0


def test_dobyti_usadi_elitu_s_prestizi_a_vazbami():
    world, _ = conquest(1)
    Conquest(0.0, "e0", "l0", ("l0", "l1")).apply(world, History(), 0)
    elite = world.groups["l0+e0"]
    assert elite.territory == "l0" and elite.prestige == 2.0 and elite.main_code.language == "e"
    assert {link.target for link in world.neighbors(elite.id)} == {"e0", "l0", "l1"}


def test_demografie_prechodu_se_pocita_z_lidi_se_kterymi_komunita_mluvi():
    world, events = conquest(1)
    simulation = Simulation(world, events=events)
    simulation.run(1100)
    # Elita je stovka lidí uprostřed tisíců poddaných: jazyk poddaných slyší
    # skoro všude, i když v ní samotné ho zatím mluví jen pár lidí.
    elite, learners = world.groups["l0+e0"], world.groups["l0+e0>l"]
    inside = learners.population / (elite.population + learners.population)
    assert inside < 0.3 < 0.7 < contact.demographic_share(world, "l0+e0", "l0+e0>l")


def test_migrace_urci_podil_pristehovalcu_podle_pritazlivosti():
    world = migration_region(1)
    contact.community_step(world, 25.0, 1, 25.0, History())
    immigration = {group: world.groups[group].immigration for group in world.group_ids()}
    assert immigration["city"] == max(immigration.values()) > 0
    assert min(immigration.values()) >= 0


def test_bez_migrace_se_pristehovalectvi_nemeni():
    world = migration_region(1, migration=0.0)
    contact.community_step(world, 25.0, 1, 25.0, History())
    assert all(world.groups[group].immigration == 0.0 for group in world.group_ids())


def test_diglosni_skola_zalozi_vysokou_varietu_a_lidova_rec_skolou_neprochazi():
    world = village_grid(3, seed=1, syntax=True, semantics=True)
    groups = tuple(world.group_ids())
    Codification(0.0, "v00-01", groups).apply(world, History(), 0)
    Schooling(0.0, groups, schooling=0.5, diglossic=True).apply(world, History(), 0)
    for group in groups:
        high = world.groups[f"{group}>H"]
        assert high.domain == "public" and high.schooling == 1.0 and high.standard == "written:v00-01"
        assert high.main_code.l1_source == group and high.population == 250
        assert world.groups[group].schooling == 0.0 and world.groups[group].literacy == 0.8
    assert ("v00-00>H", "v00-01>H") in world.links


def test_liturgicky_kod_musi_byt_psany():
    world, _ = conversion(1)
    with pytest.raises(ValueError):
        ReligiousChange(0.0, "r0", ("v0",)).apply(world, History(), 0)
