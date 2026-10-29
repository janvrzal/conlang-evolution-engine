"""Brána milníku M4 (specifikace, oddíl Milníky): syntax a gramatikalizace.

Přirozená eroze konkrétní koncovky je v simulaci vzácná (viz Známé mezery),
proto se odpověď syntaxe ověřuje kontrolovanými pokusy: na začátku se
koncovka nebo záporka oslabí a sleduje se, co jazyk udělá.
"""

import statistics
from collections import Counter

import pytest

from cee.v2 import morphology, syntax
from cee.v2.language.constructions import PATHWAYS
from cee.v2.language.lexicon import UnitForm
from cee.v2.metrics import lexicon_profile
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation
from tests.v2.gate_checks import evaluate_seeds

VELKY_CYKLUS_SEEDS = tuple(range(1, 11))
JESPERSEN_SEEDS = tuple(range(1, 20))


def _experiment(seed=3, *, cell=None, particle=None):
    world = village_grid(6, seed=seed, syntax=True, semantics=True)
    simulation = Simulation(world)
    for group in world.groups.values():
        code = group.main_code
        if cell is not None:
            for unit in sorted(code.phonology.vocabulary):
                if world.morphemes[unit].cell == cell:
                    citation = morphology.citation_form(world, code, unit)
                    code.forms.set(unit, UnitForm(citation, len(citation), world.unit_of(code, unit).exponent))
        if particle is not None:
            # Záporka obroušená na samotnou samohlásku.
            root = code.phonology.dominant[particle]
            vowel = next(segment for segment in world.form_of(code, root) if world.table.is_vowel(segment))
            code.forms.set(root, UnitForm((vowel,), None, None))
        code.phonology.version += 1
    return world, simulation


def _kinds(world, function):
    return Counter(syntax.dominant(world, group, function).kind for group in world.group_ids())


def run_control(seed: int = 3):
    world, simulation = _experiment(seed=seed)
    simulation.run(1500)
    return world, simulation.history


def run_obj_eroded(seed: int = 3):
    eroded, simulation = _experiment(seed=seed, cell="OBJ")
    simulation.run(1500)
    return eroded, simulation.history


def run_velky_cyklus(seed: int = 3):
    world, simulation = _experiment(seed=seed, cell="PAST")
    simulation.run(500)
    kinds_500 = _kinds(world, "PAST")
    simulation.run(2500)
    return world, simulation.history, kinds_500


def run_jespersen(seed: int = 3):
    world, simulation = _experiment(seed=seed, particle="not")
    simulation.run(3000)
    return world, simulation.history


def check_analytizace(eroded, control_world):
    assert _kinds(eroded, "ORDER")["fixed"] >= 5
    assert _kinds(control_world, "ORDER")["free"] >= 5


def check_velky_cyklus(world, history, kinds_500):
    assert kinds_500["periphrastic"] >= 4  # opis převzal funkci
    events = history.of_kind("grammaticalized")
    groups = {event["group"] for event in events}
    assert len(groups) >= 4  # opis srostl v novou koncovku
    assert {event["source"] for event in events} <= set(PATHWAYS["PAST"])
    weakness = statistics.mean(
        syntax.weakness(world, world.groups[group].main_code, "PAST") for group in world.group_ids()
    )
    assert weakness < 0.4  # nová koncovka minulý čas zase rozlišuje


def check_jespersenuv_cyklus(world, history):
    established = [
        syntax.construction_of(world, event["variant"]).kind
        for event in history.of_kind("established")
        if event["variable"] == "construction:NEG"
    ]
    assert "embraced" in established and "post" in established
    assert established.index("embraced") < established.index("post")
    assert _kinds(world, "NEG")["post"] >= 4


def check_bez_eroze(control_world):
    assert _kinds(control_world, "PAST")["synthetic"] >= 5
    assert _kinds(control_world, "NEG")["pre"] >= 5
    for group in control_world.group_ids():
        profile = lexicon_profile(control_world, group)
        assert 3.0 <= profile.mean_length <= 8.0
        assert profile.homophony < 0.05


@pytest.fixture(scope="module")
def control():
    return run_control(3)


@pytest.fixture(scope="module")
def velky_cyklus_runs():
    return {seed: run_velky_cyklus(seed) for seed in VELKY_CYKLUS_SEEDS}


@pytest.fixture(scope="module")
def jespersen_runs():
    return {seed: run_jespersen(seed) for seed in JESPERSEN_SEEDS}


def test_analytizace_po_erozi_padu_se_ustali_slovosled(control):
    eroded, _ = run_obj_eroded(3)
    check_analytizace(eroded, control[0])


def test_velky_cyklus_eroze_opis_priklonka_nova_koncovka(velky_cyklus_runs):
    # Audit 101..120: 15/20, Wilson 95 % [0.531, 0.888], N=10, k=2, negativní kontrola (bez eroze PAST) 0/10.
    evaluate_seeds(velky_cyklus_runs, lambda data: check_velky_cyklus(*data), k=2)


def test_jespersenuv_cyklus_ne_ne_pas_pas(jespersen_runs):
    # Audit 101..120: 8/20, Wilson 95 % [0.219, 0.613], N=19, k=1, negativní kontrola (bez oslabení záporky) 0/19.
    # Poznámka do M7: ověřit, zda má embraced dosáhnout established dřív, než ho post vytlačí (NegationReduction od podílu 0,5).
    evaluate_seeds(jespersen_runs, lambda data: check_jespersenuv_cyklus(*data), k=1)


def test_bez_eroze_syntax_zustava_a_zvukove_metriky_drzi(control):
    check_bez_eroze(control[0])


def test_determinismus_se_syntaxi():
    def run():
        world = village_grid(3, seed=4, syntax=True, semantics=True)
        simulation = Simulation(world)
        simulation.run(1000)
        return simulation.history.digest()

    assert run() == run()
