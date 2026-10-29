"""Statistické porovnání losování inovací mezi verzemi enginu v2.

Spustí scénář údolí s mřížkou 10×5 vesnic na sadě seedů jak pro starý referenční
engine (baseline), tak pro nový dávkový engine, a porovná klíčové makroskopické
ukazatele (celkový počet inovací, ustálených a zaniklých variant, korelaci
vzdáleností dle metriky 9 a počty inovací dle jednotlivých typů změn).

Běhy obou enginů jsou prováděny v oddělených podprocesech sériově za sebou.

Použití:
    python scripts/v2_innovation_stats.py [--seeds 1,2,3,4,5] [--years 1000]
                                          [--baseline-src /tmp/cee-v2-baseline-825d1c3/src]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


def collect_metrics(seeds: list[int], years: float) -> dict[str, dict[str, float]]:
    """Simuluje scénář mřížky vesnic pro zadané seedy a sesbírá metriky."""
    from cee.v2.changes import DEFAULT_CHANGES
    from cee.v2.metrics import isolation_by_distance
    from cee.v2.scenarios import village_grid
    from cee.v2.simulation import Simulation

    results: dict[str, dict[str, float]] = {}
    for seed in seeds:
        world = village_grid(10, 5, seed=seed, syntax=True, semantics=True)
        simulation = Simulation(world)
        simulation.run(years)

        history = simulation.history
        innovations = history.of_kind("innovation")
        innovations_total = float(len(innovations))
        established_total = float(len(history.of_kind("established")))
        extinct_total = float(len(history.of_kind("extinct")))

        snapshot = history.snapshots[-1]
        raw_positions = [world.position_of(g) for g in snapshot.group_ids]
        positions: list[tuple[float, float]] = [pos for pos in raw_positions if pos is not None]
        fit = isolation_by_distance(snapshot.distances, positions)
        metric9_corr = float(fit.correlation)

        seed_data: dict[str, float] = {
            "innovations_total": innovations_total,
            "established_total": established_total,
            "extinct_total": extinct_total,
            "metric9_correlation": metric9_corr,
        }
        for change in DEFAULT_CHANGES:
            count = sum(1 for e in innovations if e.get("change") == change.kind)
            seed_data[f"change:{change.kind}"] = float(count)

        results[str(seed)] = seed_data

    return results


def run_collection(
    python_path: Path, seeds_str: str, years: float, output_json: Path
) -> None:
    """Spustí sběr dat v podprocesu se specifickým PYTHONPATH."""
    script_path = Path(__file__).resolve()
    env = {**os.environ, "PYTHONPATH": str(python_path.resolve())}
    cmd = [
        sys.executable,
        str(script_path),
        "--collect-json",
        str(output_json.resolve()),
        "--seeds",
        seeds_str,
        "--years",
        str(years),
    ]
    subprocess.run(cmd, env=env, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Statistická shoda inovací mezi baseline a novým enginem v2."
    )
    parser.add_argument(
        "--baseline-src",
        type=Path,
        default=Path("/tmp/cee-v2-baseline-825d1c3/src"),
        help="Cesta ke složce src výchozího enginu.",
    )
    parser.add_argument(
        "--seeds",
        type=str,
        default="1,2,3,4,5",
        help="Čárkou oddělený seznam seedů (např. '1,2,3,4,5').",
    )
    parser.add_argument(
        "--years",
        type=float,
        default=1000.0,
        help="Počet let simulace pro každý seed (výchozí 1000).",
    )
    parser.add_argument(
        "--collect-json",
        type=Path,
        default=None,
        help="Interní režim: cesta pro uložení nasbíraných dat ve formátu JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]

    if args.collect_json is not None:
        metrics = collect_metrics(seeds, args.years)
        args.collect_json.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        return

    baseline_src: Path = args.baseline_src
    if not baseline_src.is_dir():
        sys.exit(f"Chyba: Adresář baseline neexistuje: {baseline_src}")

    repo_root = Path(__file__).resolve().parent.parent
    current_src = repo_root / "src"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        baseline_json = tmp_path / "baseline.json"
        current_json = tmp_path / "current.json"

        print(f"Sběr dat pro baseline engine ({baseline_src})...", flush=True)
        run_collection(baseline_src, args.seeds, args.years, baseline_json)

        print(f"Sběr dat pro aktuální engine ({current_src})...", flush=True)
        run_collection(current_src, args.seeds, args.years, current_json)

        data_old: dict[str, dict[str, float]] = json.loads(
            baseline_json.read_text(encoding="utf-8")
        )
        data_new: dict[str, dict[str, float]] = json.loads(
            current_json.read_text(encoding="utf-8")
        )

    # Identifikace všech metrik podle prvního záznamu
    first_seed = str(seeds[0])
    metric_names = list(data_old[first_seed].keys())

    all_passed = True
    table_rows: list[dict[str, Any]] = []

    for name in metric_names:
        vals_old = [data_old[str(s)][name] for s in seeds]
        vals_new = [data_new[str(s)][name] for s in seeds]

        mean_old = float(np.mean(vals_old))
        mean_new = float(np.mean(vals_new))

        sd_old = float(np.std(vals_old, ddof=1)) if len(seeds) >= 2 else 0.0
        sd_new = float(np.std(vals_new, ddof=1)) if len(seeds) >= 2 else 0.0

        sd = math.sqrt((sd_old**2 + sd_new**2) / 2.0)
        diff = mean_new - mean_old

        if abs(diff) == 0.0:
            ratio = 0.0
        elif sd > 0.0:
            ratio = abs(diff) / sd
        else:
            ratio = float("inf")

        passed = (abs(diff) == 0.0) or (sd > 0.0 and abs(diff) < 2.0 * sd)
        if not passed:
            all_passed = False

        table_rows.append(
            {
                "name": name,
                "mean_old": mean_old,
                "sd_old": sd_old,
                "mean_new": mean_new,
                "sd_new": sd_new,
                "diff": diff,
                "ratio": ratio,
                "passed": passed,
            }
        )

    # Výpis Markdown tabulky
    print("\n### Statistické porovnání enginů v2\n")
    print(f"- Seedy: `{args.seeds}`")
    print(f"- Roků simulace: `{args.years}`")
    print(f"- Baseline: `{baseline_src}`\n")

    print("| Veličina | Starý engine (průměr ± SD) | Nový engine (průměr ± SD) | Rozdíl | |Diff| / SD | Shoda |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: |")

    for row in table_rows:
        is_corr = "correlation" in row["name"]
        fmt = ".4f" if is_corr else ".1f"
        old_str = f"{row['mean_old']:{fmt}} ± {row['sd_old']:{fmt}}"
        new_str = f"{row['mean_new']:{fmt}} ± {row['sd_new']:{fmt}}"
        diff_str = f"{row['diff']:+{fmt}}"
        ratio_str = f"{row['ratio']:.2f}" if not math.isinf(row["ratio"]) else "inf"
        status_str = "**PASS**" if row["passed"] else "**FAIL**"

        print(
            f"| `{row['name']}` | {old_str} | {new_str} | {diff_str} | {ratio_str} | {status_str} |"
        )

    print()
    if all_passed:
        print("**Celkový výsledek: PASS** (všechny veličiny jsou v limitu 2.0 SD nebo identické)")
        sys.exit(0)
    else:
        print("**Celkový výsledek: FAIL** (některé veličiny překročily mez 2.0 SD)")
        sys.exit(1)


if __name__ == "__main__":
    main()
