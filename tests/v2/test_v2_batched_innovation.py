"""Testy dávkového losování inovací a funkce hash_poisson."""

from __future__ import annotations

import math

import numpy as np
import pytest

import cee.v2.simulation
from cee.v2.changes import DEFAULT_CHANGES, InnovationContext
from cee.v2.rng import Stream, hash_poisson
from cee.v2.scenarios import Language, Place, contact_world, village_grid
from cee.v2.simulation import Simulation
from cee.v2.transmission import _normalized


def test_normalized_capacity_invariance() -> None:
    """_normalized dává bitově shodný výsledek pro kapacitu 4 a tentýž řádek doplněný nulami na 8 a 16."""
    row4 = np.array([0.123456789, 0.234567891, 0.345678912, 0.296296408], dtype=np.float64)
    row8 = np.array([0.0, 0.0, 0.0, 0.0, *row4], dtype=np.float64)
    row16 = np.array([*[0.0] * 12, *row4], dtype=np.float64)

    arr4 = row4.reshape(1, 1, 4)
    arr8 = row8.reshape(1, 1, 8)
    arr16 = row16.reshape(1, 1, 16)

    norm4 = _normalized(arr4, arr4)
    norm8 = _normalized(arr8, arr8)
    norm16 = _normalized(arr16, arr16)

    # Nulové sloty musí zůstat 0.0
    np.testing.assert_array_equal(norm8[0, 0, :4], 0.0)
    np.testing.assert_array_equal(norm16[0, 0, :12], 0.0)

    # Nenulové sloty musí být bitově identické
    np.testing.assert_array_equal(norm8[0, 0, 4:], norm4[0, 0])
    np.testing.assert_array_equal(norm16[0, 0, 12:], norm4[0, 0])


def test_innovate_and_innovate_with_equivalence() -> None:
    """_innovate v dávce a po částech volané _innovate_with dají pro stejný stav v 1 ticku bitově shodný výsledek."""
    world1 = village_grid(4, seed=7, syntax=True, semantics=True)
    sim1 = Simulation(world1)
    sim1._innovate(sim1.year)

    world2 = village_grid(4, seed=7, syntax=True, semantics=True)
    sim2 = Simulation(world2)
    for group_id in sim2.world.group_ids():
        group = sim2.world.groups[group_id]
        if group.written:
            continue
        renewal = sim2.world.renewal(group_id, sim2.config.dt)
        context = InnovationContext(sim2.world, group, group.main_code, sim2.tick, sim2.year)
        for change in sim2.changes:
            sim2._innovate_with(change, context, renewal)

    assert sim1.history.events == sim2.history.events
    assert sim1.history.digest() == sim2.history.digest()


def test_hash_poisson_determinism() -> None:
    """Opakované volání se stejnými parametry vrátí bitově shodný výsledek."""
    rows = np.array([101, 102], dtype=np.uint64)
    cols = np.array([201, 202, 203], dtype=np.uint64)
    lam = np.array([[0.05, 1.5, 35.0], [150.0, 0.0, 2.5]], dtype=np.float64)

    run1 = hash_poisson(rows, cols, lam)
    run2 = hash_poisson(rows, cols, lam)
    np.testing.assert_array_equal(run1, run2)

    run_pw1 = hash_poisson(rows, rows, np.array([1.5, 45.0]), pairwise=True)
    run_pw2 = hash_poisson(rows, rows, np.array([1.5, 45.0]), pairwise=True)
    np.testing.assert_array_equal(run_pw1, run_pw2)


def test_hash_poisson_element_independence() -> None:
    """Výsledek pro každý prvek závisí výhradně na jeho klíči a střední hodnotě.

    Prvek (i, j) v matici musí bitově odpovídat samostatnému volání i pairwise volání.
    Přerovnání řádků/sloupců ani přechod sousedního prvku přes hranici lam = 30.0
    nesmí změnit výsledek na dané pozici.
    """
    rows = np.array([10, 20, 30], dtype=np.uint64)
    cols = np.array([100, 200], dtype=np.uint64)
    lam = np.array(
        [
            [0.8, 35.0],
            [5.0, 0.0],
            [40.0, 1.2],
        ],
        dtype=np.float64,
    )

    res_matrix = hash_poisson(rows, cols, lam)

    # Ověříme každý prvek zvlášť v matici 1x1 i přes pairwise=True
    for i in range(len(rows)):
        for j in range(len(cols)):
            elem_val = res_matrix[i, j]
            res_single = hash_poisson(
                np.array([rows[i]]), np.array([cols[j]]), np.array([[lam[i, j]]])
            )[0, 0]
            res_pw = hash_poisson(
                np.array([rows[i]]),
                np.array([cols[j]]),
                np.array([lam[i, j]]),
                pairwise=True,
            )[0]
            assert elem_val == res_single
            assert elem_val == res_pw

    # Přerovnání řádků
    perm_rows = np.array([20, 10, 30], dtype=np.uint64)
    perm_lam = lam[[1, 0, 2], :]
    res_perm = hash_poisson(perm_rows, cols, perm_lam)
    np.testing.assert_array_equal(res_perm, res_matrix[[1, 0, 2], :])

    # Změna sousedního prvku přes hranici lam = 30.0 (prvek [0, 0] z 0.8 na 80.0)
    lam_changed = lam.copy()
    lam_changed[0, 0] = 80.0
    res_changed = hash_poisson(rows, cols, lam_changed)
    # Všechny ostatní prvky musí zůstat nezměněné
    assert res_changed[0, 1] == res_matrix[0, 1]
    np.testing.assert_array_equal(res_changed[1:, :], res_matrix[1:, :])


def test_hash_poisson_zero_and_invalid() -> None:
    """Nulová lambda vrátí 0, záporné, NaN, nekonečné a nekompatibilní vstupy selžou."""
    rows = np.array([1, 2], dtype=np.uint64)
    cols = np.array([10, 20], dtype=np.uint64)

    # Nulová střední hodnota
    res = hash_poisson(rows, cols, np.zeros((2, 2), dtype=np.float64))
    np.testing.assert_array_equal(res, 0)

    # Záporná střední hodnota
    with pytest.raises(ValueError, match="nezáporná konečná čísla"):
        hash_poisson(rows, cols, np.array([[1.0, -0.5], [0.0, 1.0]], dtype=np.float64))

    # NaN
    with pytest.raises(ValueError, match="nezáporná konečná čísla"):
        hash_poisson(rows, cols, np.array([[1.0, float("nan")], [0.0, 1.0]], dtype=np.float64))

    # Nekonečno
    with pytest.raises(ValueError, match="nezáporná konečná čísla"):
        hash_poisson(rows, cols, np.array([[float("inf"), 1.0], [0.0, 1.0]], dtype=np.float64))

    # Neshoda rozměrů bez pairwise
    with pytest.raises(ValueError, match="neodpovídá tvaru"):
        hash_poisson(rows, cols, np.zeros((3, 2), dtype=np.float64))

    # Neshoda rozměrů v pairwise
    with pytest.raises(ValueError, match="stejný tvar"):
        hash_poisson(rows, cols[:1], np.zeros(2, dtype=np.float64), pairwise=True)


def test_hash_poisson_statistics() -> None:
    """Statistická shoda výběrového průměru a rozptylu s Poissonovým rozdělením."""
    n = 10_000
    rows = np.arange(1, n + 1, dtype=np.uint64)
    cols = np.full(n, 777_888, dtype=np.uint64)

    # Testujeme malé i velké střední hodnoty
    test_lambdas = [0.08, 2.5, 45.0, 250.0]

    for lam in test_lambdas:
        draws = hash_poisson(rows, cols, np.full(n, lam, dtype=np.float64), pairwise=True)
        mean = float(np.mean(draws))
        var = float(np.var(draws, ddof=1))

        # Chyba průměru: sd_mean = sqrt(lam / n) -> 4 sigma
        sd_mean = math.sqrt(lam / n)
        assert abs(mean - lam) < 4.0 * sd_mean, f"Průměr {mean} se liší od lam {lam}"

        # Chyba rozptylu: var(S^2) pro Poisson = (lam + 2*lam^2) / n -> 4 sigma
        sd_var = math.sqrt((lam + 2.0 * (lam**2)) / n)
        assert abs(var - lam) < 4.0 * sd_var, f"Rozptyl {var} se liší od lam {lam}"


def test_innovate_skips_stream_when_zero_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """Při nulovém vylosovaném počtu inovací se cee.v2.simulation.Stream vůbec nevytváří."""
    called_keys: list[tuple[object, ...]] = []

    class SpyStream(Stream):
        __slots__ = ()

        def __init__(self, seed: int, *parts: object) -> None:
            called_keys.append((seed, *parts))
            super().__init__(seed, *parts)

    poisson_results: list[np.ndarray] = []
    real_hash_poisson = cee.v2.simulation.hash_poisson

    def spy_hash_poisson(
        row_keys: np.ndarray,
        column_keys: np.ndarray,
        expected: np.ndarray,
        *,
        pairwise: bool = False,
    ) -> np.ndarray:
        res = real_hash_poisson(row_keys, column_keys, expected, pairwise=pairwise)
        poisson_results.append(res)
        return res

    monkeypatch.setattr(cee.v2.simulation, "Stream", SpyStream)
    monkeypatch.setattr(cee.v2.simulation, "hash_poisson", spy_hash_poisson)

    world = village_grid(4, seed=5, phonology=True)
    sim = Simulation(world)
    sim.run(200)

    nonzero_draws = sum(int(np.count_nonzero(res)) for res in poisson_results)
    zero_draws = sum(int(np.sum(res == 0)) for res in poisson_results)

    gen_inno_calls = [c for c in called_keys if len(c) >= 2 and c[1] == "innovation"]

    assert nonzero_draws > 0
    assert zero_draws > 5 * nonzero_draws
    assert len(gen_inno_calls) == nonzero_draws


def test_innovation_history_ordering() -> None:
    """Pořadí záznamů v historii odpovídá group_ids() a v rámci skupiny self.changes."""
    world = village_grid(4, 2, seed=3, syntax=True, semantics=True)
    sim = Simulation(world)
    sim.run(100)

    group_order = {gid: idx for idx, gid in enumerate(world.group_ids())}
    change_order = {ch.kind: idx for idx, ch in enumerate(DEFAULT_CHANGES)}

    # Pro každý tick zkontrolujeme monotónnost skupin a změn
    events_by_tick: dict[int, list[dict[str, object]]] = {}
    for event in sim.history.events:
        if event["kind"] == "innovation":
            events_by_tick.setdefault(int(event["tick"]), []).append(event)

    for tick, events in events_by_tick.items():
        pairs = [(group_order[str(e["group"])], change_order[str(e["change"])]) for e in events]
        # Dvojice (group_idx, change_idx) musí být neklesající
        for i in range(len(pairs) - 1):
            assert pairs[i] <= pairs[i + 1], f"V ticku {tick} porušeno pořadí: {pairs[i]} > {pairs[i+1]}"


def test_resume_checkpoint_exact_digest() -> None:
    """Pokračování z checkpointu dává bitově shodný digest historie s nepřerušeným během."""
    world1 = village_grid(4, seed=2, phonology=True)
    sim1 = Simulation(world1)
    sim1.run(200)
    digest_full = sim1.history.digest()

    world2 = village_grid(4, seed=2, phonology=True)
    sim2 = Simulation(world2)
    sim2.run(100)
    cp = sim2.checkpoint()

    sim_resumed = Simulation.resume(cp)
    sim_resumed.run(200)
    digest_resumed = sim_resumed.history.digest()

    assert digest_resumed == digest_full


def test_area_isolation() -> None:
    """Rozdělení jedné oblasti na víc skupin nezmění inovace ani historii nepropojené oblasti."""
    # Svět A: skupina v oblasti 1 + jedna skupina v oblasti 2
    lang_a = Language("p1", (Place("g1", (0.0, 0.0), population=500),))
    lang_b1 = Language("p2", (Place("g2", (500.0, 500.0), population=500),))
    world_a = contact_world([lang_a, lang_b1], seed=42)

    # Svět B: stejná skupina v oblasti 1 + DVĚ skupiny v oblasti 2
    lang_b2 = Language(
        "p2",
        (
            Place("g2", (500.0, 500.0), population=500),
            Place("g3", (505.0, 500.0), population=500),
        ),
    )
    world_b = contact_world([lang_a, lang_b2], seed=42)

    sim_a = Simulation(world_a)
    sim_a.run(200)

    sim_b = Simulation(world_b)
    sim_b.run(200)

    # Porovnáme historii skupiny g1 mezi oběma světy
    events_g1_a = [e for e in sim_a.history.events if e.get("group") == "g1"]
    events_g1_b = [e for e in sim_b.history.events if e.get("group") == "g1"]

    assert len(events_g1_a) > 0
    assert events_g1_a == events_g1_b
