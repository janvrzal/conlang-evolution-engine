"""Kalibrace nářečního kontinua ve scénáři ``region_world`` (M7).

Ladí jen mísení: otevřenost vesnic (``village_openness``: kolik vstupu jde
od sousedů) a propustnost hranice regionů (``border_link_scale``). Tempo
změn se nemění; to určují jiné cíle.

Svět: čtyři regiony ve čtverci (``v2_region_continuum.SQUARE``), plný model.
Čísla z nářečních atlasů nejsou s naší mírou vzdálenosti přímo srovnatelná
(dialektometrie měří jinak), proto se pásmo atlasů kombinuje s cíli, které
na míře nezávisí:

- ``pásmo``: sousední vesnice regionu v letech 2 000 a 3 000 v pásmu
  0,05–0,15 (atlasy);
- ``rovnováha``: v dlouho osídlené krajině se vzdálenost sousedů ustálí,
  inovace a mísení se vyrovnají; trest, když vzdálenost mezi 2 000 a 3 000
  lety vzroste o víc než 10 %;
- ``pořadí``: sousedé < přes hranici < vzdálené regiony v roce 3 000;
- ``jazyky``: 80 km bez bariér zůstane jedním jazykem (pozorovatel) v roce
  3 000.

Ztráta = pásmo + rovnováha + pořadí + 0,5 × (jazyků − 1) / 3.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import time
from pathlib import Path
from typing import Any

import numpy as np

from cee.v2.parameters import Parameters
from cee.v2.scenarios import region_world
from cee.v2.simulation import Simulation
from scripts.v2_region_continuum import SQUARE, _measure

YEARS = (1000, 2000, 3000)
BAND = (0.05, 0.15)
OPENNESS = (0.05, 0.1, 0.2, 0.35, 0.5, 0.7)
BORDER = (0.25, 0.5, 1.0, 2.0, 4.0)
KEYS = ("soused v regionu", "přes hranici", "vzdálené regiony")


def run_task(task: tuple[float, float, int]) -> dict[str, Any]:
    openness, border, seed = task
    params = Parameters(village_openness=openness, border_link_scale=border)
    world = region_world(SQUARE, seed=seed, syntax=True, semantics=True, params=params)
    simulation = Simulation(world)
    frames = []
    for year in YEARS:
        simulation.run(year)
        frames.append({"year": year, "languages": len(simulation.snapshots[-1].languages), **_measure(world)})
    return {"openness": openness, "border": border, "seed": seed, "frames": frames}


def score(runs: list[dict[str, Any]]) -> dict[str, Any]:
    mean = {year: {key: float(np.mean([r["frames"][i][key] for r in runs])) for key in (*KEYS, "languages")}
            for i, year in enumerate(YEARS)}
    low, high = BAND
    band = sum(max(0.0, mean[y]["soused v regionu"] - high) + max(0.0, low - mean[y]["soused v regionu"])
               for y in (2000, 3000))
    equilibrium = max(0.0, mean[3000]["soused v regionu"] / max(mean[2000]["soused v regionu"], 1e-9) - 1.1)
    final = mean[3000]
    order = (max(0.0, final["soused v regionu"] - final["přes hranici"])
             + max(0.0, final["přes hranici"] - final["vzdálené regiony"]))
    languages = (final["languages"] - 1.0) / 3.0
    return {"loss": band + equilibrium + order + 0.5 * languages, "band": band, "equilibrium": equilibrium,
            "order": order, "languages_penalty": languages, "mean": mean}


def evaluate(pool: Any, points: list[tuple[float, float]], seeds: list[int]) -> list[dict[str, Any]]:
    tasks = [(o, b, s) for o, b in points for s in seeds]
    outputs = pool.map(run_task, tasks, chunksize=1)
    results = []
    for index, (openness, border) in enumerate(points):
        runs = outputs[index * len(seeds):(index + 1) * len(seeds)]
        results.append({"openness": openness, "border": border, "seeds": seeds, **score(runs)})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seeds", type=int, default=4)
    parser.add_argument("--holdout-seeds", type=int, default=8)
    parser.add_argument("--validate-top", type=int, default=3)
    args = parser.parse_args()
    started = time.perf_counter()
    record: dict[str, Any] = {"openness": OPENNESS, "border": BORDER, "band": BAND}
    with multiprocessing.get_context("spawn").Pool(args.workers) as pool:
        grid = [(o, b) for o in OPENNESS for b in BORDER]
        record["grid"] = evaluate(pool, grid, list(range(1, args.seeds + 1)))
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"grid {len(grid)} points {time.perf_counter() - started:.0f}s", flush=True)
        best = sorted(record["grid"], key=lambda r: r["loss"])[:args.validate_top]
        candidates = [(0.1, 1.0)] + [(r["openness"], r["border"]) for r in best if (r["openness"], r["border"]) != (0.1, 1.0)]
        record["holdout"] = evaluate(pool, candidates, list(range(101, 101 + args.holdout_seeds)))
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"holdout {len(candidates)} points {time.perf_counter() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
