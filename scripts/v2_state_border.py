"""Státní hranice v jednojazyčném světě (M6f): čtverec regionů ve dvou státech.

Sever (``nw``, ``ne``) a jih (``sw``, ``se``) jsou dva státy se sídly ``nw``
a ``sw``. Po 2 000 letech se měří průměrná vzdálenost kódů spojených vesnic
přes hranici regionů uvnitř státu a přes hranici států, pro propustnost
``open``, ``normal`` a ``closed`` a bez států pro srovnání.

Použití:  python scripts/v2_state_border.py
"""

from __future__ import annotations

import multiprocessing
from typing import Any

import numpy as np

from cee.v2.observe import code_distances
from cee.v2.polity import State, region_of
from cee.v2.scenarios import region_world
from cee.v2.simulation import Simulation
from scripts.v2_region_continuum import SQUARE

NORTH, SOUTH = ("nw", "ne"), ("sw", "se")
BORDERS = (None, "open", "normal", "closed")
SEEDS = (1, 2)
YEARS = 2000.0
KEYS = ("uvnitř státu", "přes hranici států")


def _measure(world: Any) -> dict[str, float]:
    distances = code_distances(world)
    ids = list(world.live.group_ids)
    region = {group_id: region_of(world, group_id) for group_id in ids}
    linked = {tuple(sorted((link.source, link.target))) for link in world.links.values()}
    pairs: dict[str, list[float]] = {key: [] for key in KEYS}
    for i, first in enumerate(ids):
        for j in range(i + 1, len(ids)):
            second = ids[j]
            if region[first] == region[second] or (first, second) not in linked:
                continue
            same = (region[first] in NORTH) == (region[second] in NORTH)
            pairs[KEYS[0] if same else KEYS[1]].append(float(distances[i, j]))
    return {key: float(np.mean(values)) for key, values in pairs.items() if values}


def run(task: tuple[str | None, int]) -> tuple[tuple[str | None, int], dict[str, float]]:
    border, seed = task
    world = region_world(SQUARE, seed=seed, syntax=True, semantics=True)
    events = [] if border is None else [
        State(0.0, "north", NORTH, "nw", border=border), State(0.0, "south", SOUTH, "sw", border=border),
    ]
    Simulation(world, events=events).run(YEARS)
    return task, _measure(world)


def main() -> None:
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        results = dict(pool.map(run, [(border, seed) for border in BORDERS for seed in SEEDS]))
    print("| hranice | " + " | ".join(KEYS) + " |")
    print("|---|" + "---:|" * len(KEYS))
    for border in BORDERS:
        cells = [f"{np.mean([results[(border, seed)][key] for seed in SEEDS]):.3f}" for key in KEYS]
        print(f"| {border or 'bez států'} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
