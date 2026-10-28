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


@pytest.fixture(scope="module")
def control():
    world, simulation = _experiment()
    simulation.run(1500)
    return world, simulation.history


def test_analytizace_po_erozi_padu_se_ustali_slovosled(control):
    eroded, simulation = _experiment(cell="OBJ")
    simulation.run(1500)
    assert _kinds(eroded, "ORDER")["fixed"] >= 5
    assert _kinds(control[0], "ORDER")["free"] >= 5


def test_velky_cyklus_eroze_opis_priklonka_nova_koncovka():
    world, simulation = _experiment(cell="PAST")
    simulation.run(500)
    assert _kinds(world, "PAST")["periphrastic"] >= 4  # opis převzal funkci
    simulation.run(2500)
    events = simulation.history.of_kind("grammaticalized")
    groups = {event["group"] for event in events}
    assert len(groups) >= 4  # opis srostl v novou koncovku
    assert {event["source"] for event in events} <= set(PATHWAYS["PAST"])
    weakness = statistics.mean(
        syntax.weakness(world, world.groups[group].main_code, "PAST") for group in world.group_ids()
    )
    assert weakness < 0.4  # nová koncovka minulý čas zase rozlišuje


def test_jespersenuv_cyklus_ne_ne_pas_pas():
    world, simulation = _experiment(particle="not")
    simulation.run(3000)
    established = [
        syntax.construction_of(world, event["variant"]).kind
        for event in simulation.history.of_kind("established")
        if event["variable"] == "construction:NEG"
    ]
    assert "embraced" in established and "post" in established
    assert established.index("embraced") < established.index("post")
    assert _kinds(world, "NEG")["post"] >= 4


def test_bez_eroze_syntax_zustava_a_zvukove_metriky_drzi(control):
    world, _ = control
    assert _kinds(world, "PAST")["synthetic"] >= 5
    assert _kinds(world, "NEG")["pre"] >= 5
    for group in world.group_ids():
        profile = lexicon_profile(world, group)
        assert 3.0 <= profile.mean_length <= 8.0
        assert profile.homophony < 0.05


def test_determinismus_se_syntaxi():
    def run():
        world = village_grid(3, seed=4, syntax=True, semantics=True)
        simulation = Simulation(world)
        simulation.run(1000)
        return simulation.history.digest()

    assert run() == run()
