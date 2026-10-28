"""Brána milníku M4b (specifikace, oddíl Milníky): modulární gramatika.

Funkce jsou řádky katalogu a jazyk je má jen podle profilu protojazyka.
Ověřuje se, že kategorie může vzniknout (člen z ukazovacího zájmena), že
zbytková koncovka může dostat novou funkci (exaptace) a že jazyk bez
kategorie ji nemá, dokud ji nevyvine.
"""

from collections import Counter

import pytest

from cee.v2 import syntax
from cee.v2.language.constructions import Construction, catalog
from cee.v2.scenarios import SYNTAX_GRAMMAR, village_grid
from cee.v2.simulation import Simulation

#: Jazyk bez pádu a bez členu, který ho ale může vyvinout.
NO_CASE = {
    **{name: construction for name, construction in SYNTAX_GRAMMAR.items() if name != "OBJ"},
    "DEFINITE": Construction("DEFINITE", "zero"),
}
ARTICLE_SEEDS = (1, 2, 3)


def _kinds(world, function):
    return Counter(syntax.dominant(world, group, function).kind for group in world.group_ids())


@pytest.fixture(scope="module")
def no_case():
    result = []
    for seed in ARTICLE_SEEDS:
        world = village_grid(6, seed=seed, grammar=NO_CASE, semantics=True)
        simulation = Simulation(world)
        simulation.run(3000)
        result.append((world, simulation.history))
    return result


def test_clen_vznikne_z_ukazovaciho_zajmena(no_case):
    with_article = 0
    for world, history in no_case:
        kinds = _kinds(world, "DEFINITE")
        with_article += kinds["zero"] <= 2
        for group in world.group_ids():
            construction = syntax.dominant(world, group, "DEFINITE")
            assert construction.source in (None, *catalog()["DEFINITE"].sources)
        if any(event["function"] == "DEFINITE" for event in history.of_kind("grammaticalized")):
            # Člen srostl v koncovku: jazyk dostal buňku, kterou dřív neměl.
            assert "DEF" in world.paradigms["noun"].cells
    # Člen není univerzála: vznikne ve většině jazyků, ne nutně ve všech.
    assert with_article >= 2


def test_bez_padu_se_slovosled_ustali(no_case):
    for world, _ in no_case:
        assert "OBJ" not in world.paradigms["noun"].cells
        assert _kinds(world, "ORDER")["fixed"] >= 5


def _exaptation(order):
    grammar = {**SYNTAX_GRAMMAR, "DEFINITE": Construction("DEFINITE", "zero"), "ORDER": order}
    world = village_grid(6, seed=3, grammar=grammar, semantics=True)
    simulation = Simulation(world)
    simulation.run(1500)
    return world, simulation.history


def test_exaptace_zbytkove_koncovky():
    """Pád vedle pevného slovosledu nic nenese; jeho koncovka se stane členem."""
    world, history = _exaptation(Construction("ORDER", "fixed", order="SVO"))
    events = history.of_kind("exapted")
    assert len({event["group"] for event in events}) >= 4
    assert {(event["function"], event["donor"]) for event in events} == {("DEFINITE", "OBJ")}
    group = events[0]["group"]
    code = world.groups[group].main_code
    definite = syntax.cell_units(world, code, catalog()["DEFINITE"])
    assert definite
    assert all(
        world.morphemes[unit].lexeme_id + "#OBJ" in code.phonology.vocabulary for unit in definite
    )
    # Kontrola: dokud pád nese role, koncovka nic nového neznamená.
    control, control_history = _exaptation(Construction("ORDER", "free"))
    assert not control_history.of_kind("exapted")
    assert "DEF" not in control.paradigms["noun"].cells


def test_jazyk_bez_kategorie_ji_nema_dokud_ji_nevyvine():
    tenseless = {name: construction for name, construction in SYNTAX_GRAMMAR.items() if name != "PAST"}
    world = village_grid(6, seed=3, grammar=tenseless, semantics=True)
    Simulation(world).run(1000)
    assert world.paradigms["verb"].cells == ("PRES",)
    assert syntax.variable_id("PAST") not in world.variables
    assert not any(world.morphemes[unit].cell == "PAST"
                   for group in world.groups.values() for unit in group.main_code.phonology.vocabulary)

    # Stejný jazyk s minulým časem jako prázdnou funkcí si ho vytvoří opisem.
    world = village_grid(6, seed=3, grammar={**tenseless, "PAST": Construction("PAST", "zero")}, semantics=True)
    simulation = Simulation(world)
    simulation.run(2000)
    assert _kinds(world, "PAST")["zero"] <= 1
    sources = {syntax.dominant(world, group, "PAST").source for group in world.group_ids()}
    assert sources <= set(catalog()["PAST"].sources)
    if simulation.history.of_kind("grammaticalized"):
        assert "PAST" in world.paradigms["verb"].cells


def test_determinismus_s_profilem():
    def run():
        world = village_grid(3, seed=4, grammar=NO_CASE, semantics=True)
        simulation = Simulation(world)
        simulation.run(1000)
        return simulation.history.digest()

    assert run() == run()
