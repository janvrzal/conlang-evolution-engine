"""Srovnatelnost referencí, losování a neinvazivní pozorování."""

import pytest

from cee.v2 import metrics
from cee.v2.scenarios import SYNTAX_GRAMMAR, village_grid
from cee.v2.simulation import Simulation
from scripts import v2_typology as runner


def _reference_one_value(feature, value):
    reference = runner.load_reference()
    for name in runner.FEATURES:
        available = reference["features"][name]["engine_distribution"]
        selected = value if name == feature else next(iter(available))
        reference["features"][name]["engine_distribution"] = {selected: 1.0}
    return reference


@pytest.mark.parametrize("feature,value", [
    ("33A", "plural_present"), ("33A", "plural_absent"),
    ("143A", "143A-1"), ("143A", "143A-2"), ("143A", "143A-14"),
    ("37A", "definite_present"), ("37A", "definite_absent"),
    ("66A", "past_present"), ("66A", "past_absent"),
    ("67A", "67A-1"), ("67A", "67A-2"),
    *(("81A", f"81A-{index}") for index in range(1, 7)),
])
def test_losovani_reprezentantu_vraci_stejnou_kategorii(feature, value):
    reference = _reference_one_value(feature, value)
    grammar = runner.sample_grammar(17, reference)
    assert grammar == runner.sample_grammar(17, reference)
    world = village_grid(1, seed=17, grammar=grammar)
    assert metrics.typology_profile(world, list(world.groups))[feature] == value


def test_puvodni_start_ma_presny_profil_a_chybejici_funkce():
    world = village_grid(1, seed=1, grammar=dict(SYNTAX_GRAMMAR))
    assert set(SYNTAX_GRAMMAR) == {"PAST", "PL", "OBJ", "NEG", "ORDER"}
    profile = metrics.typology_profile(world, list(world.groups))
    assert profile == {"14A": "14A-6", "33A": "plural_present", "37A": "definite_absent", "66A": "past_present",
                       "67A": "67A-2", "81A": None, "143A": "143A-1"}


def test_reference_zachovava_nepodporovane_a_prazdne_pokryti():
    reference = runner.load_reference()
    feature = reference["features"]["81A"]
    projected = runner.projected_reference(feature)
    assert projected["81A-7"] == feature["distribution"]["81A-7"] > 0
    assert sum(projected.values()) == pytest.approx(1)
    profiles = [{name: None for name in runner.FEATURES}]
    runs = [{"experiment": "same", "frames": [{"year": 0, "profiles": profiles}]}]
    rows = runner.summarize(runs, reference)
    row = next(row for row in rows if row["experiment"] == "same"
               and row["year"] == 0 and row["feature"] == "81A")
    assert row["known"] == 0 and row["coverage"] == 0
    assert row["hellinger"] is None and row["entropy"] is None


def test_zachyceni_nemeni_nasledujici_beh():
    measured = Simulation(village_grid(1, seed=7, syntax=True, semantics=True))
    control = Simulation(village_grid(1, seed=7, syntax=True, semantics=True))
    runner.capture(measured)
    measured.run(100)
    control.run(100)
    runner.capture(measured)
    assert measured.history.digest() == control.history.digest()
    assert measured.tracker.lineages == control.tracker.lineages
    for group_id in measured.world.group_ids():
        for variable_id in measured.world.variables:
            first = measured.world.distribution(group_id, variable_id)
            second = control.world.distribution(group_id, variable_id)
            assert (None if first is None else first.as_dict()) == (
                None if second is None else second.as_dict()
            )
