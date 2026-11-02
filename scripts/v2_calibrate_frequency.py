"""Kalibrace převodu frekvencí pojmů na stupnici enginu podle rychlostí výměny slov.

Pagel, Atkinson & Meade (2007) změřili rychlost výměny slov pro 200 pojmů
Swadeshova seznamu v indoevropských jazycích (Concepticon ``Pagel-2007-200``,
CC BY 4.0). Rychlost s frekvencí klesá, ale mírně: horních 30 % pojmů podle
frekvence se vyměňuje rychlostí asi 0,70 ostatních (stejně s frekvencemi
z ``cee.v2.concept_data`` i s frekvencemi Pagel a kol.).

Skript pro zadané šířky kotev převodu (``concept_data.LOG_FREQUENCY_ANCHORS``,
střed 2,0) nechá kalibrační svět retence (``v2_calibrate_retention.world``,
seedy 1–8) žít ``YEARS`` let a pro každý pojem spočte podíl vesnic, kde se
převládající slovo vyměnilo, a z něj rychlost výměny. Vypíše poměr rychlostí
horních 30 % pojmů proti ostatním; ten má odpovídat 0,70.

Použití:  python scripts/v2_calibrate_frequency.py --widths 3,4.5,6 [--workers 3] [--set entrenchment_strength=0.1]
"""

from __future__ import annotations

import argparse
import csv
import multiprocessing
import sys
from pathlib import Path

import numpy as np

YEARS = 2000.0
CENTER = 2.0
PAGEL = Path.home() / ".cee" / "data" / "concepticon-lists" / "Pagel-2007-200.tsv"


def run(job: tuple[float, int, tuple[tuple[str, float], ...]]) -> tuple[float, dict[str, tuple[int, int]]]:
    width, seed, overrides = job
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from cee.v2 import concept_data
    concept_data.LOG_FREQUENCY_ANCHORS = (CENTER - width / 2, CENTER + width / 2)
    from v2_calibrate_retention import world as build

    from cee.v2.simulation import Simulation
    w, events = build(seed, 1.0, overrides=overrides)
    groups = [g for g in w.group_ids() if not w.groups[g].written]
    lexical = sorted(v for v, variable in w.variables.items() if variable.kind == "lexical")
    original = {v: w.distribution(groups[0], v).dominant()[0] for v in lexical}
    Simulation(w, events=events).run(w.start_year + YEARS)
    return width, {v.split(":", 1)[1]: (sum(w.distribution(g, v).dominant()[0] != original[v] for g in groups),
                                        len(groups)) for v in lexical}


def ratio(log_frequency: np.ndarray, rate: np.ndarray) -> float:
    top = log_frequency >= np.quantile(log_frequency, 0.7)
    return float(rate[top].mean() / rate[~top].mean())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--widths", default="3,4.5,6")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--set", default="", help="přepisy Parameters jako v v2_calibrate_retention: JMÉNO=HODNOTA,…")
    args = parser.parse_args()
    from cee.v2 import concept_data

    rates = {}
    with PAGEL.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["CONCEPTICON_ID"] and row["MEAN_RATE"] not in ("", "-"):
                rates[int(row["CONCEPTICON_ID"])] = float(row["MEAN_RATE"])
    by_id = {item["concepticon_id"]: item["wold_id"] for item in concept_data.data()["catalog"]}
    catalog = concept_data.frequencies()["catalog"]
    pairs = [(catalog[by_id[cid]][0], rate) for cid, rate in rates.items() if cid in by_id]
    target = ratio(np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs]))
    print(f"Pagel a kol. 2007: {len(pairs)} pojmů, poměr rychlostí horních 30 % / ostatních {target:.2f}")

    widths = [float(x) for x in args.widths.split(",")]
    overrides = tuple((name, float(value)) for name, value in
                      (item.split("=") for item in args.set.split(",") if item))
    print("přepisy:", dict(overrides) or "žádné")
    jobs = [(width, seed, overrides) for width in widths for seed in range(1, 9)]
    with multiprocessing.get_context("spawn").Pool(args.workers, maxtasksperchild=1) as pool:
        results = pool.map(run, jobs)
    for width in widths:
        totals: dict[str, list[int]] = {}
        for found_width, out in results:
            if found_width == width:
                for concept, (changed, count) in out.items():
                    entry = totals.setdefault(concept, [0, 0])
                    entry[0] += changed
                    entry[1] += count
        concepts = [c for c in totals if concept_data.log_frequency(c) is not None]
        x = np.array([concept_data.log_frequency(c) for c in concepts])
        p = np.array([min(totals[c][0] / totals[c][1], 0.999) for c in concepts])
        rate = -np.log(1 - p) / YEARS * 1e4
        print(f"šířka {width}: poměr {ratio(x, rate):.2f}, podíl nahrazených {p.mean():.3f}, "
              f"pojmů bez výměny {int((rate == 0).sum())} z {len(concepts)}")


if __name__ == "__main__":
    main()
