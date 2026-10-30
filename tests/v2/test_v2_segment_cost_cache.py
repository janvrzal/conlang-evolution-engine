"""Opakovaná cena hlásek musí zůstat přesně rovna původnímu výpočtu."""

from cee.v2 import observe
from cee.v2.scenarios import village_grid


def test_segment_cost_matches_direct_and_respects_scale(monkeypatch):
    world = village_grid(1, seed=1, phonology=True)
    table = world.table
    assert table is not None
    for scale in (6.0, 12.0):
        monkeypatch.setattr(observe, "FEATURE_SCALE", scale)
        for first in ("k", "kʲ", "a", "ã"):
            for second in ("t", "ɡ", "i", "õ"):
                a, b = table.id_of(first), table.id_of(second)
                expected = min(1.0, float((table.vectors[a] != table.vectors[b]).sum()) / scale)
                assert observe.segment_cost(world, a, b) == expected
                assert observe.segment_cost(world, b, a) == expected
        same = table.id_of("k")
        assert observe.segment_cost(world, same, same) == 0.0
