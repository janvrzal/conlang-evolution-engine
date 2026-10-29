"""Brána milníku M6c (specifikace, oddíl Milníky): strom jazyků.

Rozpad se známou historií: řada devíti vesnic, v roce 300 se oddělí C, v
roce 1800 A a B. Pozorovaný strom má vyjít ((A, B), C), bez kmitání.
"""

import pytest

from cee.v2.export import lineages
from cee.v2.scenarios import known_tree
from cee.v2.simulation import Simulation


def run_known_tree(seed: int):
    world, events = known_tree(seed)
    simulation = Simulation(world, events=events)
    simulation.run(4000)
    return simulation


def _cluster(groups):
    return {group[0] for group in groups}


def check_strom_odpovida(run):
    splits = run.history.of_kind("language_split")
    assert [_cluster(event["groups"]) for event in splits] in ([{"c"}, {"b"}], [{"c"}, {"a"}])
    first, second = splits
    assert first["year"] > 300 and second["year"] > 1800
    tree = {item["id"]: item for item in lineages(run)}
    root = first["parent"]
    assert tree[root]["parent"] is None
    # Druhé rozštěpení vychází z linie, která po prvním zůstala A + B.
    assert second["parent"] == root
    final = run.history.snapshots[-1].languages
    assert sorted("".join(sorted(_cluster(groups))) for groups in final.values()) == ["a", "b", "c"]


def check_strom_stabilni(run):
    assert len(run.history.of_kind("language_split")) == 2
    assert not run.history.of_kind("language_ended")
    assert len(run.history.of_kind("language_emerged")) == 1


@pytest.fixture(scope="module", params=(1, 2))
def run(request):
    return run_known_tree(request.param)


def test_strom_jazyku_odpovida_historii_rozpadu(run):
    check_strom_odpovida(run)


def test_strom_je_stabilni(run):
    check_strom_stabilni(run)
