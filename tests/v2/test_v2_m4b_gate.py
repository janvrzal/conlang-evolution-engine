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
from cee.v2.parameters import Parameters
from cee.v2.scenarios import SYNTAX_GRAMMAR, village_grid
from cee.v2.simulation import Simulation
from tests.v2.gate_checks import evaluate_seeds

#: Jazyk bez pádu a bez členu, který ho ale může vyvinout.
NO_CASE = {
    **{name: construction for name, construction in SYNTAX_GRAMMAR.items() if name != "OBJ"},
    "DEFINITE": Construction("DEFINITE", "zero"),
}
#: Člen vzniká jen v části jazyků (M7a, docs/engine-v2/12-kalibrace-m7a.md):
#: audit 6/30 na seedech 101..130, Wilson 95 % [0,095; 0,373]. Pro „aspoň
#: jednou“ s rizikem falešného selhání pod 1 % je třeba N ≥ 46 (0,905^46 < 0,01).
ARTICLE_SEEDS = tuple(range(1, 51))
#: Slovosled bez pádu se ověřuje na původních seedech (robustní, 30/30).
ORDER_SEEDS = 3
EXAPTATION_SEEDS = tuple(range(1, 11))


def _kinds(world, function):
    return Counter(syntax.dominant(world, group, function).kind for group in world.group_ids())


def run_no_case(seed: int, params: Parameters | None = None):
    world = village_grid(6, seed=seed, grammar=NO_CASE, semantics=True, params=params)
    simulation = Simulation(world)
    simulation.run(3000)
    return world, simulation.history


def check_clen_invariants(world, history) -> bool:
    kinds = _kinds(world, "DEFINITE")
    for group in world.group_ids():
        construction = syntax.dominant(world, group, "DEFINITE")
        assert construction.source in (None, *catalog()["DEFINITE"].sources)
    if any(event["function"] == "DEFINITE" for event in history.of_kind("grammaticalized")):
        # Člen srostl v koncovku: jazyk dostal buňku, kterou dřív neměl.
        assert "DEF" in world.paradigms["noun"].cells
    return bool(kinds["zero"] <= 2)


def check_clen_jeden_seed(world, history) -> None:
    assert check_clen_invariants(world, history)


def check_bez_padu(world):
    assert "OBJ" not in world.paradigms["noun"].cells
    assert _kinds(world, "ORDER")["fixed"] >= 5


def _exaptation(order, seed: int = 3):
    grammar = {**SYNTAX_GRAMMAR, "DEFINITE": Construction("DEFINITE", "zero"), "ORDER": order}
    world = village_grid(6, seed=seed, grammar=grammar, semantics=True)
    simulation = Simulation(world)
    simulation.run(1500)
    return world, simulation.history


def run_exaptation_pair(seed: int = 3):
    target = _exaptation(Construction("ORDER", "fixed", order="SVO"), seed=seed)
    control = _exaptation(Construction("ORDER", "free"), seed=seed)
    return target, control


def check_exaptace(world, history, control, control_history):
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
    assert not control_history.of_kind("exapted")
    assert "DEF" not in control.paradigms["noun"].cells


def run_tenseless_pair(seed: int = 3):
    tenseless = {name: construction for name, construction in SYNTAX_GRAMMAR.items() if name != "PAST"}
    tenseless_world = village_grid(6, seed=seed, grammar=tenseless, semantics=True)
    Simulation(tenseless_world).run(1000)

    # Stejný jazyk s minulým časem jako prázdnou funkcí si ho vytvoří opisem.
    zero_world = village_grid(6, seed=seed, grammar={**tenseless, "PAST": Construction("PAST", "zero")}, semantics=True)
    simulation = Simulation(zero_world)
    simulation.run(2000)
    return tenseless_world, (zero_world, simulation.history)


def check_jazyk_bez_kategorie(tenseless_world, zero_world, zero_history):
    assert tenseless_world.paradigms["verb"].cells == ("PRES",)
    assert syntax.variable_id("PAST") not in tenseless_world.variables
    assert not any(tenseless_world.morphemes[unit].cell == "PAST"
                   for group in tenseless_world.groups.values() for unit in group.main_code.phonology.vocabulary)

    assert _kinds(zero_world, "PAST")["zero"] <= 1
    sources = {syntax.dominant(zero_world, group, "PAST").source for group in zero_world.group_ids()}
    assert sources <= set(catalog()["PAST"].sources)
    if zero_history.of_kind("grammaticalized"):
        assert "PAST" in zero_world.paradigms["verb"].cells


@pytest.fixture(scope="module")
def no_case():
    return [run_no_case(seed) for seed in ARTICLE_SEEDS]


def test_clen_vznikne_z_ukazovaciho_zajmena(no_case):
    with_article = sum(check_clen_invariants(world, history) for world, history in no_case)
    # Člen není univerzála (WALS 37A: asi 39 % jazyků bez určitého členu):
    # za 3 000 let bez kontaktu vznikne v některých jazycích, ne ve všech.
    assert 1 <= with_article < len(no_case), f"člen ve {with_article} z {len(no_case)} jazyků"


def test_bez_opisu_a_exaptace_clen_nevznikne():
    """Negativní kontrola: bez mechanismů vzniku (opis, exaptace) člen nevznikne."""
    off = Parameters(change_rates={"periphrasis": 0.0, "exaptation": 0.0})
    assert not any(check_clen_invariants(*run_no_case(seed, off)) for seed in range(1, 6))


def test_bez_padu_se_slovosled_ustali(no_case):
    for world, _ in no_case[:ORDER_SEEDS]:
        check_bez_padu(world)


@pytest.fixture(scope="module")
def exaptation_runs():
    return {seed: run_exaptation_pair(seed) for seed in EXAPTATION_SEEDS}


def test_exaptace_zbytkove_koncovky(exaptation_runs):
    """Pád vedle pevného slovosledu nic nenese; jeho koncovka se stane členem."""
    # Audit 101..120: 15/20, Wilson 95 % [0.531, 0.888], N=10, k=2, negativní kontrola (volný slovosled) 0/10.
    evaluate_seeds(
        exaptation_runs,
        lambda pair: check_exaptace(pair[0][0], pair[0][1], pair[1][0], pair[1][1]),
        k=2,
    )


def test_jazyk_bez_kategorie_ji_nema_dokud_ji_nevyvine():
    tenseless_world, (zero_world, zero_history) = run_tenseless_pair(3)
    check_jazyk_bez_kategorie(tenseless_world, zero_world, zero_history)


def test_determinismus_s_profilem():
    def run():
        world = village_grid(3, seed=4, grammar=NO_CASE, semantics=True)
        simulation = Simulation(world)
        simulation.run(1000)
        return simulation.history.digest()

    assert run() == run()
