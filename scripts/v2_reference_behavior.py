"""Referenční souhrn chování enginu v2 v Pythonu pro kalibraci Rustu.

Pro scénáře ze ``scripts/v2_digests.py`` a semínka 1 až 3 spočítá souhrn chování
(počty inovací podle druhu změny, ustálené a zaniklé varianty, uzavřené procesy,
fonologizovaná slova, analogie, gramatikalizace, retenci slovní zásoby, vzdálenost
sousedů a počty nářečí a jazyků v čase, přechody jazyka) a uloží ho do
``tests/v2/data/reference_behavior.json``. Rust počítá totéž příkazem
``cee behavior`` (stejný tvar výstupu) a porovnání dělá ``scripts/v2_compare_behavior.py``.

Pustit jednou, v jednom procesu, bez Rust rozšíření:
    CEE_NATIVE=0 PYTHONPATH=src:. python scripts/v2_reference_behavior.py

Soubor se po každém běhu přepíše, takže přerušený běh nechá hotové části.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

from cee.v2.metrics import retention
from cee.v2.scenarios import island_and_city, language_shift, village_grid
from cee.v2.simulation import Simulation, SimulationConfig

SEEDS = (1, 2, 3)
#: Roky snímků, které se do souhrnu berou (snímky vznikají po 100 letech).
SNAPSHOT_YEARS = (200, 500, 1000, 1500, 2000)
OUTPUT = Path(__file__).resolve().parent.parent / "tests" / "v2" / "data" / "reference_behavior.json"


def worlds():
    """(jméno, továrna ``seed -> (svět, události)``, délka v letech); pořadí od nejlevnějšího."""
    yield "phonology", lambda s: (village_grid(4, seed=s, phonology=True), ()), 1000
    yield "morphology", lambda s: (village_grid(4, seed=s, morphology=True, semantics=True), ()), 1000
    yield "syntax", lambda s: (village_grid(4, seed=s, syntax=True, semantics=True), ()), 1000
    yield "grid-5x5", lambda s: (village_grid(5, 5, seed=s, morphology=True, semantics=True), ()), 1000
    yield "shift", lambda s: language_shift(s, start=300.0), 900
    yield "island-city", lambda s: (island_and_city(s), ()), 800
    yield "valley-50", lambda s: (village_grid(10, 5, seed=s, syntax=True, semantics=True), ()), 2000


def neighbour_distance(world, snapshot) -> float | None:
    """Průměr vzdáleností jazyka mezi nejbližšími sousedy mřížky (geografická vzdálenost = rozestup)."""
    ids = list(snapshot.group_ids)
    try:
        positions = [world.position_of(group_id) for group_id in ids]
    except KeyError:  # skupina bez území (např. přistěhovalci)
        return None
    if snapshot.distances is None or len(ids) < 2 or any(p is None for p in positions):
        return None
    pairs = [
        (i, j, math.dist(positions[i], positions[j]))
        for i in range(len(ids)) for j in range(i + 1, len(ids))
    ]
    positive = [d for _, _, d in pairs if d > 1e-9]
    if not positive:
        return None
    step = min(positive)
    values = [float(snapshot.distances[i, j]) for i, j, d in pairs if d <= step * 1.001]
    return sum(values) / len(values) if values else None


def summarize(world, simulation) -> dict:
    history = simulation.history
    innovation_change = {e["variant"]: e["change"] for e in history.of_kind("innovation")}
    innovations = Counter(innovation_change.values())
    established = Counter(innovation_change[e["variant"]] for e in history.of_kind("established") if e["variant"] in innovation_change)
    extinct = Counter(innovation_change[e["variant"]] for e in history.of_kind("extinct") if e["variant"] in innovation_change)
    kinds = Counter(e["kind"] for e in history.events if e["kind"] != "milestone")
    words = sum(e["words"] for e in history.of_kind("phonologized"))
    last = history.snapshots[-1]
    kept = [retention(world, group_id) for group_id in last.group_ids]
    snapshots = []
    for snapshot in history.snapshots:
        if round(snapshot.year) in SNAPSHOT_YEARS:
            snapshots.append({
                "year": round(snapshot.year),
                "dialects": len(snapshot.dialects),
                "languages": len(snapshot.languages),
                "neighbour_distance": neighbour_distance(world, snapshot),
            })
    return {
        "events": dict(sorted(kinds.items())),
        "innovations": dict(sorted(innovations.items())),
        "established": dict(sorted(established.items())),
        "extinct": dict(sorted(extinct.items())),
        "phonologized_words": words,
        "retention": sum(kept) / len(kept) if kept else None,
        "snapshots": snapshots,
    }


def main() -> None:
    result: dict = {"seeds": list(SEEDS), "scenarios": {}}
    if OUTPUT.exists():  # navázání po přerušeném běhu
        result = json.loads(OUTPUT.read_text(encoding="utf-8"))
    for name, build, years in worlds():
        runs = result["scenarios"].setdefault(name, {"years": years, "runs": {}})["runs"]
        for seed in SEEDS:
            if str(seed) in runs:
                continue
            world, events = build(seed)
            simulation = Simulation(world, SimulationConfig(keep_distances=True), events=events)
            simulation.run(years)
            runs[str(seed)] = summarize(world, simulation)
            OUTPUT.write_text(json.dumps(result, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            print(name, seed, "hotovo", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
