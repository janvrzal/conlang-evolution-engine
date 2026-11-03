"""Řídké živé fondy: shoda s husté referenční implementací a čtení výskytů po variantách."""

from __future__ import annotations

import copy
import pickle

import numpy as np
import pytest

from cee.v2.pools import LivePools
from cee.v2.registry import Numbering
from cee.v2.repertoire import Distribution

GROUPS = ["g0", "g1", "g2", "g3", "g4", "g5"]


class DenseReference:
    """Husté pole podle proměnné: ``{varianta: [podíl, základna] po skupinách}`` (jako dřívější uložení)."""

    def __init__(self, groups: int):
        self.groups = groups
        self.variables: dict[str, tuple[dict[str, np.ndarray], np.ndarray]] = {}

    def load(self, variable_id: str, distributions: list[Distribution | None]) -> None:
        variants = sorted({v for item in distributions if item is not None for v in item.variants})
        freqs = {v: np.zeros((self.groups, 2)) for v in variants}
        present = np.zeros(self.groups, dtype=bool)
        for column, item in enumerate(distributions):
            if item is None:
                continue
            present[column] = True
            for variant, freq, before in zip(item.variants, item.freqs, item.previous):
                freqs[variant][column] = (freq, before)
        self.variables[variable_id] = (freqs, present)

    def innovate(self, variable_id: str, column: int, variant: str, share: float) -> None:
        freqs, _ = self.variables[variable_id]
        freqs.setdefault(variant, np.zeros((self.groups, 2)))
        for array in freqs.values():
            array[column, 0] *= 1.0 - share
        freqs[variant][column, 0] += share
        for array in freqs.values():
            array[column, 1] = array[column, 0]

    def get(self, variable_id: str, column: int) -> Distribution | None:
        freqs, present = self.variables[variable_id]
        if not present[column]:
            return None
        used = sorted(v for v, array in freqs.items() if array[column, 0] > 0)
        return Distribution(
            tuple(used),
            np.array([freqs[v][column, 0] for v in used]),
            np.array([freqs[v][column, 1] for v in used]),
        )


def _equal(first: Distribution | None, second: Distribution | None) -> bool:
    if first is None or second is None:
        return first is second
    return (first.variants == second.variants and np.array_equal(first.freqs, second.freqs)
            and np.array_equal(first.previous, second.previous))


def _random_distribution(rng: np.random.Generator, pool: list[str]) -> Distribution:
    chosen = sorted(rng.choice(pool, size=int(rng.integers(1, 4)), replace=False).tolist())
    freqs = rng.random(len(chosen)) + 0.05
    freqs = freqs / freqs.sum()
    return Distribution(tuple(chosen), freqs, freqs * rng.random(len(chosen)) + 0.01)


def _check(pools: LivePools, reference: DenseReference) -> None:
    for variable_id in reference.variables:
        for column, group_id in enumerate(GROUPS):
            expected = reference.get(variable_id, column)
            assert _equal(pools.get(group_id, variable_id), expected), (variable_id, group_id)
            assert pools.holds(group_id, variable_id) == (expected is not None)
            if expected is None:
                assert pools.dominant(group_id, variable_id) is None
                continue
            assert pools.dominant(group_id, variable_id) == expected.dominant()
            for variant in expected.variants + ("v-absent",):
                assert pools.frequency(group_id, variable_id, variant) == expected.frequency(variant)


@pytest.mark.parametrize("seed", range(6))
def test_nahodne_operace_davaji_stejny_stav_jako_husta_reference(seed):
    rng = np.random.default_rng(seed)
    pools, reference = LivePools(GROUPS), DenseReference(len(GROUPS))
    names = [f"variant:{letter}" for letter in "abcdefghij"]
    for number in range(4):
        distributions = [None if rng.random() < 0.15 else _random_distribution(rng, names[:4])
                         for _ in GROUPS]
        variable_id = f"lexical:w{number}"
        pools.load(variable_id, distributions)
        reference.load(variable_id, distributions)
    _check(pools, reference)
    for _ in range(40):
        variable_id = f"lexical:w{int(rng.integers(0, 4))}"
        column = int(rng.integers(0, len(GROUPS)))
        if not pools.holds(GROUPS[column], variable_id):
            continue
        variant = names[int(rng.integers(0, len(names)))]
        if variant in (pools.get(GROUPS[column], variable_id) or Distribution((), np.zeros(0))).variants:
            continue
        share = float(rng.uniform(0.01, 0.3))
        pools.innovate(variable_id, GROUPS[column], variant, share)
        reference.innovate(variable_id, column, variant, share)
        if rng.random() < 0.3:
            pools.compact()
        if rng.random() < 0.2:
            for block in pools.iter_blocks():
                block.freqs  # noqa: B018 - sestaví hustý pohled
    _check(pools, reference)
    pools.compact()
    _check(pools, reference)


def test_husty_pohled_odpovida_slotum_a_zapis_celeho_bloku_ho_zachova():
    pools = LivePools(GROUPS)
    first = Distribution(("variant:a", "variant:b"), np.array([0.25, 0.75]), np.array([0.5, 0.5]))
    pools.load("lexical:x", [first, Distribution.fixed("variant:a"), None, first, Distribution.fixed("variant:b"),
                             Distribution.fixed("variant:a")])
    (block,) = pools.iter_blocks()
    freqs, previous = block.freqs.copy(), block.previous.copy()
    assert freqs[0, 0, :2].tolist() == [0.25, 0.75] and previous[0, 0, :2].tolist() == [0.5, 0.5]
    assert freqs[0, 2].sum() == 0.0  # skupina bez proměnné
    # Zápis celého bloku nic nemění a hustý pohled se po zahození sestaví znovu stejně.
    block.set_state(freqs.copy(), previous.copy())
    block.drop_dense()
    assert np.array_equal(block.freqs, freqs) and np.array_equal(block.previous, previous)
    # Pohled je jen pro čtení.
    with pytest.raises(ValueError):
        block.freqs[0, 0, 0] = 0.5
    with pytest.raises(ValueError, match="tvar"):
        block.set_state(np.zeros((1, 2, 3)), np.zeros((1, 2, 3)))


def test_zakladna_bez_podilu_se_uchova():
    pools = LivePools(["a", "b"])
    pools.load("lexical:x", [Distribution(("p", "q"), np.array([0.5, 0.5]), np.array([0.5, 0.5])),
                             Distribution.fixed("p")])
    (block,) = pools.iter_blocks()
    freqs, previous = block.freqs.copy(), block.previous.copy()
    # Základna v buňce, kde podíl zanikl, je stav, který hustá pole také nesla.
    freqs[0, 1, 1], previous[0, 1, 1] = 0.0, 0.25
    block.set_state(freqs, previous)
    block.drop_dense()
    assert block.previous[0, 1, 1] == 0.25 and block.freqs[0, 1, 1] == 0.0
    assert pools.get("b", "lexical:x").variants == ("p",)


def test_mapa_rozsireni_varianty_je_seznam_vyskytu():
    pools = LivePools(GROUPS)
    old = Distribution.fixed("variant:old")
    pools.load("lexical:x", [old] * len(GROUPS))
    pools.innovate("lexical:x", "g1", "variant:new", 0.25)
    pools.innovate("lexical:x", "g4", "variant:new", 0.5)
    groups, shares = pools.range_of("lexical:x", "variant:new")
    assert groups == ["g1", "g4"] and shares.tolist() == [0.25, 0.5]
    groups, shares = pools.range_of("lexical:x", "variant:old")
    assert groups == GROUPS and shares[[0, 1, 4]].tolist() == [1.0, 0.75, 0.5]
    assert pools.range_of("lexical:x", "variant:none") == ([], pytest.approx(np.zeros(0)))
    assert pools.range_of("lexical:neznama", "variant:old")[0] == []
    # Nová varianta zabírá jen svých pár buněk, ne řádek přes všechny skupiny.
    stats = pools.stats()
    assert stats["entries"] == len(GROUPS) + 2
    assert stats["entries"] < stats["dense_cells"]
    assert stats["sparse_bytes"] > 0


def test_cisla_variant_ve_slotech_odpovidaji_retezcovym_id():
    numbering = Numbering("variant")
    for name in ("zzz", "variant:old"):
        numbering.intern(name)
    pools = LivePools(GROUPS, numbering)
    pools.load("lexical:x", [Distribution.fixed("variant:old")] * len(GROUPS))
    pools.innovate("lexical:x", "g0", "variant:new", 0.1)
    (block,) = pools.iter_blocks()
    names = [None if number < 0 else numbering.names[number] for number in block.slot_variants[0]]
    assert names == block.slots[0] == ["variant:old", "variant:new"]
    assert block.numbers_in(numbering).tolist() == [[1, 2]]
    other = Numbering("variant")
    other.intern("variant:new")
    other.intern("variant:old")
    assert block.numbers_in(other).tolist() == [[1, 0]]


def test_kopie_a_pickle_zachovaji_stav_bez_hustych_pohledu():
    pools = LivePools(GROUPS)
    pools.load("lexical:x", [Distribution.fixed("variant:old")] * len(GROUPS))
    pools.innovate("lexical:x", "g2", "variant:new", 0.2)
    (block,) = pools.iter_blocks()
    block.freqs  # noqa: B018 - hustý pohled existuje
    for clone in (copy.deepcopy(pools), pickle.loads(pickle.dumps(pools))):
        (copied,) = clone.iter_blocks()
        assert not copied.has_dense
        assert _equal(clone.get("g2", "lexical:x"), pools.get("g2", "lexical:x"))
        assert np.array_equal(copied.freqs, block.freqs)


def test_uvolneni_a_presun_do_mensiho_bloku_zachova_hodnoty():
    pools = LivePools(GROUPS)
    pools.load("lexical:x", [Distribution.fixed("variant:a")] * len(GROUPS))
    for letter, group in zip("bcd", GROUPS[1:]):
        pools.innovate("lexical:x", group, f"variant:{letter}", 0.2)
    before = [pools.get(group, "lexical:x") for group in GROUPS]
    assert pools.release() == []
    assert [_equal(item, pools.get(group, "lexical:x")) for item, group in zip(before, GROUPS)] == [True] * 6
    # Varianta, kterou nežije žádná skupina, uvolní slot i základnu; ostatní zůstanou.
    (block,) = pools.iter_blocks()
    state = block.freqs.copy()
    state[0, 1:, block.slots[0].index("variant:b")] = 0.0
    state[0, 1] /= state[0, 1].sum()
    block.set_state(state, np.where(state > 0, block.previous, 0.0))
    assert pools.release() == []
    assert "variant:b" not in block.slots[0]
    assert block.slot_variants[0].tolist().count(-1) == 1 and block.slot_keys[0, block.slots[0].index(None)] == 0
