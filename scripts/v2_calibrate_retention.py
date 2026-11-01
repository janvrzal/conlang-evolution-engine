"""Kalibrace M7: retence základní slovní zásoby na ``region_world``.

Měří, kolik pojmů vyjadřuje vesnice po 1 000, 2 000 a 3 000 letech pořád
zděděným slovem, zvlášť pro Swadeshův seznam (100 pojmů) a pro rozšíření
o kulturní slovní zásobu. Cíl glottochronologie: Swadeshův seznam asi 86 %
za tisíciletí (Lees 1953; rozptyl mezi jazyky asi 75–95 %). Tempo slovních
změn se ladí jedním násobkem ``Parameters.change_rates`` pro všechny
lexikální rodiny, aby se neměnil jejich poměr.

Druhý parametr je převod hustoty osídlení na velikost vesnice
(``Parameters.population_per_density``): menší vesnice znamenají silnější
drift, a tedy rychlejší šíření nových slov bez výhody.

Použití:  python scripts/v2_calibrate_retention.py --scales 1 --populations 500 200 --seeds 1-8
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import statistics

from cee.data.core_vocabulary import SWADESH_CORE
from cee.v2.changes import LEXICAL_CHANGES
from cee.v2.parameters import Parameters
from cee.v2.scenarios import ProtoLanguage, Region, region_world
from cee.v2.simulation import Simulation

YEARS = (1000, 2000, 3000)


def world(seed: int, scale: float, population: float = 500.0):
    regions = tuple(
        Region(f"r{i}", (60.0 * (i % 3), 60.0 * (i // 3)), language="a", villages=3,
               neighbours=tuple(f"r{j}" for j in range(6)
                                if j != i and abs(j % 3 - i % 3) + abs(j // 3 - i // 3) == 1))
        for i in range(6)
    )
    rates = {change.kind: scale for change in LEXICAL_CHANGES}
    return region_world(regions, seed=seed, languages=(ProtoLanguage("a"),), semantics=True,
                        params=Parameters(change_rates=rates, population_per_density=population))


def kept(world_, group_id: str) -> tuple[list[bool], list[bool]]:
    core, extension = [], []
    for variable_id, variable in world_.variables.items():
        if variable.kind != "lexical":
            continue
        distribution = world_.distribution(group_id, variable_id)
        if distribution is None:
            continue
        inherited = world_.variants[distribution.dominant()[0]].origin.change is None
        concept = variable.key.split(":", 1)[-1]
        (core if concept in SWADESH_CORE else extension).append(inherited)
    return core, extension


def run(job: tuple[int, float, float]) -> dict:
    seed, scale, population = job
    w = world(seed, scale, population)
    simulation = Simulation(w)
    out = {"seed": seed, "scale": scale, "population": population}
    for year in YEARS:
        simulation.run(float(year))
        core, extension = [], []
        for group_id in w.group_ids():
            if w.groups[group_id].written or w.groups[group_id].domain != "home":
                continue
            c, e = kept(w, group_id)
            core += c
            extension += e
        out[year] = (sum(core) / len(core), sum(extension) / len(extension))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scales", type=float, nargs="+", default=[1.0])
    parser.add_argument("--populations", type=float, nargs="+", default=[500.0])
    parser.add_argument("--seeds", default="1-8")
    # Jeden běh potřebuje asi 1,5 GB paměti; víc procesů na 16 GB stroji vede do swapu.
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    first, last = (int(x) for x in args.seeds.split("-"))
    jobs = [(seed, scale, population) for scale in args.scales for population in args.populations
            for seed in range(first, last + 1)]
    with multiprocessing.get_context("spawn").Pool(args.workers) as pool:
        results = pool.map(run, jobs)
    for scale, population in sorted({(r["scale"], r["population"]) for r in results}):
        rows = [r for r in results if r["scale"] == scale and r["population"] == population]
        line = [f"škála {scale:<4} populace {population:<5.0f}"]
        for year in YEARS:
            core = statistics.mean(r[year][0] for r in rows)
            ext = statistics.mean(r[year][1] for r in rows)
            line.append(f"{year}: jádro {core:.3f} ({core ** (1000 / year):.3f}/tis.) rozšíření {ext:.3f}")
        print(" | ".join(line), flush=True)
    print(json.dumps(results))


if __name__ == "__main__":
    main()
