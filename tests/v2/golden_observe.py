"""Společné části zlatých dat pozorování: záznam jednoho ticku a jeho výpočet v obou režimech.

Skript ``scripts/v2_golden_observe.py`` záznamy pořídí (Python reference), test
``test_v2_golden_observe.py`` je ověří v Pythonu i v Rustu bit po bitu.

**Vstup a výstup pozorování** (``cee.v2.observe``). Vstupem je stav světa v ticku (běh scénáře
z ``tests/v2/golden_worlds.py``, bitově shodný s otisky) a dosavadní linie skupin (stav
``LineageTracker``, který se vlákny stejných ticků předává). Záznam ticku obsahuje:

- ``features``: rysy mluvených skupin: otisk SHA-256 matice vložení (``float32``) a čtverce
  skupin (``float64``), počty a otisky slovníků kategorií tvarů a rozptylu (v pořadí vkládání);
- ``pairs``: kandidáti sloučení;
- ``runs``: pro každou dvojici prahů dialekty, jazyky a události ``LineageTracker.update`` a
  (u prvního běhu) otisk matice vzdáleností kódů;
- ``edit``: editační vzdálenosti všech dvojic z vybraných tvarů banky.
"""

from __future__ import annotations

import contextlib
import hashlib
from collections.abc import Iterator, Sequence
from typing import Any

import numpy as np

from cee.v2 import native
from cee.v2 import observe as observation
from cee.v2.observe import LineageTracker, observe
from cee.v2.rng import Stream
from cee.v2.simulation import Simulation
from tests.v2 import golden_worlds as worlds

#: Dvojice prahů (dialekty, jazyky) každého běhu pozorování: výchozí a čtvrtinové.
THRESHOLDS = ((0.05, 0.25), (0.0125, 0.0625))
#: Kolik tvarů banky se porovná mezi sebou (všechny dvojice).
EDIT_FORMS = 24


@contextlib.contextmanager
def mode(use_native: bool) -> Iterator[None]:
    """Pozorování se počítá v Rustu (``True``), nebo Python referencí (``False``)."""
    original = native.observe_enabled
    native.observe_enabled = lambda: use_native  # type: ignore[assignment]
    try:
        yield
    finally:
        native.observe_enabled = original  # type: ignore[assignment]


def digest(*arrays: np.ndarray) -> str:
    hasher = hashlib.sha256()
    for array in arrays:
        hasher.update(np.ascontiguousarray(array).tobytes())
    return hasher.hexdigest()


def csr(dicts: Sequence[dict[int, float]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ptr, cols, vals = [0], [], []
    for item in dicts:
        cols += list(item.keys())
        vals += list(item.values())
        ptr.append(len(cols))
    return np.array(ptr, dtype=np.int64), np.array(cols, dtype=np.int64), np.array(vals, dtype=np.float64)


def csr_of(item: tuple[np.ndarray, np.ndarray, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return item[0].astype(np.int64), item[1].astype(np.int64), item[2].astype(np.float64)


def spoken_of(world: Any) -> tuple[list[str], np.ndarray]:
    """Mluvené skupiny (psaný kód a veřejná doména se nepočítají) a jejich čísla mezi živými."""
    spoken = [index for index, group_id in enumerate(world.live.group_ids)
              if not world.groups[group_id].written and world.groups[group_id].domain == "home"]
    return [world.live.group_ids[index] for index in spoken], np.array(spoken, dtype=np.int64)


def features_of(world: Any, use_native: bool) -> dict[str, Any]:
    """Rysy mluvených skupin a kandidáti sloučení z Rustu, nebo z Pythonu (bez záznamu čísel pojmů)."""
    ids, columns = spoken_of(world)
    inp = observation._gather(world, columns)
    if use_native:
        step = native.kernel("observe_step")
        assert step is not None
        links, places = observation._geometry(world, ids)
        forms = None if inp.forms is None else observation._native_forms(inp.forms)
        _, _, _, detail = step(
            observation._native_pools(inp), inp.live, inp.columns, forms, inp.lexical, links, places,
            np.full(len(ids), -1, dtype=np.int64), (0.0, 0.0, 0.0), False, native.threads(), True,
        )
        shares, squares, forms_csr, spread_csr, pairs = detail
        pairs = [tuple(pair) for pair in pairs.tolist()]
        forms_csr, spread_csr = csr_of(forms_csr), csr_of(spread_csr)
    else:
        found = observation._features(inp)
        shares, squares = found.shares, found.squares
        forms_csr, spread_csr = csr(found.forms), csr(found.spread)
        pairs = observation._candidates(*observation._geometry(world, ids))
    return {
        "shares": {"shape": list(shares.shape), "dtype": str(shares.dtype), "sha256": digest(shares)},
        "squares": [float(value) for value in squares],
        "forms": {"entries": int(len(forms_csr[1])), "sha256": digest(*forms_csr)},
        "spread": {"entries": int(len(spread_csr[1])), "sha256": digest(*spread_csr)},
        "pairs": [list(pair) for pair in pairs],
    }


def edit_forms(world: Any, name: str, tick: int) -> list[tuple[int, ...]]:
    """Tvary vybrané deterministicky z různých podkladových tvarů dominantních kořenů (seřazených podle
    obsahu, ne podle čísel v bance, která se mezi režimy liší) a prázdný tvar."""
    forms = sorted({world.form_of(world.groups[group_id].main_code, root)
                    for group_id in world.live.group_ids
                    for root in world.groups[group_id].main_code.phonology.dominant.values()})
    chosen = worlds.sample(Stream(0, "golden-edit", name, tick), range(len(forms)), EDIT_FORMS - 1)
    return [(), *(forms[index] for index in chosen)]


def edit_distances(world: Any, forms: Sequence[tuple[int, ...]], use_native: bool) -> list[float]:
    """Vzdálenosti všech dvojic ``i < j`` z ``forms``."""
    pairs = [(a, b) for a in range(len(forms)) for b in range(a + 1, len(forms))]
    if use_native:
        ptr = np.concatenate([[0], np.cumsum([len(form) for form in forms])]).astype(np.int64)
        flat = np.array([segment for form in forms for segment in form], dtype=np.int32)
        kernel = native.kernel("observe_edit_distances")
        assert kernel is not None
        found = kernel(
            np.ascontiguousarray(world.table.vectors), observation.FEATURE_SCALE, ptr, flat,
            np.array(pairs, dtype=np.int64),
        )
        return [float(value) for value in found]
    return [observation.form_distance(world, forms[a], forms[b]) for a, b in pairs]


def runs_of(simulation: Simulation, trackers: Sequence[LineageTracker], use_native: bool) -> list[dict[str, Any]]:
    """``observe`` pro každou dvojici prahů s vlastním ``LineageTracker`` (ten se mezi ticky předává)."""
    found = []
    for index, ((dialect, language), tracker) in enumerate(zip(THRESHOLDS, trackers)):
        snapshot, events = observe(
            simulation.world, simulation.tick, simulation.year, tracker, dialect_threshold=dialect,
            language_threshold=language, keep_distances=index == 0,
        )
        spoken = list(snapshot.group_ids)
        entry: dict[str, Any] = {
            "dialects": [[spoken.index(group) for group in cluster] for cluster in snapshot.dialects],
            "languages": {lineage: [spoken.index(group) for group in members]
                          for lineage, members in snapshot.languages.items()},
            "events": events,
        }
        if snapshot.distances is not None:
            entry["distances"] = {"shape": list(snapshot.distances.shape), "sha256": digest(snapshot.distances),
                                  "sums": [float(value) for value in snapshot.distances.sum(axis=1)]}
        found.append(entry)
    return found


def record_tick(
    simulation: Simulation, name: str, trackers: Sequence[LineageTracker], use_native: bool
) -> dict[str, Any]:
    """Záznam jednoho ticku v daném režimu (viz modul)."""
    world = simulation.world
    forms = edit_forms(world, name, simulation.tick)
    with mode(use_native):
        return {
            "tick": simulation.tick,
            "groups": spoken_of(world)[0],
            "features": features_of(world, use_native),
            "runs": runs_of(simulation, trackers, use_native),
            "edit": {"forms": [list(form) for form in forms], "distances": edit_distances(world, forms, use_native)},
        }
