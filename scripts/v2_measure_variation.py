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
- ``decay``: průměrný podíl o 1, 2, 3 vazby dál jako násobek vrcholu
  (jen pro přehled; engine šíří podle grafu),
- ``graph_scale``: převod poměru grafu vazeb ``G[j, i] / G[i, i]``
  (``cee.v2.variation.source_graph``) na podíl v okolní vesnici jako násobek
  vrcholu, změřený na sítích modelu vesnice (součet skutečných poměrů ku
  součtu poměrů grafu ve vesnicích do tří vazeb od vrcholu).

Množství variability ve vesnici (počet menšinových variant a jejich masa)
závisí silně na otevřenosti, populaci a počtu sousedů. Skript ho proto
změří zvlášť na řadě sítí (řady a mřížky vesnic, kraje) s různou
otevřeností a populací a uloží model vesnice (``village_model``: tabulka
otevřenost × populace a počet sousedů, členy ``cee.v2.variation.model_terms``),
podle kterého engine variabilitu každé vesnici dávkuje.

Varianta, která slovo autora v některé vesnici vytlačila, se nepočítá:
do protojazyka ji engine nedává (``cee.v2.variation``). Engine pak tutéž
variabilitu rozdá při tvorbě světa bez simulace.

Použití:  python scripts/v2_measure_variation.py --seeds 1-8 [--years 2000] [--model-seeds 1-2]
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
from collections import Counter
from pathlib import Path

import numpy as np

from cee.v2 import concept_data, variation
from cee.v2.changes import LEXICAL_CHANGES
from cee.v2.changes.base import InnovationContext
from cee.v2.parameters import Parameters
from cee.v2.scenarios import DEFAULT_CONCEPTS, ProtoLanguage, Region, region_world, village_grid
from cee.v2.simulation import Simulation
from cee.v2.variation import REACH, model_terms, source_graph, village_features

OUT = Path(__file__).resolve().parents[1] / "src" / "cee" / "data" / "v2_standing_variation.json"
#: Hranice košů frekvence pojmu: kvartily frekvencí výchozí sady pojmů z dat
#: (``cee.v2.concept_data.frequency``).
EDGES = tuple(round(float(np.quantile([concept_data.frequency(concept) for concept in DEFAULT_CONCEPTS], q)), 3)
              for q in (0.25, 0.5, 0.75))
#: Menšinová varianta pod tímto podílem se nepočítá.
MIN_SHARE = 1e-3
QUANTILES = (0.0, 0.01, *(round(q, 2) for q in np.linspace(0.05, 0.95, 19)), 0.99, 1.0)
#: Velikosti sítě: (sloupce, řádky) krajů po třech vesnicích.
LAYOUTS = ((3, 2), (4, 3))
#: Sítě, otevřenosti a populace pro model množství variability vesnice.
MODEL_TOPOLOGIES = ("line6", "line12", "grid3", "grid4", "region", "region-mixed")
MODEL_OPENNESS = (0.05, 0.1, 0.25, 0.5, 0.8)
MODEL_POPULATIONS = (125, 250, 500, 1000, 2000, 4000, 8000)


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


def model_world(topology: str, openness: float, population: float, seed: int, variation: float = 0.0):
    """Síť pro model vesnice: řada či mřížka vesnic, nebo kraje (``region-mixed`` s různou hustotou)."""
    params = Parameters(standing_variation=variation)
    if topology.startswith("line"):
        return village_grid(int(topology[4:]), seed=seed, semantics=True, openness=openness,
                            population=int(population), params=params)
    if topology.startswith("grid"):
        size = int(topology[4:])
        return village_grid(size, size, seed=seed, semantics=True, openness=openness,
                            population=int(population), params=params)
    columns, rows = 3, 2
    count = columns * rows
    spread = (0.25, 1.0, 4.0) if topology == "region-mixed" else (1.0,)
    regions = tuple(
        Region(f"r{i}", (60.0 * (i % columns), 60.0 * (i // columns)), language="a", villages=3,
               density=population / params.population_per_density * spread[i % len(spread)], openness=openness,
               neighbours=tuple(f"r{j}" for j in range(count)
                                if j != i and abs(j % columns - i % columns) + abs(j // columns - i // columns) == 1))
        for i in range(count)
    )
    return region_world(regions, seed=seed, languages=(ProtoLanguage("a"),), semantics=True, params=params)


def measure_villages(job: tuple[str, float, float, int, float]) -> dict:
    """Ustálený stav vesnic jedné sítě (jako v ``measure``) a šíření variant proti grafu.

    ``rows``: počet a masa menšinových variant v každé vesnici a její
    vlastnosti. ``spread``: pro každý koš frekvence součet skutečných poměrů
    podílu k vrcholu ve vesnicích do ``REACH`` vazeb od vrcholu a součet
    poměrů grafu ``G[j, vrchol] / G[vrchol, vrchol]`` týchž vesnic.
    """
    topology, openness, population, seed, years = job
    world = model_world(topology, openness, population, seed)
    groups = [group_id for group_id in world.group_ids() if not world.groups[group_id].written]
    graph = source_graph(world, groups)
    position = {group_id: index for index, group_id in enumerate(groups)}
    features = village_features(world, groups, graph)
    lexical = sorted(v for v, variable in world.variables.items() if variable.kind == "lexical")
    original = {v: world.distribution(groups[0], v).dominant()[0] for v in lexical}
    Simulation(world, changes=LEXICAL_CHANGES).run(world.start_year + years)
    distance = hops(world, groups)
    found = {group_id: [0, 0.0] for group_id in groups}
    spread = [[0.0, 0.0] for _ in range(len(EDGES) + 1)]
    for v in lexical:
        distributions = {group_id: world.distribution(group_id, v) for group_id in groups}
        lost = {distribution.dominant()[0] for distribution in distributions.values()} - {original[v]}
        shares: dict[str, dict[str, float]] = {}
        for group_id, distribution in distributions.items():
            for variant, share in zip(distribution.variants, distribution.freqs):
                if variant != original[v] and variant not in lost and share >= MIN_SHARE:
                    found[group_id][0] += 1
                    found[group_id][1] += float(share)
                    shares.setdefault(variant, {})[group_id] = float(share)
        totals = spread[bin_of(world.concept_frequency(v.split(":", 1)[1]))]
        for variant, where in sorted(shares.items()):
            peak_group = max(where, key=lambda group_id: (where[group_id], group_id))
            peak, origin = where[peak_group], position[peak_group]
            for other, depth in distance[peak_group].items():
                if 1 <= depth <= REACH:
                    totals[0] += where.get(other, 0.0) / peak
                    totals[1] += float(graph[position[other], origin] / graph[origin, origin])
    return {"rows": [{"topology": topology, "seed": seed, "features": list(features[group_id]),
                      "count": found[group_id][0], "mass": found[group_id][1]} for group_id in groups],
            "spread": spread}


def fit_model(rows: list[dict]) -> dict:
    """Koeficienty log(1 + počet) a log(1 + masa) v členech ``model_terms`` a rozpětí vlastností."""
    knots = {"openness": list(MODEL_OPENNESS), "population": list(MODEL_POPULATIONS)}
    terms = np.array([model_terms(tuple(row["features"]), knots) for row in rows])
    model: dict = {"terms": "tabulka otevřenost × populace (bilineárně v logaritmech) a ln max(zdroje, 1)",
                   "knots": knots,
                   "ranges": {name: [float(min(row["features"][index] for row in rows)),
                                     float(max(row["features"][index] for row in rows))]
                              for index, name in enumerate(("openness", "population", "sources"))},
                   "villages": len(rows)}
    for name in ("count", "mass"):
        values = np.log1p(np.array([row[name] for row in rows]))
        coefficients, *_ = np.linalg.lstsq(terms, values, rcond=None)
        residual = values - terms @ coefficients
        model[name] = [round(float(value), 6) for value in coefficients]
        model[f"{name}_residual_sd"] = round(float(np.std(residual)), 4)
        model[f"{name}_bias"] = {topology: round(float(np.mean([r for r, row in zip(residual, rows)
                                                               if row["topology"] == topology])), 3)
                                 for topology in MODEL_TOPOLOGIES}
    return model


def measure_delivery(job: tuple[str, float, float, int, dict]) -> tuple[float, float, float, float]:
    """Rozdá variabilitu podle ``data`` (bez simulace) a vrátí rozdaný a cílový počet a masu sítě.

    Rozdání nedodá přesně očekávané množství: část navržených variant nejde
    vytvořit (duplicita, pojem bez místa) a strop menšin u pojmu ořízne masu.
    Poměr rozdaného a cílového stavu se uloží jako ``delivery`` a engine o něj
    cíl zvýší.
    """
    topology, openness, population, seed, data = job
    variation.measured = lambda: data  # type: ignore[method-assign]
    world = model_world(topology, openness, population, seed, variation=1.0)
    groups = [group_id for group_id in world.group_ids() if not world.groups[group_id].written]
    lexical = sorted(v for v, variable in world.variables.items() if variable.kind == "lexical")
    original = {v: world.distribution(groups[0], v).dominant()[0] for v in lexical}
    features = village_features(world, groups)
    Simulation(world, changes=LEXICAL_CHANGES)
    count = mass = wanted_count = wanted_mass = 0.0
    for group_id in groups:
        wanted = variation.target(data["village_model"], features[group_id])
        wanted_count, wanted_mass = wanted_count + wanted[0], wanted_mass + wanted[1]
        for v in lexical:
            distribution = world.distribution(group_id, v)
            for variant, share in zip(distribution.variants, distribution.freqs):
                if variant != original[v] and share >= MIN_SHARE:
                    count, mass = count + 1, mass + float(share)
    return count, wanted_count, mass, wanted_mass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default="1-8")
    parser.add_argument("--years", type=float, default=2000.0)
    parser.add_argument("--model-seeds", default="1-2", help="seedy sítí pro model vesnice")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true", help="jen vypsat, nezapisovat")
    args = parser.parse_args()
    first, last = (int(x) for x in args.seeds.split("-"))
    jobs = [(columns, rows, seed, args.years) for columns, rows in LAYOUTS for seed in range(first, last + 1)]
    first_model, last_model = (int(x) for x in args.model_seeds.split("-"))
    model_jobs = [(topology, openness, population, seed, args.years) for topology in MODEL_TOPOLOGIES
                  for openness in MODEL_OPENNESS for population in MODEL_POPULATIONS
                  for seed in range(first_model, last_model + 1)]
    with multiprocessing.get_context("spawn").Pool(args.workers) as pool:
        results = pool.map(measure, jobs)
        villages = pool.map(measure_villages, model_jobs)
    village_rows = [row for result in villages for row in result["rows"]]
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
            # Podíl v okolní vesnici = vrchol × graph_scale × G[j, i] / G[i, i] (cee.v2.variation).
            "graph_scale": round(sum(result["spread"][index][0] for result in villages)
                                 / sum(result["spread"][index][1] for result in villages), 5),
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
        "village_model": fit_model(village_rows),
    }
    data["village_model"]["delivery"] = {"count": 1.0, "mass": 1.0}
    delivery_jobs = [(topology, openness, population, first_model, data) for topology in MODEL_TOPOLOGIES
                     for openness in MODEL_OPENNESS for population in MODEL_POPULATIONS]
    with multiprocessing.get_context("spawn").Pool(args.workers) as pool:
        delivered = pool.map(measure_delivery, delivery_jobs)
    data["village_model"]["delivery"] = {
        "count": round(float(np.median([count / wanted for count, wanted, _, _ in delivered if wanted > 0])), 4),
        "mass": round(float(np.median([mass / wanted for _, _, mass, wanted in delivered if wanted > 0])), 4),
    }
    text = json.dumps(data, ensure_ascii=False, indent=1)
    print(text)
    if not args.dry_run:
        OUT.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
