"""Diagnostika eroze koncovek (krok D0, specifikace zadani-prozodie.md).

Běh:
    PYTHONPATH=src:. python scripts/v2_ending_erosion.py --output results/v2_ending_erosion.json \
        --markdown results/v2_ending_erosion.md
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np

import cee.v2.pressures.linguistic as ling_mod
from cee.v2.assessment import assess
from cee.v2.language.processes import StressRule
from cee.v2.rng import hash_normal, stable_int
from cee.v2.scenarios import FULL_GRAMMAR, village_grid
from cee.v2.simulation import Simulation
from cee.v2.syntax import weakness

CELLS = ("PAST", "FUTURE", "PL", "OBJ", "DEFINITE")
REDUCTIVE_FAMILIES = ("apocope", "coda_loss", "syncope", "vowel_reduction")
YEARS = (0, 1000, 2000, 3000)

CONFIGURATIONS: dict[str, dict[str, Any]] = {
    "penult_fl5": {"rule": "penult", "fl_scale": 5.0, "label": "penult / FL 5.0 (výchozí)"},
    "initial_fl5": {"rule": "initial", "fl_scale": 5.0, "label": "initial / FL 5.0"},
    "final_fl5": {"rule": "final", "fl_scale": 5.0, "label": "final / FL 5.0"},
    "penult_fl2.5": {"rule": "penult", "fl_scale": 2.5, "label": "penult / FL 2.5"},
    "penult_fl0": {"rule": "penult", "fl_scale": 0.0, "label": "penult / FL 0.0"},
    "initial_fl2.5": {"rule": "initial", "fl_scale": 2.5, "label": "initial / FL 2.5"},
}


@dataclass
class InnovationRecord:
    seed: int
    config: str
    var_id: str
    variant_id: str
    group_id: str
    tick: int
    year: float
    family: str
    hits_ending: int
    hits_root: int
    ending_cells: list[str]
    art: float
    cla: float
    fl: float
    pho: float
    dis: float
    act: float
    conf: float
    soc: float
    fit: float
    short_share: float
    merge_mass: float
    markedness_delta: float
    is_phonologized: bool = False
    is_established: bool = False
    is_extinct: bool = False


def run_single(
    seed: int,
    config_key: str,
    rule: StressRule,
    fl_scale: float,
    columns: int = 6,
    max_year: int = 3000,
) -> tuple[list[InnovationRecord], dict[int, dict[str, list[float]]]]:
    ling_mod.FUNCTIONAL_LOAD_SCALE = fl_scale
    try:
        world = village_grid(
            columns,
            seed=seed,
            syntax=True,
            semantics=True,
            phonology=True,
            morphology=True,
            grammar=dict(FULL_GRAMMAR),
        )
        for grp in world.groups.values():
            grp.main_code.stress_rule = rule

        sim = Simulation(world)
        innovations: list[InnovationRecord] = []
        weakness_by_year: dict[int, dict[str, list[float]]] = {}

        # Year 0 weakness
        weakness_by_year[0] = {
            fn: [weakness(world, g.main_code, fn) for g in world.groups.values()]
            for fn in CELLS
        }

        last_idx = 0
        current_year = 0
        while current_year < max_year:
            sim.step()
            current_year = int(round(sim.year))
            evs = sim.history.events[last_idx:]
            last_idx = len(sim.history.events)

            for ev in evs:
                if ev["kind"] == "innovation" and ev.get("variable") in world.processes:
                    var_id = ev["variable"]
                    grp_id = ev["group"]
                    code = world.groups[grp_id].main_code
                    proc = world.processes[var_id]

                    hits_ending = 0
                    hits_root = 0
                    ending_cells: set[str] = set()

                    for u_id in code.phonology.vocabulary:
                        u = world.unit_of(code, u_id)
                        m = world.morphemes[u_id]
                        sites = proc.sites(u.form, world.table, code.stress_rule)
                        if sites:
                            if m.cell in CELLS and u.boundary is not None:
                                for s in sites:
                                    if s >= u.boundary:
                                        hits_ending += 1
                                        ending_cells.add(m.cell)
                                    else:
                                        hits_root += 1
                            else:
                                hits_root += len(sites)

                    asm = assess(world, grp_id, var_id, sim.tick)
                    art = proc.ease
                    cla = 0.6 * float(np.clip(proc.clarity - 1.5 * asm.short_share, -1.0, 1.0))
                    fl = -float(min(1.0, fl_scale * asm.merge_mass))
                    dis = 0.5 * float(np.clip(4.0 * asm.dispersion_delta, -1.0, 1.0))
                    pho = -0.4 * float(np.clip(asm.markedness_delta, -1.0, 1.0))

                    epoch = sim.tick // 8
                    gk = np.array([stable_int(seed, "actuation", epoch, grp_id)], dtype=np.uint64)
                    vk = np.array([stable_int("actuation", ev["variant"])], dtype=np.uint64)
                    act = float(np.clip(0.25 * hash_normal(gk, vk), -1.0, 1.0)[0, 0])
                    p0 = 0.02
                    conf = 0.1 * (2.0 * p0 - 1.0)
                    soc = act + conf
                    fit = art + cla + fl + dis + pho + soc

                    rec = InnovationRecord(
                        seed=seed,
                        config=config_key,
                        var_id=var_id,
                        variant_id=ev["variant"],
                        group_id=grp_id,
                        tick=ev["tick"],
                        year=ev["year"],
                        family=ev["change"],
                        hits_ending=hits_ending,
                        hits_root=hits_root,
                        ending_cells=sorted(ending_cells),
                        art=art,
                        cla=cla,
                        fl=fl,
                        pho=pho,
                        dis=dis,
                        act=act,
                        conf=conf,
                        soc=soc,
                        fit=fit,
                        short_share=asm.short_share,
                        merge_mass=asm.merge_mass,
                        markedness_delta=asm.markedness_delta,
                    )
                    innovations.append(rec)

            if current_year in (1000, 2000, 3000):
                weakness_by_year[current_year] = {
                    fn: [weakness(world, g.main_code, fn) for g in world.groups.values()]
                    for fn in CELLS
                }

        # Resolve outcomes at year 3000
        phonologized_vars = {
            (e["variable"], e["group"])
            for e in sim.history.events
            if e["kind"] == "phonologized"
        }
        established_variants = {
            (e["variant"], e["group"])
            for e in sim.history.events
            if e["kind"] == "established"
        }
        extinct_variants = {
            e["variant"]
            for e in sim.history.events
            if e["kind"] == "extinct"
        }

        for rec in innovations:
            rec.is_phonologized = (rec.var_id, rec.group_id) in phonologized_vars
            rec.is_established = (rec.variant_id, rec.group_id) in established_variants
            rec.is_extinct = rec.variant_id in extinct_variants

        return innovations, weakness_by_year
    finally:
        ling_mod.FUNCTIONAL_LOAD_SCALE = 5.0


def summarize_target(records: list[InnovationRecord]) -> dict[str, Any]:
    if not records:
        return {
            "n": 0,
            "est_count": 0,
            "est_rate": 0.0,
            "ph_count": 0,
            "ph_rate": 0.0,
            "ph_only_count": 0,
            "ph_only_rate": 0.0,
            "ext_no_ph_count": 0,
            "ext_no_ph_rate": 0.0,
            "ext_total_count": 0,
            "ext_total_rate": 0.0,
            "art": 0.0,
            "cla": 0.0,
            "fl": 0.0,
            "pho": 0.0,
            "dis": 0.0,
            "soc": 0.0,
            "fit": 0.0,
            "merge_mass": 0.0,
            "short_share": 0.0,
            "markedness_delta": 0.0,
        }
    n = len(records)
    est_c = sum(1 for r in records if r.is_established)
    ph_c = sum(1 for r in records if r.is_phonologized)
    ph_only_c = sum(1 for r in records if r.is_phonologized and not r.is_established)
    ext_total_c = sum(1 for r in records if r.is_extinct)
    ext_no_ph_c = sum(1 for r in records if r.is_extinct and not r.is_phonologized)
    return {
        "n": n,
        "est_count": est_c,
        "est_rate": est_c / n,
        "ph_count": ph_c,
        "ph_rate": ph_c / n,
        "ph_only_count": ph_only_c,
        "ph_only_rate": ph_only_c / n,
        "ext_no_ph_count": ext_no_ph_c,
        "ext_no_ph_rate": ext_no_ph_c / n,
        "ext_total_count": ext_total_c,
        "ext_total_rate": ext_total_c / n,
        "art": float(np.mean([r.art for r in records])),
        "cla": float(np.mean([r.cla for r in records])),
        "fl": float(np.mean([r.fl for r in records])),
        "pho": float(np.mean([r.pho for r in records])),
        "dis": float(np.mean([r.dis for r in records])),
        "soc": float(np.mean([r.soc for r in records])),
        "fit": float(np.mean([r.fit for r in records])),
        "merge_mass": float(np.mean([r.merge_mass for r in records])),
        "short_share": float(np.mean([r.short_share for r in records])),
        "markedness_delta": float(np.mean([r.markedness_delta for r in records])),
    }


def summarize_weakness(
    weakness_runs: list[dict[int, dict[str, list[float]]]],
) -> dict[int, dict[str, dict[str, float]]]:
    # year -> func -> stats
    res: dict[int, dict[str, dict[str, float]]] = {}
    for y in YEARS:
        res[y] = {}
        for fn in CELLS:
            vals: list[float] = []
            for run in weakness_runs:
                vals.extend(run.get(y, {}).get(fn, []))
            arr = np.array(vals) if vals else np.zeros(1)
            res[y][fn] = {
                "mean": float(np.mean(arr)),
                "median": float(np.median(arr)),
                "p90": float(np.percentile(arr, 90)),
                "max": float(np.max(arr)),
            }
    return res


def generate_markdown(
    all_summaries: dict[str, Any],
) -> str:
    lines: list[str] = [
        "# Diagnostika eroze koncovek (krok D0)",
        "",
        "Běh scénáře `village_grid(6, …)` s `FULL_GRAMMAR`, seedy 1..20, 3 000 let.",
        "Sledovány všechny zvukové inovace rozdělené na:",
        "- **Ending**: procesy zasahující koncovku gramatické buňky (`hits_ending > 0`)",
        "- **Root**: procesy zasahující výhradně kořen (`hits_ending == 0 and hits_root > 0`)",
        "- **Reductive ending**: redukční procesy (`apocope`, `coda_loss`, `syncope`, `vowel_reduction`) zasahující koncovku.",
        "",
        "### Definice kategorií osudu inovace",
        "V průběhu simulace proces prochází stavy, které se mohou částečně překrývat:",
        "- **Ustáleno (100 %)**: varianta dosáhla frekvence 1,0 v dané skupině (předtím byla fonologizována).",
        "- **Jen fonologizováno**: varianta přepsala $\\ge 1$ tvar v lexikonu, ale nedosáhla 100 % (následně zanikla nebo zůstává aktivní).",
        "- **Zaniklo bez fonologizace**: varianta vymřela, aniž by stihla přepsat jakýkoli tvar v lexikonu.",
        "- *Součty:* `Ustáleno` + `Jen fonologizováno` + `Zaniklo bez fonologizace` = $N$ (disjunktní rozklad).",
        "- *Doplňkové součty:* `Fonologizováno celkem` = `Ustáleno` + `Jen fonologizováno`; `Zaniklo celkem` = `Zaniklo bez fonologizace` + zaniklé po fonologizaci.",
        "",
        "## 1. Souhrnná tabulka osudu inovací a rozpadu fitness",
        "",
        "| Konfigurace | Cíl | N | Ustáleno (100 %) | Jen fonolog. | Zaniklo bez fon. | Fonolog. celkem | Zaniklo celkem | Fitness | Articul. | Clarity | FuncLoad | Phonotact. | Social |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for cfg_key, data in all_summaries.items():
        label = CONFIGURATIONS[cfg_key]["label"]
        for target_key, target_label in (
            ("ending", "Ending"),
            ("root", "Root"),
            ("reductive_ending", "Reductive Ending"),
        ):
            s = data["targets"][target_key]
            n = s["n"]
            est = f"{s.get('est_count', 0)} ({s['est_rate']*100:.1f} %)"
            ph_only = f"{s.get('ph_only_count', 0)} ({s['ph_only_rate']*100:.1f} %)"
            ext_no_ph = f"{s.get('ext_no_ph_count', 0)} ({s['ext_no_ph_rate']*100:.1f} %)"
            ph_total = f"{s.get('ph_count', 0)} ({s['ph_rate']*100:.1f} %)"
            ext_total = f"{s.get('ext_total_count', 0)} ({s['ext_total_rate']*100:.1f} %)"
            lines.append(
                f"| {label} | {target_label} | {n} | {est} | {ph_only} | {ext_no_ph} | {ph_total} | {ext_total} | "
                f"{s['fit']:+.3f} | {s['art']:+.3f} | {s['cla']:+.3f} | {s['fl']:+.3f} | {s['pho']:+.3f} | {s['soc']:+.3f} |"
            )

    lines.extend([
        "",
        "## 2. Rozbor redukčních rodin na koncovkách i kořenech (výchozí: penult / FL 5.0)",
        "",
        "| Pozice | Rodina | N | Ustáleno (100 %) | Jen fonolog. | Zaniklo bez fon. | Fonolog. celkem | Zaniklo celkem | Fitness | Articul. | Clarity | FuncLoad | Phonotact. | short_share | merge_mass |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])

    base_fams = all_summaries["penult_fl5"]["reductive_families"]
    for fam in REDUCTIVE_FAMILIES:
        for pos_key, pos_label in (("ending", "Koncovka (Ending)"), ("root", "Kořen (Root)")):
            s = base_fams[fam][pos_key]
            n = s["n"]
            if n == 0:
                lines.append(f"| {pos_label} | {fam} | 0 | — | — | — | — | — | — | — | — | — | — | — | — |")
                continue
            est = f"{s.get('est_count', 0)} ({s['est_rate']*100:.1f} %)"
            ph_only = f"{s.get('ph_only_count', 0)} ({s['ph_only_rate']*100:.1f} %)"
            ext_no_ph = f"{s.get('ext_no_ph_count', 0)} ({s['ext_no_ph_rate']*100:.1f} %)"
            ph_total = f"{s.get('ph_count', 0)} ({s['ph_rate']*100:.1f} %)"
            ext_total = f"{s.get('ext_total_count', 0)} ({s['ext_total_rate']*100:.1f} %)"
            lines.append(
                f"| {pos_label} | {fam} | {n} | {est} | {ph_only} | {ext_no_ph} | {ph_total} | {ext_total} | {s['fit']:+.3f} | {s['art']:+.3f} | {s['cla']:+.3f} | "
                f"{s['fl']:+.3f} | {s['pho']:+.3f} | {s['short_share']:.3f} | {s['merge_mass']:.4f} |"
            )

    lines.extend([
        "",
        "## 3. Vývoj slabosti (weakness) podle funkcí v čase",
        "",
        "### Rok 3 000 (konec běhu): Medián (Maximum) [Průměr]",
        "",
        "| Konfigurace | PAST | FUTURE | PL | OBJ | DEFINITE |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ])

    for cfg_key, data in all_summaries.items():
        label = CONFIGURATIONS[cfg_key]["label"]
        w3000 = data["weakness"][3000]
        cells_str = []
        for fn in CELLS:
            st = w3000[fn]
            cells_str.append(f"{st['median']:.3f} ({st['max']:.3f}) [{st['mean']:.3f}]")
        lines.append(f"| {label} | " + " | ".join(cells_str) + " |")

    lines.extend([
        "",
        "### Časový průběh mediánu weakness (výchozí: penult / FL 5.0)",
        "",
        "| Funkce | Rok 0 | Rok 1 000 | Rok 2 000 | Rok 3 000 | Max v r. 3 000 |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ])

    base_w = all_summaries["penult_fl5"]["weakness"]
    for fn in CELLS:
        r0 = base_w[0][fn]["median"]
        r1000 = base_w[1000][fn]["median"]
        r2000 = base_w[2000][fn]["median"]
        r3000 = base_w[3000][fn]["median"]
        mx3000 = base_w[3000][fn]["max"]
        lines.append(f"| {fn} | {r0:.3f} | {r1000:.3f} | {r2000:.3f} | {r3000:.3f} | {mx3000:.3f} |")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnostika eroze koncovek (krok D0)")
    parser.add_argument("--seeds", type=str, default="1..20", help="Rozsah seedů (např. 1..20)")
    parser.add_argument("--configs", type=str, default="all", help="Klíče konfigurací čárkou, nebo 'all'")
    parser.add_argument("--years", type=int, default=3000, help="Délka simulace v letech (default 3000)")
    parser.add_argument("--output", type=Path, default=Path("/tmp/cee-ending-erosion.json"))
    parser.add_argument("--markdown", type=Path, default=Path("/tmp/cee-ending-erosion.md"))
    args = parser.parse_args()

    if ".." in args.seeds:
        start_s, end_s = args.seeds.split("..")
        seeds = list(range(int(start_s), int(end_s) + 1))
    else:
        seeds = [int(s) for s in args.seeds.split(",")]

    configs_to_run = (
        list(CONFIGURATIONS.keys())
        if args.configs == "all"
        else [c.strip() for c in args.configs.split(",")]
    )

    all_summaries: dict[str, Any] = {}
    all_raw_data: dict[str, Any] = {}

    total_runs = len(configs_to_run) * len(seeds)
    run_idx = 0
    t0_global = time.perf_counter()

    for cfg_key in configs_to_run:
        cfg = CONFIGURATIONS[cfg_key]
        rule = cast(StressRule, cfg["rule"])
        fl_scale = float(cfg["fl_scale"])
        label = cfg["label"]

        cfg_records: list[InnovationRecord] = []
        cfg_weakness: list[dict[int, dict[str, list[float]]]] = []

        print("\n=======================================================")
        print(f"Spouštím konfiguraci: {cfg_key} ({label})")
        print("=======================================================")

        for seed in seeds:
            run_idx += 1
            t0 = time.perf_counter()
            recs, w_by_yr = run_single(
                seed=seed,
                config_key=cfg_key,
                rule=rule,
                fl_scale=fl_scale,
                columns=6,
                max_year=args.years,
            )
            elapsed = time.perf_counter() - t0
            cfg_records.extend(recs)
            cfg_weakness.append(w_by_yr)

            end_recs = [r for r in recs if r.hits_ending > 0]
            root_recs = [r for r in recs if r.hits_ending == 0 and r.hits_root > 0]
            print(
                f"[{run_idx}/{total_runs}] {cfg_key} seed={seed:2d} ({elapsed:.1f}s) "
                f"Inovace: sound={len(recs)} (end={len(end_recs)}, root={len(root_recs)})",
                flush=True,
            )

        # Summarize this configuration
        ending_recs = [r for r in cfg_records if r.hits_ending > 0]
        root_recs = [r for r in cfg_records if r.hits_ending == 0 and r.hits_root > 0]
        reductive_ending_recs = [
            r for r in ending_recs if r.family in REDUCTIVE_FAMILIES
        ]

        fam_summaries: dict[str, dict[str, Any]] = {}
        for fam in REDUCTIVE_FAMILIES:
            fam_ending_recs = [r for r in ending_recs if r.family == fam]
            fam_root_recs = [r for r in root_recs if r.family == fam]
            fam_summaries[fam] = {
                "ending": summarize_target(fam_ending_recs),
                "root": summarize_target(fam_root_recs),
            }

        w_summary = summarize_weakness(cfg_weakness)

        all_summaries[cfg_key] = {
            "config": cfg,
            "targets": {
                "ending": summarize_target(ending_recs),
                "root": summarize_target(root_recs),
                "reductive_ending": summarize_target(reductive_ending_recs),
            },
            "reductive_families": fam_summaries,
            "weakness": w_summary,
        }

        all_raw_data[cfg_key] = {
            "records": [asdict(r) for r in cfg_records],
        }

    total_elapsed = time.perf_counter() - t0_global
    print(f"\nHotovo všech {total_runs} běhů za {total_elapsed:.1f} s.")

    # Save outputs
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {"summaries": all_summaries, "raw": all_raw_data},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Uloženo JSON: {args.output}")

    md_text = generate_markdown(all_summaries)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(md_text, encoding="utf-8")
    print(f"Uloženo Markdown: {args.markdown}")
    print("\n" + md_text)


if __name__ == "__main__":
    main()
