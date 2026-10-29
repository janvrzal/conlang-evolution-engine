"""Brána milníku M3b (specifikace, oddíl Milníky): lexikon a význam.

Kontinuum osmi vesnic s fonologií, paradigmaty a grafem pojmů, dva seedy,
3 000 let; k tomu kontrolované pokusy s erozí a tabu.
"""

import statistics

import pytest

from cee.v2.language.lexicon import UnitForm
from cee.v2.metrics import lexicon_profile, retention
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation
from tests.v2.gate_checks import evaluate_seeds

SEEDS = (1, 2)
TABOO_SEEDS = tuple(range(1, 13))
ORIGINS = {
    "shift", "conversion", "derivation", "compound", "circumlocution", "contamination",
    "back_formation", "coinage",
}


def _dominant(world, group_id, variable_id):
    return world.variants[world.distribution(group_id, variable_id).dominant()[0]]


def _lexical(world):
    return [(variable_id, variable.key) for variable_id, variable in sorted(world.variables.items())
            if variable.kind == "lexical"]


def run_m3b(seed: int):
    world = village_grid(8, seed=seed, phonology=True, morphology=True, semantics=True)
    Simulation(world).run(3000)
    return world


def run_eroded(seed: int = 7):
    """Kontrolovaný pokus: polovině pojmů se zděděné slovo zkrátí na dvě hlásky."""
    world = village_grid(6, seed=seed, phonology=True, morphology=True, semantics=True)
    eroded = set()
    for index, (variable_id, concept) in enumerate(_lexical(world)):
        if index % 2:
            continue
        root = world.stored(world.group_ids()[0], variable_id)
        morpheme = world.variants[root.variants[0]].payload["morpheme"]
        form = world.morphemes[morpheme].form
        if len(form) < 4:
            continue
        eroded.add(variable_id)
        for group in world.groups.values():
            group.main_code.forms.set(morpheme, UnitForm(form[:2], None, None))
            group.main_code.phonology.version += 1
    Simulation(world).run(1500)
    return world, eroded


def _taboo_replacements(taboo, seed: int = 5):
    world = village_grid(4, seed=seed, phonology=True, morphology=True, semantics=True, taboo=taboo)
    simulation = Simulation(world)
    simulation.run(2500)
    return {event["variant"] for event in simulation.history.of_kind("established")
            if event["variable"] == "lexical:dog"}


def run_taboo_pair(seed: int = 5):
    return _taboo_replacements(("dog",), seed=seed), _taboo_replacements((), seed=seed)


def check_metrika_1(world):
    per_millennium = statistics.mean(retention(world, group) for group in world.group_ids()) ** (1 / 3)
    assert 0.70 <= per_millennium <= 0.95


def check_metrika_2(worlds_seq):
    frequent, rare = [], []
    for world in worlds_seq:
        for group in world.group_ids():
            for variable_id, concept in _lexical(world):
                replaced = _dominant(world, group, variable_id).origin.change is not None
                (frequent if world.concept_frequency(concept) >= 0.5 else rare).append(replaced)
    assert statistics.mean(frequent) < statistics.mean(rare) / 2


def check_nova_slova(worlds_seq):
    origins = []
    for world in worlds_seq:
        for group in world.group_ids():
            for variable_id, _ in _lexical(world):
                variant = _dominant(world, group, variable_id)
                if variant.origin.change is not None:
                    origins.append(variant.payload["origin"])
    assert origins and set(origins) <= ORIGINS
    motivated = sum(origin in {"shift", "conversion", "derivation", "compound"} for origin in origins)
    assert motivated / len(origins) >= 0.6
    assert origins.count("coinage") / len(origins) < 0.3


def check_erodovana_slova(world, eroded):
    hit, control = [], []
    for group in world.group_ids():
        for variable_id, _ in _lexical(world):
            replaced = _dominant(world, group, variable_id).origin.change is not None
            (hit if variable_id in eroded else control).append(replaced)
    assert statistics.mean(hit) > 2 * statistics.mean(control)


def check_tabu(with_taboo, without_taboo):
    assert len(with_taboo) >= 2
    assert not without_taboo


def check_zvukove_metriky(world):
    for group in world.group_ids():
        profile = lexicon_profile(world, group)
        assert 3.0 <= profile.mean_length <= 8.0
        assert profile.homophony < 0.05


@pytest.fixture(scope="module")
def runs():
    return [run_m3b(seed) for seed in SEEDS]


def test_metrika_1_retence_zakladni_slovni_zasoby_v_pasmu(runs):
    for world in runs:
        check_metrika_1(world)


def test_metrika_2_caste_pojmy_se_nahrazuji_pomaleji(runs):
    check_metrika_2(runs)


def test_nova_slova_maji_doloditelny_puvod(runs):
    check_nova_slova(runs)


def test_erodovana_slova_se_nahrazuji_casteji():
    world, eroded = run_eroded(7)
    check_erodovana_slova(world, eroded)


@pytest.fixture(scope="module")
def taboo_runs():
    return {seed: run_taboo_pair(seed) for seed in TABOO_SEEDS}


def test_tabu_vyvola_kolobeh_opisu(taboo_runs):
    # Brána existence (otevřená otázka do M7). Audit 101..120: 11/20, Wilson 95 % [0.342, 0.742], N=12, k=1, negativní kontrola (taboo=()) 0/12.
    evaluate_seeds(taboo_runs, lambda pair: check_tabu(*pair), k=1)


def test_zvukove_metriky_drzi_i_s_lexikalni_zmenou(runs):
    for world in runs:
        check_zvukove_metriky(world)


def test_determinismus_s_vyznamem():
    def run():
        world = village_grid(3, seed=4, phonology=True, morphology=True, semantics=True)
        simulation = Simulation(world)
        simulation.run(1000)
        return simulation.history.digest()

    assert run() == run()
