"""Přenos a živé fondy v Rustu proti Pythonu: zlatá data, náhodné šířky, vlákna a stav bloku.

Rust musí dát bit po bitu totéž co Python:

- ``hear``, ``settle`` a ``normalized`` na zlatých datech přenosu
  (``tests/v2/data/golden_transmission.json.gz``) a na náhodných vstupech šířek 1 až
  několik set (počet skupin, slotů i proměnných);
- libovolný počet vláken dá stejné bity (vlákna dělí jen nezávislé proměnné);
- buňky bloku fondů (``NativeCells``) se chovají jako Python ``PyCells`` při náhodné
  posloupnosti operací, uložení i obnově;
- celý běh s Rustem a bez něj dá tentýž otisk historie i stav světa.

Bez sestaveného rozšíření se testy s Rustem přeskočí.
"""

from __future__ import annotations

import gzip
import json
import os
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from cee.v2 import native
from cee.v2 import phases_transmission as phases
from cee.v2.pools import LivePools, PoolBlock, PyCells
from cee.v2.repertoire import Distribution
from cee.v2.rng import hash_normal

GOLDEN = Path(__file__).parent / "data" / "golden_transmission.json.gz"

needs_native = pytest.mark.skipif(
    os.environ.get("CEE_NATIVE") == "0" or not native.available(),
    reason="rozšíření cee_core není sestavené (nebo je vypnuté CEE_NATIVE=0)",
)


def _module() -> Any:
    module = native._load()
    assert module is not None
    return module


def same(first: np.ndarray, second: np.ndarray) -> bool:
    return first.dtype == second.dtype and first.shape == second.shape and first.tobytes() == second.tobytes()


# --- zlatá data -------------------------------------------------------------------------


def _golden(name: str) -> list[dict[str, Any]]:
    from test_v2_golden_transmission import decode

    with gzip.open(GOLDEN, "rt") as handle:
        records = json.load(handle)["functions"]["cee.v2.phases_transmission." + name]["records"]
    return [{"args": [decode(arg) for arg in record["args"]], "result": decode(record["result"])}
            for record in records]


@needs_native
def test_rust_hear_settle_and_normalized_match_the_golden_data() -> None:
    assert native.libm_matches(), "knihovna systému se liší od numpy: settle v Rustu se nepoužívá"
    module = _module()
    for record in _golden("hear"):
        current, present, members, blocks, alone, alone_weight, flows, channels = record["args"]
        found = module.hear(current, present, members, blocks, alone, alone_weight, flows, channels)
        assert same(found, record["result"])
    for record in _golden("settle"):
        assert all(same(a, b) for a, b in zip(module.settle(*record["args"]), record["result"]))
    for record in _golden("normalized"):
        array, fallback = record["args"]
        if array.ndim == 3:
            assert same(module.normalized(array, fallback), record["result"])


@needs_native
def test_numpy_and_the_system_library_agree_on_exp_log_cos() -> None:
    """Zkouška, na které stojí ``settle`` v Rustu; na stroji, kde neprojde, počítá Python."""
    assert native.libm_matches()
    module = _module()
    rng = np.random.default_rng(7)
    keys = rng.integers(0, np.iinfo(np.uint64).max, size=(2, 5000), dtype=np.uint64)
    found = module.libm_probe("hash_normal", np.zeros(5000), np.ascontiguousarray(keys.T.reshape(-1)))
    assert same(found, hash_normal(keys[0], keys[1], pairwise=True))
    exps = rng.uniform(-30.0, 30.0, 5000)
    assert same(module.libm_probe("exp", exps, np.zeros(0, dtype=np.uint64)), np.exp(exps))


# --- náhodné šířky -------------------------------------------------------------------


def _network(rng: np.random.Generator, size: int) -> tuple[Any, ...]:
    """Řídká matice vazeb ``size`` skupin (jako ``prepare``): komponenty, osamocené skupiny, bloky mezi jazyky."""
    links = rng.random((size, size)) * (rng.random((size, size)) < min(1.0, 6.0 / size))
    np.fill_diagonal(links, 0.0)
    openness = rng.uniform(0.05, 0.9, size)
    totals = links.sum(axis=1)
    safe = np.where(totals > 0, totals, 1.0)
    openness = np.where(totals > 0, openness, 0.0)
    mixing = (1.0 - openness)[:, None] * np.eye(size) + openness[:, None] * (links / safe[:, None])
    components = phases.components(mixing)
    linked = [members for members in components if len(members) > 1]
    alone = np.array([members[0] for members in components if len(members) == 1], dtype=np.intp)
    languages = rng.integers(0, 3, size).astype(np.intp)
    foreign = phases.foreign_mask(languages)
    fraction = rng.random((size, size))
    return (linked, phases.internal_blocks(mixing, linked, foreign), alone, mixing[alone, alone],
            [phases.cross_blocks(mixing, linked, foreign, None),
             phases.cross_blocks(mixing, linked, foreign, fraction)])


def _hear_inputs(rng: np.random.Generator, size: int, slots: int, variables: int) -> tuple[Any, ...]:
    members, blocks, alone, alone_weight, cross = _network(rng, size)
    cells = rng.random((variables, size, slots)) * (rng.random((variables, size, slots)) < 0.5)
    present = rng.random((variables, size)) < 0.9
    cells[~present] = 0.0
    flows = [(rng.uniform(0.0, 1.5, variables), crossing) for crossing in cross]
    learners = np.sort(rng.choice(size, size=max(1, size // 3), replace=False)).astype(np.intp)
    channels = [(rng.uniform(0.0, 2.0, variables), learners, rng.integers(0, size, len(learners)).astype(np.intp),
                 rng.random(len(learners)))]
    return cells, present, members, blocks, alone, alone_weight, flows, channels


@needs_native
@pytest.mark.parametrize("size", [1, 2, 3, 5, 8, 17, 64, 127, 128, 129, 300])
@pytest.mark.parametrize("slots", [1, 2, 3, 8])
def test_hear_matches_python_on_random_networks(size: int, slots: int) -> None:
    rng = np.random.default_rng(size * 31 + slots)
    args = _hear_inputs(rng, size, slots, 3)
    expected = phases.hear_python(*args)
    for threads in (1, 2, 5):
        assert same(_module().hear(*args, threads), expected), (size, slots, threads)


@needs_native
@pytest.mark.parametrize("slots", [1, 2, 3, 4, 8, 16])
def test_settle_matches_python_on_random_blocks(slots: int) -> None:
    assert native.libm_matches()
    rng = np.random.default_rng(slots)
    for size, variables in ((1, 1), (4, 7), (33, 5), (200, 2)):
        shape = (variables, size, slots)
        current = rng.dirichlet(np.ones(slots) * 0.4, size=shape[:2])
        current[rng.random(shape) < 0.3] = 0.0
        current /= np.where(current.sum(axis=2, keepdims=True) > 0, current.sum(axis=2, keepdims=True), 1.0)
        present = rng.random(shape[:2]) < 0.9
        current[~present] = 0.0
        previous = np.clip(current + rng.normal(0.0, 0.05, shape), 0.0, None) * (current > 0)
        heard = np.clip(current + rng.normal(0.0, 0.1, shape), 0.0, None)
        heard /= np.where(heard.sum(axis=2, keepdims=True) > 0, heard.sum(axis=2, keepdims=True), 1.0)
        fitness = rng.uniform(-1.0, 1.0, shape)
        slot_keys = rng.integers(1, 2**63, size=(variables, slots), dtype=np.uint64)
        args = (current, previous, present, heard, fitness, slot_keys,
                rng.integers(1, 2**63, size=size, dtype=np.uint64), rng.uniform(0.0, 0.2, size),
                rng.uniform(0.05, 0.9, size), rng.uniform(0.0, 0.05, size), 1.0, 0.3, 0.05, 0.9)
        expected = phases.settle_python(*args)
        for threads in (1, 3):
            found = _module().settle(*args, threads)
            assert all(same(a, b) for a, b in zip(found, expected)), (size, variables, threads)


@needs_native
def test_normalized_matches_python_for_many_slot_counts() -> None:
    rng = np.random.default_rng(3)
    for slots in range(1, 40):
        array = rng.random((4, 6, slots)) * (rng.random((4, 6, slots)) < 0.6)
        array[0, 0] = 0.0
        fallback = rng.random((4, 6, slots))
        assert same(_module().normalized(array, fallback), phases.normalized_python(array, fallback)), slots


# --- buňky bloku ----------------------------------------------------------------------


def _random_ops(cells: Any, rng: np.random.Generator, groups: int, capacity: int) -> None:
    """Stejná náhodná posloupnost operací nad uložením buněk."""
    for _ in range(4):
        width = int(rng.integers(1, capacity + 1))
        freqs = rng.random((groups, width)) * (rng.random((groups, width)) < 0.5)
        freqs /= np.where(freqs.sum(axis=1, keepdims=True) > 0, freqs.sum(axis=1, keepdims=True), 1.0)
        cells.append(freqs, freqs * rng.random((groups, width)))
    for _ in range(60):
        row = int(rng.integers(0, len(cells)))
        column = int(rng.integers(0, groups))
        slot = int(rng.integers(0, capacity))
        kind = rng.random()
        if kind < 0.6:
            cells.add_share(row, column, slot, float(rng.uniform(0.01, 0.99)))
        elif kind < 0.8:
            cells.free_slots(row, [slot])
        elif kind < 0.9 and len(cells) > 1:
            cells.swap_remove(row)
        else:
            dense_f, dense_p = (np.array(array) for array in cells.dense())
            dense_f[row] *= 0.5
            cells.stage(dense_f, dense_p)
            cells.commit(False)


def _dump(cells: Any) -> tuple[np.ndarray, ...]:
    dense_f, dense_p = cells.dense()
    return (np.array(dense_f), np.array(dense_p), *(np.array(array) for array in cells.flat()))


@needs_native
@pytest.mark.parametrize("seed", range(8))
def test_native_cells_behave_like_python_cells(seed: int) -> None:
    groups, capacity = int(np.random.default_rng(seed).integers(1, 9)), int(np.random.default_rng(seed + 9).integers(2, 9))
    python, native_cells = PyCells(groups, capacity), _module().NativeCells(groups, capacity, 1 + seed % 3)
    for cells in (python, native_cells):
        _random_ops(cells, np.random.default_rng(seed), groups, capacity)
    assert len(python) == len(native_cells) and python.entries() == native_cells.entries()
    for first, second in zip(_dump(python), _dump(native_cells)):
        assert same(first, second)
    for row in range(len(python)):
        for column in range(groups):
            for slot in range(capacity):
                assert python.value(row, column, slot) == native_cells.value(row, column, slot)
            assert all(same(np.asarray(a), np.asarray(b)) for a, b in zip(python.cell(row, column),
                                                                          native_cells.cell(row, column)))
        for slot in range(capacity):
            assert all(same(np.asarray(a), np.asarray(b)) for a, b in zip(python.range_of(row, slot),
                                                                          native_cells.range_of(row, slot)))
    # Uložení a obnova přes pole jsou záměnné mezi oběma uloženími.
    restored = _module().NativeCells.from_flat(groups, capacity, *python.flat(), 1)
    again = PyCells.from_flat(groups, capacity, *native_cells.flat())
    for first, second, third in zip(_dump(python), _dump(restored), _dump(again)):
        assert same(first, second) and same(first, third)


@needs_native
def test_dense_views_stay_valid_and_unchanged_after_the_block_changes() -> None:
    pools = LivePools(["a", "b", "c"])
    pools.load("lexical:x", [Distribution.fixed("old")] * 3)
    pools.innovate("lexical:x", "a", "new", 0.25)
    (block,) = pools.iter_blocks()
    assert block.native is not None
    view = block.freqs
    snapshot = view.copy()
    pools.innovate("lexical:x", "b", "newer", 0.5)  # změna bloku neukáže starému pohledu cizí data
    assert same(view, snapshot) and not view.flags.writeable
    (moved,) = pools.iter_blocks()  # proměnná přešla do většího bloku
    assert moved.freqs.sum() == snapshot.sum() and moved.freqs.shape[2] == 4
    moved.freqs  # noqa: B018 - sestaví hustý pohled
    moved.add_share(0, 2, 1, 0.5)
    assert moved.freqs[0, 2, 1] == 0.5 and same(view, snapshot)
    del view


@needs_native
def test_pool_block_pickle_roundtrip_between_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    pools = LivePools(["a", "b", "c"])
    pools.load("lexical:x", [Distribution.fixed("old")] * 3)
    pools.innovate("lexical:x", "c", "new", 0.3)
    saved = pickle.dumps(pools)
    monkeypatch.setenv("CEE_NATIVE", "0")
    python_pools = pickle.loads(saved)
    (python_block,) = python_pools.iter_blocks()
    assert isinstance(python_block._cells, PyCells)
    monkeypatch.delenv("CEE_NATIVE")
    (block,) = pools.iter_blocks()
    assert same(python_block.freqs, block.freqs) and same(python_block.previous, block.previous)
    assert isinstance(pickle.loads(pickle.dumps(python_pools)).iter_blocks().__next__().native, type(block.native))


# --- celý běh ------------------------------------------------------------------------


def _run(monkeypatch: pytest.MonkeyPatch, **environment: str) -> tuple[str, str]:
    from edit_worlds import fingerprint

    from cee.v2.scenarios import village_grid
    from cee.v2.simulation import Simulation

    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    world = village_grid(4, 3, seed=5, syntax=True, semantics=True, morphology=True)
    simulation = Simulation(world)
    simulation.run(400)
    return simulation.history.digest(), fingerprint(simulation.world)


@needs_native
def test_run_is_bit_identical_with_and_without_rust_and_for_any_thread_count(monkeypatch: pytest.MonkeyPatch) -> None:
    python = _run(monkeypatch, CEE_NATIVE="0")
    monkeypatch.delenv("CEE_NATIVE")
    assert _run(monkeypatch, CEE_THREADS="1") == python
    assert _run(monkeypatch, CEE_THREADS="3") == python


@needs_native
def test_transmission_with_a_library_mismatch_falls_back_to_python(monkeypatch: pytest.MonkeyPatch) -> None:
    reference = _run(monkeypatch, CEE_NATIVE="0")
    monkeypatch.delenv("CEE_NATIVE")
    monkeypatch.setattr(native, "_LIBM", False)  # jako stroj, kde knihovna systému dává jiné bity
    assert not native.transmit_enabled()
    assert _run(monkeypatch) == reference


def test_python_pool_block_has_no_native_cells(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CEE_NATIVE", "0")
    block = PoolBlock(3, 2)
    assert block.native is None and isinstance(block._cells, PyCells)
