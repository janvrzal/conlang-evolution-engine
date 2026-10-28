"""Jednotkové testy stavebních kamenů enginu v2 (milník M1)."""

import numpy as np
import pytest

from cee.v2.events import Border, RefineTerritory, SettlementSpec
from cee.v2.history import History
from cee.v2.pools import LivePools
from cee.v2.repertoire import Distribution, Repertoire
from cee.v2.rng import hash_normal, stable_id, stable_int
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation, SimulationConfig
from cee.v2.world import Code, SpeechGroup, Territory, World, gravity_links


def _world_with(groups, concepts=("water", "fire")):
    world = World(seed=7)
    world.add_territory(Territory("world", "world"))
    base = world.seed_lexicon(concepts)
    for index, (group_id, kwargs) in enumerate(groups.items()):
        world.add_territory(
            Territory(group_id, "settlement", parent="world", position=(index * 10.0, 0.0))
        )
        world.add_group(SpeechGroup(group_id, group_id, codes=[Code("main", base.branch())], **kwargs))
    return world


def test_stabilni_id_a_seedy_se_nemeni_a_neslevaji_casti():
    assert stable_int("ab", "c") == stable_int("ab", "c")
    assert stable_int("ab", "c") != stable_int("a", "bc")
    assert stable_id("variant", 1, "x") == stable_id("variant", 1, "x")


def test_hashovany_sum_je_normalni_a_zavisi_jen_na_paru_klicu():
    rows = np.arange(200, dtype=np.uint64) * np.uint64(7919)
    columns = np.arange(300, dtype=np.uint64) * np.uint64(104729)
    matrix = hash_normal(rows, columns)
    assert abs(matrix.mean()) < 0.02
    assert abs(matrix.std() - 1.0) < 0.02
    # Jiný počet sloupců nezmění hodnoty těch ostatních.
    assert np.array_equal(hash_normal(rows[:5], columns[:3]), matrix[:5, :3])
    assert np.array_equal(hash_normal(rows[:5], columns[:5], pairwise=True), np.diag(matrix[:5, :5]))


def test_repertoar_je_copy_on_write():
    parent = Repertoire()
    parent.set("lexical:water", Distribution.fixed("a"))
    child = parent.branch()
    child.set("lexical:water", Distribution.fixed("b"))
    parent.set("lexical:fire", Distribution.fixed("c"))

    assert parent.get("lexical:water").variants == ("a",)
    assert child.get("lexical:water").variants == ("b",)
    assert child.get("lexical:fire") is None
    assert parent.variable_ids() == ["lexical:fire", "lexical:water"]
    with pytest.raises(RuntimeError):
        Repertoire().freeze().set("x", Distribution.fixed("a"))


def test_inovace_vstoupi_s_podilem_a_bez_trendu():
    distribution = Distribution.fixed("old").with_innovation("new", 0.02)
    assert distribution.as_dict() == pytest.approx({"new": 0.02, "old": 0.98})
    assert np.array_equal(distribution.previous, distribution.freqs)


def test_zivy_sklad_vraci_ustalene_promenne_do_repertoaru():
    pools = LivePools(["a", "b"])
    pools.load("lexical:water", [Distribution.fixed("old"), Distribution.fixed("old")])
    pools.innovate("lexical:water", "a", "new", 0.5)
    assert pools.get("a", "lexical:water").as_dict() == pytest.approx({"new": 0.5, "old": 0.5})
    assert pools.release() == []

    (block,) = pools.iter_blocks()
    block.freqs = np.array([[[1.0, 0.0], [1.0, 0.0]]])
    (released,) = pools.release()
    assert released[0] == "lexical:water"
    assert [item.variants for item in released[1]] == [("old",), ("old",)]
    assert len(pools) == 0


def test_gravitacni_vazby_slabnou_se_vzdalenosti():
    world = _world_with({"a": {"population": 500}, "b": {"population": 500}, "c": {"population": 500}})
    gravity_links(world)
    assert world.links[("a", "b")].strength == world.links[("b", "a")].strength
    assert world.links[("a", "b")].strength > world.links[("a", "c")].strength
    assert gravity_links(_world_with({"x": {"population": 1}}), max_distance=1.0) == 0


def test_krok_nesmi_byt_delsi_nez_nejkratsi_generace():
    world = _world_with({"elves": {"population": 100, "generation_years": 20}})
    with pytest.raises(ValueError, match="generace"):
        Simulation(world)


def test_strom_uzemi_hlida_urovne():
    world = World(seed=1)
    world.add_territory(Territory("world", "world"))
    world.add_territory(Territory("north", "region", parent="world"))
    with pytest.raises(ValueError, match="níž"):
        world.add_territory(Territory("planet", "world", parent="north"))
    assert world.territories["world"].children == ["north"]


def test_hranice_oslabi_jen_vazby_pres_hranici():
    world = village_grid(4, seed=1)
    ids = world.group_ids()
    before = world.links[(ids[1], ids[2])].strength
    inside = world.links[(ids[0], ids[1])].strength
    history = History()
    Border(0, (ids[0], ids[1]), (ids[2], ids[3]), 0.1).apply(world, history, 0)
    assert world.links[(ids[1], ids[2])].strength == pytest.approx(before * 0.1)
    assert world.links[(ids[2], ids[1])].strength == pytest.approx(before * 0.1)
    assert world.links[(ids[0], ids[1])].strength == inside
    # Vazby sahají ob jednu vesnici: přes hranici vedou 0–2, 1–2 a 1–3.
    assert history.of_kind("border")[0]["weakened_links"] == 3


def _region_world(seed=5):
    world = World(seed=seed)
    world.add_territory(Territory("world", "world"))
    world.add_territory(Territory("coast", "region", parent="world", position=(0.0, 0.0)))
    base = world.seed_lexicon([f"c{index}" for index in range(30)])
    world.add_group(
        SpeechGroup("coast", "coast", population=4_000, aggregate=True, codes=[Code("main", base.branch())])
    )
    world.add_territory(Territory("hills", "settlement", parent="world", position=(15.0, 0.0)))
    world.add_group(SpeechGroup("hills", "hills", population=500, codes=[Code("main", base.branch())]))
    world.connect("coast", "hills", 0.5)
    return world


def test_zjemneni_od_roku_x_preda_repertoar_populaci_a_vazby():
    world = _region_world()
    settlements = (SettlementSpec("port", 3.0, (0.0, 0.0)), SettlementSpec("cove", 1.0, (5.0, 0.0)))
    simulation = Simulation(world, events=[RefineTerritory(250, "coast", settlements)])
    simulation.run(225)
    before = {variable: world.distribution("coast", variable) for variable in world.variables}
    simulation.run(250)

    assert "coast" not in world.groups
    assert world.groups["port"].population == 3_000
    assert world.groups["cove"].population == 1_000
    assert world.links[("port", "cove")].kind == "strong"
    assert world.links[("cove", "hills")].strength == 0.5
    assert world.territories["port"].refined_from_year == 250
    assert simulation.history.of_kind("refinement")[0]["groups"] == ["port", "cove"]
    # Sídla začínají se stavem souhrnné skupiny z předchozího kroku.
    for variable, distribution in before.items():
        assert world.distribution("port", variable).variants or distribution is None


def test_delsi_generace_meni_jazyk_pomaleji():
    def replaced(generation_years):
        world = village_grid(3, seed=11, generation_years=generation_years)
        Simulation(world, SimulationConfig(dt=25.0)).run(1500)
        return sum(
            world.variants[world.distribution(group_id, variable).dominant()[0]].origin.change
            is not None
            for group_id in world.group_ids()
            for variable in world.variables
        )

    # Lexikální inovace se řídí kalendářním časem, šíření ale generacemi:
    # národ s pětisetletou generací nová slova zkouší stejně často, jen se
    # mu v populaci téměř neprosadí.
    assert replaced(500.0) < replaced(25.0)
