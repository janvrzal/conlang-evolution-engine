"""Pozorování v Rustu (B6a): shoda s Pythonem bit po bitu.

Rust (``rust/cee_core/src/observe.rs``) a Python reference (``cee.v2.observe``) čtou tatáž pole
(``_gather``) a musí dát stejné bity: rysy skupin (vložení podílů, čtverce, kategorie tvarů
a vzdálenosti tvarů), kandidáty sloučení, obě průměrné vazby i matice vzdáleností kódů. Zlatá
data pozorování ze skutečných běhů hlídá ``test_v2_golden_observe.py``.
"""

from __future__ import annotations

import copy
import os

import numpy as np
import pytest

from cee.v2 import native
from cee.v2 import observe as observation
from cee.v2.observe import (
    LineageTracker,
    _candidates,
    _Features,
    _gather,
    _geometry,
    _Input,
    _native_forms,
    _native_pools,
    code_distances,
    constrained_average_linkage,
    form_distance,
    observe,
)
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation, SimulationConfig
from tests.v2.edit_worlds import church_school

needs_native = pytest.mark.skipif(
    os.environ.get("CEE_NATIVE") == "0" or not native.observe_enabled(),
    reason="rozšíření cee_core není sestavené, je vypnuté, nebo se numpy a knihovny systému s Rustem rozcházejí",
)


def rust_step(inp, world, group_ids, labels, limits=(0.02, 0.05, 0.005), distances=False, threads=1, detail=True):
    """Jedno volání ``observe_step`` nad vstupem ``inp`` (s geometrií světa ``world`` nebo prázdnou)."""
    step = native.kernel("observe_step")
    assert step is not None
    if world is None:
        empty = np.zeros(0, dtype=np.int64)
        links, places = (empty, empty), (empty, np.zeros(0), np.zeros(0))
    else:
        links, places = _geometry(world, group_ids)
    forms = None if inp.forms is None else _native_forms(inp.forms)
    return step(
        _native_pools(inp), inp.live, inp.columns, forms, inp.lexical, links, places,
        np.asarray(labels, dtype=np.int64), limits, distances, threads, detail,
    )


def same_dicts(csr, dicts):
    """Slovníky v CSR z Rustu se shodují s Python slovníky včetně pořadí vkládání a bitů hodnot."""
    ptr, cols, vals = csr
    assert len(ptr) == len(dicts) + 1
    for index, item in enumerate(dicts):
        span = slice(ptr[index], ptr[index + 1])
        assert cols[span].tolist() == list(item.keys())
        assert vals[span].tobytes() == np.array(list(item.values()), dtype=np.float64).tobytes()


@pytest.fixture(scope="module")
def diverged():
    """Svět s rozcházejícími se slovy, tvary i konstrukcemi (dialekty a víc kategorií tvarů)."""
    world = village_grid(5, 3, seed=2, syntax=True, semantics=True)
    Simulation(world).run(900)
    return world


def spoken_columns(world, every=1):
    ids = list(world.live.group_ids)
    return ids[::every], np.arange(0, len(ids), every, dtype=np.int64)


@needs_native
@pytest.mark.parametrize("every", [1, 2])
def test_rysy_kandidati_a_shluky_jsou_stejne_jako_v_pythonu(diverged, every):
    world = diverged
    ids, columns = spoken_columns(world, every)
    inp = _gather(world, columns)
    reference = observation._features(inp)
    pairs = _candidates(*_geometry(world, ids))
    labels = [index % 3 - 1 for index in range(len(ids))]
    dialects, languages, matrix, detail = rust_step(inp, world, ids, labels)
    assert matrix is None
    shares, squares, forms, spread, found = detail
    assert shares.dtype == np.float32 and shares.tobytes() == reference.shares.tobytes()
    assert squares.tobytes() == reference.squares.tobytes()
    same_dicts(forms, reference.forms)
    same_dicts(spread, reference.spread)
    assert [tuple(pair) for pair in found.tolist()] == pairs
    assert any(len(item) > 1 for item in reference.spread), "svět má nesouhlasné tvary příbuzných slov"
    assert dialects == constrained_average_linkage(reference, pairs, 0.02)
    assert languages == constrained_average_linkage(reference, pairs, 0.05, labels=labels, margin=0.005)


@needs_native
def test_vice_vlaken_da_stejne_bity(diverged):
    ids, columns = spoken_columns(diverged)
    inp = _gather(diverged, columns)
    one = rust_step(inp, diverged, ids, [-1] * len(ids), distances=True, threads=1)
    for threads in (2, 3, 7):
        many = rust_step(inp, diverged, ids, [-1] * len(ids), distances=True, threads=threads)
        assert many[:2] == one[:2]
        assert many[2].tobytes() == one[2].tobytes()
        assert many[3][0].tobytes() == one[3][0].tobytes() and many[3][1].tobytes() == one[3][1].tobytes()


@needs_native
def test_vyber_vzorku_promennych_a_vlozeni_na_syntetickych_blocich():
    """Nad 2 000 proměnlivých sloupců se vybírá vzorek podle pořadí proměnných; Rust vybere totéž."""
    rng = np.random.default_rng(7)
    groups, pools = 7, []
    for rows, capacity in ((400, 4), (150, 7), (30, 2)):
        freqs = rng.random((rows + 3, groups, capacity)) * (rng.random((rows + 3, groups, capacity)) < 0.6)
        freqs[::5] = freqs[::5, :1]  # proměnné, které jsou všude stejné
        present = rng.random((rows + 3, groups)) < 0.9
        chosen = np.sort(rng.choice(rows + 3, rows, replace=False)).astype(np.int64)
        pools.append((freqs, present, chosen, np.zeros(rows, dtype=np.int64)))
    ranks = rng.permutation(sum(len(pool[2]) for pool in pools)).astype(np.int64)
    start = 0
    for index, (freqs, present, chosen, _) in enumerate(pools):
        pools[index] = (freqs, present, chosen, ranks[start : start + len(chosen)])
        start += len(chosen)
    inp = _Input(None, groups, np.arange(groups, dtype=np.int64), pools, None, 11)  # type: ignore[arg-type]
    reference = observation._features(inp)
    assert reference.shares.shape[1] // 13 < sum(len(pool[2]) * pool[0].shape[2] for pool in pools)
    _, _, _, detail = rust_step(inp, None, [], [-1] * groups)
    assert detail[0].tobytes() == reference.shares.tobytes()
    assert detail[1].tobytes() == reference.squares.tobytes()
    # Bez vzorku (málo sloupců) je výsledek také stejný.
    small = _Input(None, groups, np.array([0, 2, 3], dtype=np.int64), [(*pools[2][:3], pools[2][3])], None, 4)  # type: ignore[arg-type]
    _, _, _, detail = rust_step(small, None, [], [-1] * 3)
    assert detail[0].tobytes() == observation._features(small).shares.tobytes()


def random_features(rng, groups, dim):
    shares = (rng.random((groups, dim)) * (rng.random((groups, dim)) < 0.5) * 2.0).astype(np.float32)
    if groups > 2:
        shares[1] = shares[0]  # shodné skupiny: vzdálenost je šum čísel
    squares = (shares.astype(np.float64) ** 2).sum(axis=1)
    columns = 40

    def table(weights):
        found = []
        for _ in range(groups):
            order = rng.permutation(columns)[: rng.integers(0, 25)]
            found.append({int(column): weights(column) for column in order})
        return found

    forms = table(lambda column: 1.0)
    spread = table(lambda column: float(rng.random() * 0.97))
    return _Features(shares, squares, forms, spread, int(rng.integers(1, 9)))


def csr(dicts):
    ptr, cols, vals = [0], [], []
    for item in dicts:
        cols += list(item.keys())
        vals += list(item.values())
        ptr.append(len(cols))
    return np.array(ptr, dtype=np.int64), np.array(cols, dtype=np.int64), np.array(vals, dtype=np.float64)


@needs_native
def test_prumerna_vazba_na_nahodnych_rysech_je_stejna_jako_v_pythonu():
    """Pořadí vkládání do slovníků, remízy a hystereze: stovky náhodných vstupů a prahů."""
    rng = np.random.default_rng(11)
    nontrivial = 0
    for case in range(150):
        groups = int(rng.integers(2, 30))
        dim = int(rng.choice([0, 13, 26, 130]))
        features = random_features(rng, groups, dim)
        pairs = sorted({(int(min(a, b)), int(max(a, b))) for a, b in rng.integers(0, groups, (groups * 3, 2)) if a != b})
        labels = None if case % 3 == 0 else rng.integers(-1, 4, groups)
        margin = 0.0 if case % 4 == 0 else float(rng.random() * 0.05)
        for threshold in (0.0, 0.05, 0.3, 1.0, 3.0, 1e9):
            expected = constrained_average_linkage(features, pairs, threshold, labels=labels, margin=margin)
            found = native.kernel("observe_linkage")(
                features.shares, features.squares, csr(features.forms), csr(features.spread), float(features.lexical),
                np.array(pairs, dtype=np.int64).reshape(-1, 2), threshold, labels, margin,
            )
            assert found == expected, (case, threshold)
            nontrivial += 1 < len(expected) < groups
    assert nontrivial > 100


@needs_native
def test_kandidati_na_nahodnych_polohach_jsou_stejni_jako_v_pythonu():
    rng = np.random.default_rng(5)
    for case in range(120):
        count = int(rng.integers(0, 70))
        kind = case % 4
        if kind == 0:
            xs, ys = rng.uniform(-50, 50, count), rng.uniform(-50, 50, count)
        elif kind == 1:  # mřížka s remízami ve vzdálenostech
            xs, ys = rng.integers(0, 8, count) * 12.5, rng.integers(0, 8, count) * 12.5
        elif kind == 2:  # shodné polohy
            xs, ys = np.repeat(rng.uniform(0, 9, 5), 14)[:count], np.repeat(rng.uniform(0, 9, 5), 14)[:count]
        else:  # jedna řada
            xs, ys = np.arange(count) * 0.3, np.full(count, -4.0)
        slots = np.sort(rng.choice(count + 5, count, replace=False)).astype(np.int64)
        links = rng.integers(0, count + 5, (int(rng.integers(0, 40)), 2)).astype(np.int64)
        expected = _candidates((links[:, 0].copy(), links[:, 1].copy()), (slots, xs, ys))
        found = native.kernel("observe_candidates")(links.reshape(-1, 2), slots, xs, ys)
        assert [tuple(pair) for pair in found.tolist()] == expected, case


@needs_native
def test_editacni_vzdalenost_tvaru_je_stejna_a_meni_se_s_delitelem(diverged, monkeypatch):
    world = diverged
    bank = world.form_bank()
    forms = [form for form in bank.forms if form]
    rng = np.random.default_rng(3)
    chosen = [forms[index] for index in rng.choice(len(forms), 200, replace=False)]
    chosen += [(), chosen[0], chosen[0][:1], chosen[1] + chosen[1]]
    ptr = np.concatenate([[0], np.cumsum([len(form) for form in chosen])]).astype(np.int64)
    flat = np.array([segment for form in chosen for segment in form], dtype=np.int32)
    pairs = rng.integers(0, len(chosen), (500, 2)).astype(np.int64)
    kernel = native.kernel("observe_edit_distances")
    for scale in (6.0, 12.0):
        monkeypatch.setattr(observation, "FEATURE_SCALE", scale)
        found = kernel(np.ascontiguousarray(world.table.vectors), scale, ptr, flat, pairs)
        expected = np.array([observation._edit_distance(world, chosen[a], chosen[b]) if chosen[a] != chosen[b]
                             and chosen[a] and chosen[b] else form_distance(world, chosen[a], chosen[b])
                             for a, b in pairs.tolist()])
        assert found.tobytes() == expected.tobytes()
    assert found.max() > 0.0


@needs_native
def test_matice_vzdalenosti_kodu_je_stejna_a_nezavisla_na_vlaknech(diverged, monkeypatch):
    world = diverged
    live = len(world.live.group_ids)
    native_distances = code_distances(world)
    monkeypatch.setattr(native, "observe_enabled", lambda: False)
    reference = code_distances(world)
    assert native_distances.tobytes() == reference.tobytes()
    assert reference.max() > 0.0
    inp = _gather(world, np.arange(live, dtype=np.int64), ranked=False)
    totals = native.kernel("observe_distance_totals")
    one = totals(_native_pools(inp), live, 4_000_000, 1)
    for threads in (2, 3, 5, 64):
        assert totals(_native_pools(inp), live, 4_000_000, threads).tobytes() == one.tobytes()
    # Po blocích po jednom řádku vyjde stejný součet jako ``numpy`` po blocích.
    expected = observation._distance_totals(inp.pools, live, 1)
    assert totals(_native_pools(inp), live, 1, 3).tobytes() == expected.tobytes()
    cognate = native.kernel("observe_cognate_totals")(live, _native_forms(inp.forms))
    assert cognate.tobytes() == observation.cognate_matrix(world, world.live.group_ids).tobytes()
    assert cognate.max() > 0.0


def test_vyber_tvaru_nic_nezarazuje_do_banky_a_odpovida_slovniku_kodu(diverged):
    """Tvary dominantních kořenů jako čísla do tabulky různých tvarů; výchozí tvary mimo banku také."""
    for world in (village_grid(3, seed=1, syntax=True, semantics=True), diverged):
        world = copy.deepcopy(world)
        size = len(world.form_bank().forms)
        inp = _gather(world, np.arange(len(world.live.group_ids), dtype=np.int64))
        forms = inp.forms
        assert forms is not None and len(world.form_bank().forms) == size
        morphemes = world.registry.morphemes.names
        concepts = world.registry.concepts.names
        for index, group_id in enumerate(world.live.group_ids):
            code = world.groups[group_id].main_code
            span = slice(forms.ptr[index], forms.ptr[index + 1])
            found = [(concepts[c], morphemes[r], forms.form_of(f))
                     for c, r, f in zip(forms.concept[span], forms.root[span], forms.form[span])]
            expected = [(concept, root, world.form_of(code, root)) for concept, root in code.phonology.dominant.items()]
            assert found == expected
        # Tvary jsou různé a každý jen jednou (stejný obsah, stejné číslo).
        contents = [forms.form_of(number) for number in range(len(forms.form_ptr) - 1)]
        assert len(set(contents)) == len(contents)


@needs_native
def test_cele_pozorovani_se_stavem_sledovace_linii_je_stejne_v_obou_cestach(monkeypatch):
    """Svět s psaným kódem a veřejnou doménou (jen část skupin je mluvená) a dosavadní linie skupin."""
    world, events, _ = church_school()
    simulation = Simulation(world, events=events)
    simulation.run(world.start_year + 25.0 * 8)
    spoken = [g for g in world.live.group_ids if not world.groups[g].written and world.groups[g].domain == "home"]
    assert 0 < len(spoken) < len(world.live.group_ids)
    results = []
    for use_native in (True, False):
        monkeypatch.setattr(native, "observe_enabled", lambda use=use_native: use)
        tracker = LineageTracker()
        seen = []
        for tick, (dialect, language) in enumerate(((0.004, 0.02), (0.02, 0.05), (0.01, 0.03), (0.5, 0.5))):
            snapshot, found = observe(
                world, tick, 2.0 * tick, tracker, dialect_threshold=dialect, language_threshold=language,
                keep_distances=tick % 2 == 0,
            )
            distances = None if snapshot.distances is None else snapshot.distances.tobytes()
            seen.append((snapshot.group_ids, snapshot.dialects, snapshot.languages, distances, found))
        results.append(seen)
    assert results[0] == results[1]
    assert any(len(item[1]) > 1 for item in results[0])


@needs_native
def test_beh_s_pozorovanim_dava_stejny_otisk_a_matice_v_obou_cestach(monkeypatch):
    runs = []
    for use_native in (True, False):
        monkeypatch.setattr(native, "observe_enabled", lambda use=use_native: use)
        world = village_grid(3, 2, seed=4, syntax=True, semantics=True)
        simulation = Simulation(world, config=SimulationConfig(keep_distances=True, observe_every=2))
        simulation.run(600)
        history = simulation.history
        runs.append((history.digest(), [item.distances.tobytes() for item in history.snapshots],
                     [(item.dialects, item.languages) for item in history.snapshots]))
    assert runs[0] == runs[1]
    assert len(runs[0][1]) > 5
