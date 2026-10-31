"""Kalibrace M7a: stacionarita gramatické typologie (WALS) a obrat uvnitř rodiny.

Prohledává prostor kalibračních parametrů gramatické dynamiky (tempo vzniku
kategorií, kontextová síla nevyjádřené funkce, síla kontaktu) a hodnotí každé
nastavení dvěma pokusy na stejných seedech (společná náhoda, srovnání
nastavení je proto spravedlivé):

- ``wals``: gramatika i přízvuk protojazyka losované z WALS. Cíl je
  stacionarita: rozložení rysů 33A, 37A, 66A a 67A po 2 000 a 5 000 letech má
  zůstat blízko WALS (průměrná Hellingerova vzdálenost).
- ``family``: všechny seedy začínají stejnou úplnou gramatikou
  (``FULL_GRAMMAR``: člen a budoucí čas chybí). Cíl je obrat uvnitř rodiny:
  po 5 000 letech se mají jazyky lišit aspoň u členu a budoucího času
  (normovaná entropie ≥ 0,5; v indoevropské rodině má člen zhruba polovina
  větví). Model, který se nemění vůbec, by byl stacionární triviálně; tento
  člen to trestá.

Kontakt: každý seed dostane stálý podíl L2 mluvčích podle ``CONTACT``
(většina jazyků má málo kontaktu, část hodně). Je to předpoklad o prostředí,
ne kalibrovaný parametr; jeho vliv je v deníku.

Ztráta = průměr H (wals; roky 2 000 a 5 000; čtyři rysy)
       + ``TURNOVER_WEIGHT`` × průměr max(0; 0,5 − E) (family; 37A a 67A).

Hledání: výchozí bod + latinská hyperkrychle (pevný seed) + místní zjemnění
kolem nejlepších; nejlepší kandidáti se ověří na odložených seedech.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import time
from collections import Counter
from pathlib import Path
from typing import Any, cast

import numpy as np

from cee.v2 import metrics
from cee.v2.observe import LineageTracker, observe
from cee.v2.parameters import Parameters
from cee.v2.scenarios import FULL_GRAMMAR, village_grid
from cee.v2.simulation import Simulation
from scripts.v2_typology import (
    load_reference,
    projected_reference,
    sample_grammar,
    sample_stress_rule,
)

YEARS = (0, 2000, 5000)
FEATURES = ("33A", "37A", "66A", "67A")
TURNOVER_FEATURES = ("37A", "67A")
TURNOVER_TARGET = 0.5
TURNOVER_WEIGHT = 0.5
#: Stálý podíl L2 mluvčích podle ``seed % 3``.
CONTACT = (0.0, 0.1, 0.3)

#: Prohledávaný prostor: název, dolní a horní mez. Výchozí hodnoty modelu
#: leží uvnitř.
SPACE: tuple[tuple[str, float, float], ...] = (
    ("emergence_need_scale", 0.0, 1.0),
    ("context.DEFINITE", 0.10, 0.50),
    ("context.FUTURE", 0.20, 0.60),
    ("context.PL", 0.10, 0.50),
    ("context.PAST", 0.10, 0.50),
    ("coverage.ASPECT", 0.40, 0.90),
)
#: Síla kontaktu a tempo opisu první kolo neurčilo; drží se na výchozích hodnotách.
DEFAULT = {"emergence_need_scale": 1.0, "context.DEFINITE": 0.22, "context.FUTURE": 0.35,
           "context.PL": 0.30, "context.PAST": 0.25, "coverage.ASPECT": 0.7}


def to_parameters(point: dict[str, float]) -> Parameters:
    grammar: dict[str, dict[str, float]] = {}
    rates: dict[str, float] = {}
    scalars: dict[str, float] = {}
    for name, value in point.items():
        if name.startswith(("context.", "coverage.")):
            field, function = name.split(".", 1)
            grammar.setdefault(function, {})[field] = value
        elif name.startswith("rate."):
            rates[name.split(".", 1)[1]] = value
        else:
            scalars[name] = value
    return Parameters(grammar=grammar, change_rates=rates, **cast(Any, scalars))


def _profiles(simulation: Simulation) -> list[dict[str, Any]]:
    if simulation.year == 0:
        config = simulation.config
        snapshot, _ = observe(simulation.world, 0, 0, LineageTracker(),
                              dialect_threshold=config.dialect_threshold,
                              language_threshold=config.language_threshold)
    else:
        snapshot = simulation.snapshots[-1]
    return [metrics.typology_profile(simulation.world, groups) for _, groups in sorted(snapshot.languages.items())]


def run_task(task: tuple[dict[str, float], str, int]) -> dict[str, Any]:
    point, experiment, seed = task
    reference = load_reference()
    if experiment == "wals":
        # Vid WALS neměří (65A není ve výřezu): začíná nevyjádřený jako v rodině.
        grammar = {"ASPECT": FULL_GRAMMAR["ASPECT"], **sample_grammar(seed, reference)}
        rule: Any = sample_stress_rule(seed, reference)
    else:
        grammar, rule = dict(FULL_GRAMMAR), "penult"
    world = village_grid(6, seed=seed, syntax=True, semantics=True, phonology=True, morphology=True,
                         grammar=grammar, stress_rule=rule, params=to_parameters(point))
    share = CONTACT[seed % len(CONTACT)]
    for group in world.groups.values():
        group.immigration = share
        group.main_code.l2_share = share
    simulation = Simulation(world)
    frames = {0: _profiles(simulation)}
    for year in YEARS[1:]:
        simulation.run(year)
        frames[year] = _profiles(simulation)
    return {"experiment": experiment, "seed": seed, "frames": frames}


def _distribution(runs: list[dict[str, Any]], year: int, feature: str) -> dict[str, float]:
    counts = Counter(profile[feature] for run in runs for profile in run["frames"][year]
                     if profile[feature] is not None)
    total = sum(counts.values())
    return {key: count / total for key, count in sorted(counts.items())} if total else {}


def score(runs: list[dict[str, Any]], reference: dict[str, Any]) -> dict[str, Any]:
    wals = [run for run in runs if run["experiment"] == "wals"]
    family = [run for run in runs if run["experiment"] == "family"]
    hellinger: dict[str, dict[int, float]] = {}
    for feature in FEATURES:
        expected = projected_reference(reference["features"][feature])
        hellinger[feature] = {year: metrics.hellinger(_distribution(wals, year, feature), expected)
                              for year in YEARS}
    entropy = {}
    for feature in TURNOVER_FEATURES:
        categories = tuple(reference["features"][feature]["engine_categories"])
        entropy[feature] = metrics.normalized_entropy(_distribution(family, YEARS[-1], feature), categories)
    stationarity = float(np.mean([hellinger[f][year] for f in FEATURES for year in YEARS[1:]]))
    turnover = float(np.mean([max(0.0, TURNOVER_TARGET - entropy[f]) for f in TURNOVER_FEATURES]))
    return {"loss": stationarity + TURNOVER_WEIGHT * turnover, "stationarity": stationarity,
            "turnover_penalty": turnover, "hellinger": hellinger, "family_entropy": entropy,
            "wals_present": {f: {year: _distribution(wals, year, f) for year in YEARS} for f in FEATURES},
            "family_final": {f: _distribution(family, YEARS[-1], f) for f in FEATURES}}


def latin_hypercube(count: int, seed: int) -> list[dict[str, float]]:
    rng = np.random.Generator(np.random.PCG64(seed))
    columns = []
    for _ in SPACE:
        strata = (rng.permutation(count) + rng.random(count)) / count
        columns.append(strata)
    return [{name: round(low + (high - low) * float(columns[d][i]), 4) for d, (name, low, high) in enumerate(SPACE)}
            for i in range(count)]


def neighbours(point: dict[str, float], count: int, seed: int, scale: float = 0.15) -> list[dict[str, float]]:
    rng = np.random.Generator(np.random.PCG64(seed))
    found = []
    for _ in range(count):
        moved = {}
        for name, low, high in SPACE:
            step = (high - low) * scale * float(rng.standard_normal())
            moved[name] = round(min(high, max(low, point[name] + step)), 4)
        found.append(moved)
    return found


def evaluate(pool: Any, points: list[dict[str, float]], seeds: list[int],
             reference: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = [(point, experiment, seed) for point in points for experiment in ("wals", "family") for seed in seeds]
    outputs = pool.map(run_task, tasks, chunksize=1)
    per_point = len(seeds) * 2
    results = []
    for index, point in enumerate(points):
        runs = outputs[index * per_point:(index + 1) * per_point]
        results.append({"point": point, "seeds": seeds, **score(runs, reference)})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--search-seeds", type=int, default=8, help="seeds 1..N for the search")
    parser.add_argument("--holdout-seeds", type=int, default=12, help="seeds 101..100+N for validation")
    parser.add_argument("--lhs", type=int, default=32, help="Latin hypercube points")
    parser.add_argument("--refine-top", type=int, default=4)
    parser.add_argument("--refine-each", type=int, default=6)
    parser.add_argument("--validate-top", type=int, default=3)
    args = parser.parse_args()
    reference = load_reference()
    search_seeds = list(range(1, args.search_seeds + 1))
    holdout_seeds = list(range(101, 101 + args.holdout_seeds))
    record: dict[str, Any] = {"space": SPACE, "default": DEFAULT, "contact": CONTACT,
                              "search_seeds": search_seeds, "holdout_seeds": holdout_seeds}

    def save() -> None:
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")

    context = multiprocessing.get_context("spawn")
    with context.Pool(args.workers) as pool:
        started = time.perf_counter()
        stage1 = [DEFAULT, *latin_hypercube(args.lhs, seed=2026)]
        record["stage1"] = evaluate(pool, stage1, search_seeds, reference)
        save()
        print(f"stage1 {len(stage1)} points {time.perf_counter() - started:.0f}s", flush=True)

        best = sorted(record["stage1"], key=lambda r: r["loss"])[:args.refine_top]
        stage2 = [p for i, r in enumerate(best) for p in neighbours(r["point"], args.refine_each, seed=3000 + i)]
        record["stage2"] = evaluate(pool, stage2, search_seeds, reference)
        save()
        print(f"stage2 {len(stage2)} points {time.perf_counter() - started:.0f}s", flush=True)

        ranked = sorted(record["stage1"] + record["stage2"], key=lambda r: r["loss"])
        candidates = [DEFAULT] + [r["point"] for r in ranked if r["point"] != DEFAULT][:args.validate_top]
        record["holdout"] = evaluate(pool, candidates, holdout_seeds, reference)
        save()
        print(f"holdout {len(candidates)} points {time.perf_counter() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
