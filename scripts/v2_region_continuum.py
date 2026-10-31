"""Nářeční kontinuum ve scénáři ``region_world`` (příprava M7).

Čtyři regiony ve čtverci (každý sousedí se dvěma), po pěti vesnicích, plný
model (fonologie, morfologie, význam, syntax). Pro odečty v čase vypíše
průměrnou vzdálenost kódů (``observe.code_distances``, stejná míra jako pro
prahy dialektu a jazyka) pro tři druhy dvojic vesnic:

- ``soused v regionu``: spojené vesnice téhož regionu;
- ``přes hranici``: pohraniční dvojice sousedních regionů;
- ``vzdálené regiony``: vesnice regionů, které spolu nesousedí.

Nářeční atlasy dávají pro sousední vesnice zhruba 0,05–0,15. Vypíše i počet
jazyků, které rozliší pozorovatel, a čas běhu.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import time
from pathlib import Path
from typing import Any

import numpy as np

from cee.v2.observe import code_distances
from cee.v2.scenarios import Region, region_world
from cee.v2.simulation import Simulation

YEARS = (500, 1000, 2000, 3000)
SQUARE = (
    Region("nw", (0.0, 40.0), neighbours=("ne", "sw"), villages=5),
    Region("ne", (40.0, 40.0), neighbours=("nw", "se"), villages=5),
    Region("sw", (0.0, 0.0), neighbours=("nw", "se"), villages=5),
    Region("se", (40.0, 0.0), neighbours=("ne", "sw"), villages=5),
)


def _measure(world: Any) -> dict[str, float]:
    distances = code_distances(world)
    ids = list(world.live.group_ids)
    position = {group_id: index for index, group_id in enumerate(ids)}
    region = {group_id: world.territories[group_id].parent for group_id in ids}
    neighbours = {r.id: set(r.neighbours) for r in SQUARE}
    pairs: dict[str, list[float]] = {"soused v regionu": [], "přes hranici": [], "vzdálené regiony": []}
    linked = {tuple(sorted((link.source, link.target))) for link in world.links.values()}
    for i, first in enumerate(ids):
        for second in ids[i + 1:]:
            value = float(distances[position[first], position[second]])
            if region[first] == region[second]:
                if (first, second) in linked:
                    pairs["soused v regionu"].append(value)
            elif (first, second) in linked:
                pairs["přes hranici"].append(value)
            elif region[second] not in neighbours[region[first]]:
                pairs["vzdálené regiony"].append(value)
    return {key: float(np.mean(values)) for key, values in pairs.items() if values}


def run(seed: int) -> dict[str, Any]:
    world = region_world(SQUARE, seed=seed, syntax=True, semantics=True)
    simulation = Simulation(world)
    frames = []
    started = time.perf_counter()
    for year in YEARS:
        simulation.run(year)
        snapshot = simulation.snapshots[-1]
        frames.append({"year": year, "languages": len(snapshot.languages), **_measure(world)})
    return {"seed": seed, "seconds": time.perf_counter() - started, "frames": frames}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with multiprocessing.get_context("spawn").Pool(args.workers) as pool:
        runs = pool.map(run, range(1, args.seeds + 1))
    if args.output:
        args.output.write_text(json.dumps(runs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    keys = ("soused v regionu", "přes hranici", "vzdálené regiony")
    print("| rok | jazyků | " + " | ".join(keys) + " |")
    print("|---:|---:|" + "---:|" * len(keys))
    for index, year in enumerate(YEARS):
        frames = [r["frames"][index] for r in runs]
        cells = [f"{np.mean([f[key] for f in frames if key in f]):.3f}" for key in keys]
        languages = np.mean([f["languages"] for f in frames])
        print(f"| {year} | {languages:.1f} | " + " | ".join(cells) + " |")
    print(f"čas běhu 3 000 let (20 vesnic): {np.mean([r['seconds'] for r in runs]):.1f} s")


if __name__ == "__main__":
    main()
