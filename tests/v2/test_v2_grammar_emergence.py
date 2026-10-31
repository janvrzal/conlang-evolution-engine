"""Vznik a obnova kategorií, obecná kompenzace a vid (příprava kalibrace M7a)."""

from __future__ import annotations

import numpy as np
import pytest

from cee.v2 import syntax
from cee.v2.language.constructions import Construction
from cee.v2.parameters import Parameters
from cee.v2.pressures.base import PressureBatch
from cee.v2.pressures.syntactic import Expressivity
from cee.v2.repertoire import Origin
from cee.v2.scenarios import FULL_GRAMMAR, village_grid
from cee.v2.simulation import Simulation


def _world(grammar=FULL_GRAMMAR, params=None):
    world = village_grid(1, seed=42, syntax=True, semantics=True, grammar=grammar, params=params)
    Simulation(world)
    return world, world.groups[world.group_ids()[0]]


def _scores(world, group, function, constructions):
    variants = [syntax.register(world, item, Origin("test", 0, 0, None))[1] for item in constructions]
    share = np.full((1, 1, len(variants)), 1.0 / len(variants))
    batch = PressureBatch(world=world, variable_ids=[syntax.variable_id(function)], group_ids=[group.id],
                          freqs=share, slots=[[variant.id for variant in variants]], tick=0, heard=share)
    return Expressivity().scores(batch)[0, 0]


def test_vznik_kategorie_tlaci_jen_casti_potreby():
    """Nevyjádřená funkce: výhoda opisu proti zero se škáluje ``emergence_need_scale``."""
    pair = [Construction("DEFINITE", "zero"), Construction("DEFINITE", "periphrastic", "this", "free")]
    full_world, full_group = _world()
    weak_world, weak_group = _world(params=Parameters(emergence_need_scale=0.2))
    assert syntax.dominant(full_world, full_group.id, "DEFINITE").kind == "zero"
    full = _scores(full_world, full_group, "DEFINITE", pair)
    weak = _scores(weak_world, weak_group, "DEFINITE", pair)
    assert weak[1] - weak[0] == pytest.approx(0.2 * (full[1] - full[0]))


def test_obnova_zeslabeneho_vyrazu_ma_plnou_potrebu():
    """Vyjádřená funkce (koncovka minulého času): škála vzniku se neuplatní."""
    pair = [Construction("PAST", "synthetic"), Construction("PAST", "periphrastic", "have", "free")]
    full_world, full_group = _world()
    weak_world, weak_group = _world(params=Parameters(emergence_need_scale=0.2))
    assert syntax.dominant(full_world, full_group.id, "PAST").kind == "synthetic"
    assert list(_scores(full_world, full_group, "PAST", pair)) == list(
        _scores(weak_world, weak_group, "PAST", pair))


def test_vid_zastoupi_minuly_cas_a_slovosled_pad():
    """Kompenzace podle ``coverage``: vid nese 0,7 role minulého času, pevný slovosled 0,9 pádu."""
    world, group = _world()
    assert syntax.compensation(world, group.id, "PAST") == 0.0
    with_aspect = {**FULL_GRAMMAR, "ASPECT": Construction("ASPECT", "periphrastic", "finish", "free"),
                   "ORDER": Construction("ORDER", "fixed", order="SVO")}
    world, group = _world(with_aspect)
    assert syntax.compensation(world, group.id, "PAST") == pytest.approx(0.7)
    assert syntax.compensation(world, group.id, "OBJ") == pytest.approx(0.9)
    zero_past = syntax.strength(world, group.main_code, Construction("PAST", "zero"), group_id=group.id)
    assert zero_past == pytest.approx(0.7)
    assert syntax.carries_role(world, Construction("ORDER", "free")) is False
    assert syntax.carries_role(world, Construction("ASPECT", "zero")) is False


def test_coverage_lze_prepsat_parametry_sveta():
    with_aspect = {**FULL_GRAMMAR, "ASPECT": Construction("ASPECT", "periphrastic", "finish", "free")}
    world, group = _world(with_aspect, Parameters(grammar={"ASPECT": {"coverage": 0.4}}))
    assert syntax.compensation(world, group.id, "PAST") == pytest.approx(0.4)
