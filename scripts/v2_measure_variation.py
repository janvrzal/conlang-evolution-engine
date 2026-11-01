"""Změří souběžnou variabilitu slovní zásoby ustáleného jazyka (``cee/data/v2_standing_variation.json``).

Protojazyk zadaný autorem má pro každý pojem jediné slovo, kdežto živý
jazyk má vždy rozpracované změny. Skript nechá síť vesnic
(``scenarios.region_world``) žít ``--years`` let jen s lexikálními změnami
a změří, jakou variabilitu v ní dynamika vytvoří, podle frekvence pojmu:

- ``density``: kolik různých přeživších menšinových variant každého druhu
  změny připadá na vesnici a pojem, u kterého ten druh jde v protojazyce
  navrhnout (varianty, které vznikly až řetězením, se připočtou tam; engine
  navrhuje jen z protojazyka),
- ``peak``: kvantily podílu varianty ve vesnici, kde je nejsilnější,
- ``decay``: průměrný podíl o 1, 2, 3 vazby dál jako násobek vrcholu.

Varianta, která slovo autora v některé vesnici vytlačila, se nepočítá:
do protojazyka ji engine nedává (``cee.v2.variation``). Engine pak tutéž
variabilitu rozdá při tvorbě světa bez simulace.

Použití:  python scripts/v2_measure_variation.py --seeds 1-8 [--years 2000]
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
from collections import Counter
from pathlib import Path

import numpy as np

from cee.v2.changes import LEXICAL_CHANGES
from cee.v2.changes.base import InnovationContext
from cee.v2.parameters import Parameters
from cee.v2.scenarios import ProtoLanguage, Region, region_world
from cee.v2.simulation import Simulation

OUT = Path(__file__).resolve().parents[1] / "src" / "cee" / "data" / "v2_standing_variation.json"
#: Hranice košů frekvence pojmu (kvartily výchozí sady pojmů).
EDGES = (0.12, 0.25, 0.56)
#: Menšinová varianta pod tímto podílem se nepočítá.
MIN_SHARE = 1e-3
QUANTILES = (0.0, 0.01, *(round(q, 2) for q in np.linspace(0.05, 0.95, 19)), 0.99, 1.0)
#: Velikosti sítě: (sloupce, řádky) krajů po třech vesnicích.
LAYOUTS = ((3, 2), (4, 3))


def bin_of(frequency: float) -> int:
    return int(np.searchsorted(EDGES, frequency, side="right"))


def network(columns: int, rows: int, seed: int):
    count = columns * rows
    regions = tuple(
        Region(f"r{i}", (60.0 * (i % columns), 60.0 * (i // columns)), language="a", villages=3,
               neighbours=tuple(f"r{j}" for j in range(count)
                                if j != i and abs(j % columns - i % columns) + abs(j // columns - i // columns) == 1))
        for i in range(count)
    )
    return region_world(regions, seed=seed, languages=(ProtoLanguage("a"),), semantics=True,
                        params=Parameters(standing_variation=0.0))


def hops(world, group_ids: list[str]) -> dict[str, dict[str, int]]:
    near: dict[str, set[str]] = {group_id: set() for group_id in group_ids}
    for (first, second), link in world.links.items():
        if first in near and second in near and link.strength > 0:
            near[first].add(second)
    found = {}
    for start in group_ids:
        depth, frontier = {start: 0}, [start]
        while frontier:
            following = []
            for group_id in frontier:
                for other in sorted(near[group_id]):
                    if other not in depth:
                        depth[other] = depth[group_id] + 1
                        following.append(other)
            frontier = following
        found[start] = depth
    return found


def measure(job: tuple[int, int, int, float]) -> dict:
    columns, rows, seed, years = job
    world = network(columns, rows, seed)
    groups = [group_id for group_id in world.group_ids() if not world.groups[group_id].written]
    lexical = sorted(v for v, variable in world.variables.items() if variable.kind == "lexical")
    original = {v: world.distribution(groups[0], v).dominant()[0] for v in lexical}
    simulation = Simulation(world, changes=LEXICAL_CHANGES)
    model = world.groups[groups[0]]
    context = InnovationContext(world, model, model.main_code, 0, world.start_year)
    available = {change.kind: set(change.weighted_sites(context)[0]) for change in LEXICAL_CHANGES}
    simulation.run(years)
    distance = hops(world, groups)
    bins = [{"concepts": 0, "variants": 0, "kinds": Counter(), "available": Counter(), "peaks": [],
             "decay": [[], [], []]} for _ in range(len(EDGES) + 1)]
    winners = 0
    for v in lexical:
        target = bins[bin_of(world.concept_frequency(v.split(":", 1)[1]))]
        target["concepts"] += 1
        target["available"].update(kind for kind, sites in available.items() if v in sites)
        shares: dict[str, dict[str, float]] = {}
        lost = set()
        for group_id in groups:
            distribution = world.distribution(group_id, v)
            dominant = distribution.dominant()[0]
            if dominant != original[v]:
                lost.add(dominant)
            for variant, share in zip(distribution.variants, distribution.freqs):
                if variant != original[v] and share >= MIN_SHARE:
                    shares.setdefault(variant, {})[group_id] = float(share)
        winners += len(lost)
        for variant, where in sorted(shares.items()):
            if variant in lost:
                continue
            target["variants"] += 1
            target["kinds"][world.variants[variant].origin.change] += 1
            peak_group = max(where, key=lambda group_id: (where[group_id], group_id))
            peak = where[peak_group]
            target["peaks"].append(peak)
            for hop in (1, 2, 3):
                ring = [group_id for group_id, depth in distance[peak_group].items() if depth == hop]
                if ring:
                    target["decay"][hop - 1].append(np.mean([where.get(g, 0.0) for g in ring]) / peak)
    return {"groups": len(groups), "winners": winners, "bins": [
        {**item, "kinds": dict(item["kinds"]), "available": dict(item["available"])} for item in bins]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default="1-8")
    parser.add_argument("--years", type=float, default=2000.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true", help="jen vypsat, nezapisovat")
    args = parser.parse_args()
    first, last = (int(x) for x in args.seeds.split("-"))
    jobs = [(columns, rows, seed, args.years) for columns, rows in LAYOUTS for seed in range(first, last + 1)]
    with multiprocessing.get_context("spawn").Pool(args.workers) as pool:
        results = pool.map(measure, jobs)
    out_bins = []
    for index in range(len(EDGES) + 1):
        items = [result["bins"][index] for result in results]
        kinds: Counter = Counter()
        places: Counter = Counter()
        for result, item in zip(results, items):
            kinds.update(item["kinds"])
            for kind, count in item["available"].items():
                places[kind] += result["groups"] * count
        peaks = [peak for item in items for peak in item["peaks"]]
        out_bins.append({
            "density": {kind: round(kinds[kind] / places[kind], 5)
                        for kind in sorted(kinds) if places[kind] > 0},
            "peak": [round(float(value), 4) for value in np.quantile(peaks, QUANTILES)],
            "decay": [round(float(np.mean([d for item in items for d in item["decay"][hop]])), 4)
                      for hop in range(3)],
        })
    data = {
        "source": "scripts/v2_measure_variation.py",
        "years": args.years, "seeds": args.seeds, "layouts": [list(layout) for layout in LAYOUTS],
        "edges": list(EDGES), "quantiles": list(QUANTILES), "min_share": MIN_SHARE,
        "per_group_size": {f"{c}x{r}": round(float(np.mean([
            sum(item["variants"] for item in result["bins"]) / result["groups"]
            for result, job in zip(results, jobs) if job[:2] == (c, r)])), 3) for c, r in LAYOUTS},
        "winners_per_group": round(float(np.mean([result["winners"] / result["groups"] for result in results])), 3),
        "bins": out_bins,
    }
    text = json.dumps(data, ensure_ascii=False, indent=1)
    print(text)
    if not args.dry_run:
        OUT.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
