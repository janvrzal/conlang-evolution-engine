"""Brána milníku M3 (specifikace, oddíl Milníky): morfologie.

Kontinuum osmi vesnic s podstatnými jmény (singulár, plurál) a slovesy
(prézens, préteritum), dva seedy, 3 000 let; pro Sturtevantův paradox
navíc tentýž běh bez vyrovnání.
"""

import statistics

import pytest

from cee.v2 import morphology
from cee.v2.changes import DEFAULT_CHANGES
from cee.v2.metrics import lexicon_profile, morphology_profile
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation

SEEDS = (1, 2)


def _run(seed, changes=DEFAULT_CHANGES):
    world = village_grid(8, seed=seed, phonology=True, morphology=True)
    simulation = Simulation(world, changes=changes)
    simulation.run(3000)
    return world, simulation.history


@pytest.fixture(scope="module")
def runs():
    return [_run(seed) for seed in SEEDS]


@pytest.fixture(scope="module")
def without_leveling():
    changes = tuple(change for change in DEFAULT_CHANGES if change.kind != "leveling")
    return [_run(seed, changes) for seed in SEEDS]


def _mean(world, attribute):
    return statistics.mean(
        getattr(morphology_profile(world, group), attribute) for group in world.group_ids()
    )


def test_sturtevantuv_paradox_zvuk_tvori_nepravidelnost_analogie_ji_opravuje(runs, without_leveling):
    for (world, _), (unleveled, _) in zip(runs, without_leveling):
        assert _mean(unleveled, "alternation") > 0.3  # zvukové změny vyrobily alternace
        assert _mean(world, "alternation") < _mean(unleveled, "alternation") - 0.1


def test_morfologizace_vznikne_sama(runs):
    """Plurál nesený jen kmenem: koncovka zanikla, alternace zůstala."""
    assert all(_mean(world, "morphologized") > 0.02 for world, _ in runs)


def test_produktivni_vzor_se_siri_a_caste_slova_si_drzi_nepravidelnost(runs):
    frequent, rare = [], []
    for world, _ in runs:
        assert _mean(world, "productive_share") > 0.8  # z výchozích 65 %
        for group in world.group_ids():
            profile = morphology_profile(world, group)
            frequent.append(profile.irregular_frequent)
            rare.append(profile.irregular_rare)
    assert statistics.mean(frequent) > statistics.mean(rare)


def test_analogie_zasahuje_spis_vzacna_slova(runs):
    for world, history in runs:
        analogized = [
            world.morphemes[world.morphemes[unit].lexeme_id].frequency
            for unit in (
                world.form_changes[event["variable"]].unit for event in history.of_kind("analogy")
            )
        ]
        vocabulary = [
            morpheme.frequency for morpheme in world.morphemes.values()
            if morpheme.kind == "root" and morpheme.word_class is not None
        ]
        assert statistics.mean(analogized) < statistics.mean(vocabulary)


def test_zvukove_metriky_drzi_i_s_paradigmaty(runs):
    for world, _ in runs:
        for group in world.group_ids():
            profile = lexicon_profile(world, group)
            assert 3.0 <= profile.mean_length <= 8.0
            assert profile.homophony < 0.05


def test_determinismus_s_morfologii():
    def run():
        world = village_grid(3, seed=4, phonology=True, morphology=True)
        simulation = Simulation(world)
        simulation.run(1000)
        code = world.groups[world.group_ids()[0]].main_code
        forms = {unit: world.form_of(code, unit) for unit in sorted(code.phonology.vocabulary)}
        return simulation.history.digest(), forms, morphology.class_stats(world, code).endings

    assert run() == run()
