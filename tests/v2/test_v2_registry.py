"""Registr stabilních ID pro číselná pole enginu."""

import copy

import pytest

from cee.v2.language.registry import IdRegistry


def test_registr_prideluje_stala_cisla_a_radi_podle_id():
    registry = IdRegistry()
    assert [registry.register(value) for value in ("z", "a", "m", "a")] == [0, 1, 2, 1]
    assert len(registry) == 3
    assert registry.index_of("m") == 2
    assert registry.id_of(0) == "z"
    assert registry.sorted_indices() == (1, 2, 0)
    registry.register("b")
    assert registry.sorted_indices() == (1, 3, 2, 0)
    assert registry.id_of(0) == "z"


def test_kopie_registru_se_mohou_nezavisle_rozrustat():
    registry = IdRegistry()
    registry.register("root")
    clone = copy.deepcopy(registry)
    assert registry.register("left") == 1
    assert clone.register("right") == 1
    assert registry.sorted_indices() == (1, 0)
    assert clone.sorted_indices() == (1, 0)
    assert registry.id_of(1) == "left"
    assert clone.id_of(1) == "right"
    with pytest.raises(KeyError):
        clone.index_of("left")


def test_neznamy_index_a_id_nesmi_vratit_jiny_zaznam():
    registry = IdRegistry()
    registry.register("x")
    with pytest.raises(KeyError):
        registry.index_of("missing")
    with pytest.raises(IndexError):
        registry.id_of(-1)
    with pytest.raises(IndexError):
        registry.id_of(1)
