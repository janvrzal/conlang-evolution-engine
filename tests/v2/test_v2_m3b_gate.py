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

SEEDS = (1, 2)
ORIGINS = {
    "shift", "conversion", "derivation", "compound", "circumlocution", "contamination",
    "back_formation", "coinage",
}


@pytest.fixture(scope="module")
def runs():
    result = []
    for seed in SEEDS:
        world = village_grid(8, seed=seed, phonology=True, morphology=True, semantics=True)
        Simulation(world).run(3000)
        result.append(world)
    return result


def _dominant(world, group_id, variable_id):
    return world.variants[world.distribution(group_id, variable_id).dominant()[0]]


def _lexical(world):
    return [(variable_id, variable.key) for variable_id, variable in sorted(world.variables.items())
            if variable.kind == "lexical"]


def test_metrika_1_retence_zakladni_slovni_zasoby_v_pasmu(runs):
    for world in runs:
        per_millennium = statistics.mean(retention(world, group) for group in world.group_ids()) ** (1 / 3)
        assert 0.70 <= per_millennium <= 0.95


def test_metrika_2_caste_pojmy_se_nahrazuji_pomaleji(runs):
    frequent, rare = [], []
    for world in runs:
        for group in world.group_ids():
            for variable_id, concept in _lexical(world):
                replaced = _dominant(world, group, variable_id).origin.change is not None
                (frequent if world.concept_frequency(concept) >= 0.5 else rare).append(replaced)
    assert statistics.mean(frequent) < statistics.mean(rare) / 2


def test_nova_slova_maji_doloditelny_puvod(runs):
    origins = []
    for world in runs:
        for group in world.group_ids():
            for variable_id, _ in _lexical(world):
                variant = _dominant(world, group, variable_id)
                if variant.origin.change is not None:
                    origins.append(variant.payload["origin"])
    assert origins and set(origins) <= ORIGINS
    motivated = sum(origin in {"shift", "conversion", "derivation", "compound"} for origin in origins)
    assert motivated / len(origins) >= 0.6
    assert origins.count("coinage") / len(origins) < 0.3


def test_erodovana_slova_se_nahrazuji_casteji():
    """Kontrolovaný pokus: polovině pojmů se zděděné slovo zkrátí na dvě hlásky."""
    world = village_grid(6, seed=7, phonology=True, morphology=True, semantics=True)
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
    hit, control = [], []
    for group in world.group_ids():
        for variable_id, _ in _lexical(world):
            replaced = _dominant(world, group, variable_id).origin.change is not None
            (hit if variable_id in eroded else control).append(replaced)
    assert statistics.mean(hit) > 2 * statistics.mean(control)


def test_tabu_vyvola_kolobeh_opisu():
    def replacements(taboo):
        world = village_grid(4, seed=5, phonology=True, morphology=True, semantics=True, taboo=taboo)
        simulation = Simulation(world)
        simulation.run(2500)
        return {event["variant"] for event in simulation.history.of_kind("established")
                if event["variable"] == "lexical:dog"}

    assert len(replacements(("dog",))) >= 2
    assert not replacements(())


def test_zvukove_metriky_drzi_i_s_lexikalni_zmenou(runs):
    for world in runs:
        for group in world.group_ids():
            profile = lexicon_profile(world, group)
            assert 3.0 <= profile.mean_length <= 8.0
            assert profile.homophony < 0.05


def test_determinismus_s_vyznamem():
    def run():
        world = village_grid(3, seed=4, phonology=True, morphology=True, semantics=True)
        simulation = Simulation(world)
        simulation.run(1000)
        return simulation.history.digest()

    assert run() == run()
