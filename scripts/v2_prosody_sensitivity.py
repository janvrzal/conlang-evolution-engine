"""Měření citlivosti síly přízvuku (krok D2).

Testuje násobek STRESS_STRENGTH_MULTIPLIER v {1.0, 1.5, 2.0} napříč 20 seedy (3 000 let)
pro 3 podmínky:
1. initial_strong: silný přízvuk na 1. slabice (iniciální)
2. penult_strong: silný přízvuk na předposlední slabice (penult)
3. evolving_weak: výchozí stav penult + weak, kde se prozódie i síla volně vyvíjejí
"""

from __future__ import annotations

import json
import time
from typing import Any, Literal

import numpy as np

from cee.v2 import syntax
from cee.v2.language.processes import StressRule
from cee.v2.pressures import linguistic
from cee.v2.scenarios import FULL_GRAMMAR, village_grid
from cee.v2.simulation import Simulation

SEEDS = range(1, 21)  # 20 seedů
YEARS = 3000
MULTIPLIERS = [1.0, 1.5, 2.0]
CELLS = ("PAST", "FUTURE", "PL", "OBJ", "DEFINITE")
REDUCTIVE_FAMILIES = {"apocope", "coda_loss", "syncope", "vowel_reduction"}


def run_condition_m(
    condition_name: str,
    multiplier: float,
    rule: StressRule,
    strength: Literal["weak", "strong"],
    seeds: range = SEEDS,
) -> dict[str, Any]:
    # 1. Ověření propagace hodnoty
    linguistic.STRESS_STRENGTH_MULTIPLIER = multiplier
    assert (
        linguistic.STRESS_STRENGTH_MULTIPLIER == multiplier
    ), f"Hodnota M={multiplier} se nepropsala do linguistic.STRESS_STRENGTH_MULTIPLIER!"

    started = time.perf_counter()
    weakness_by_fn: dict[str, list[float]] = {fn: [] for fn in CELLS}

    # Čítače osudu pro reduktivní koncovky (Ending) a kořeny (Root)
    ending_stats: dict[str, Any] = {
        "n": 0,
        "established": 0,
        "phonologized_only": 0,
        "extinct_no_phon": 0,
        "phonologized_total": 0,
        "extinct_total": 0,
    }
    root_stats: dict[str, Any] = {
        "n": 0,
        "established": 0,
        "phonologized_only": 0,
        "extinct_no_phon": 0,
        "phonologized_total": 0,
        "extinct_total": 0,
    }

    by_family: dict[str, dict[str, int]] = {
        fam: {"n": 0, "established": 0, "phonologized_only": 0, "extinct_no_phon": 0}
        for fam in sorted(REDUCTIVE_FAMILIES)
    }

    # Fitness rozpad na reduktivních koncovkách
    fit_sums = {"fit": 0.0, "art": 0.0, "cla": 0.0, "fl": 0.0, "pho": 0.0, "soc": 0.0}

    category_loss_events = 0
    stress_rule_changes = 0
    stress_strength_changes = 0

    for seed in seeds:
        world = village_grid(
            6,
            seed=seed,
            phonology=True,
            morphology=True,
            semantics=True,
            syntax=True,
            grammar=dict(FULL_GRAMMAR),
            stress_rule=rule,
            stress_strength=strength,
        )
        sim = Simulation(world)

        # Inovace a jejich zasažení koncovek/kořenů
        # Ukládáme: var_id, variant_id, group_id, family, hits_ending, hits_root
        innovations: list[dict[str, Any]] = []

        last_idx = 0
        current_year = 0
        while current_year < YEARS:
            sim.step()
            current_year = int(round(sim.year))
            evs = sim.history.events[last_idx:]
            last_idx = len(sim.history.events)

            for ev in evs:
                kind = ev["kind"]
                if kind == "category_lost":
                    category_loss_events += 1
                elif kind == "stress_rule_changed":
                    stress_rule_changes += 1
                elif kind == "stress_strength_changed":
                    stress_strength_changes += 1
                elif kind == "innovation" and ev.get("variable") in world.processes:
                    var_id = ev["variable"]
                    grp_id = ev["group"]
                    code = world.groups[grp_id].main_code
                    proc = world.processes[var_id]

                    hits_ending = 0
                    hits_root = 0

                    assert world.table is not None
                    for u_id in code.phonology.vocabulary:
                        u = world.unit_of(code, u_id)
                        m = world.morphemes[u_id]
                        sites = proc.sites(u.form, world.table, code.stress_rule)
                        if sites:
                            if m.cell in CELLS and u.boundary is not None:
                                for s in sites:
                                    if s >= u.boundary:
                                        hits_ending += 1
                                    else:
                                        hits_root += 1
                            else:
                                hits_root += len(sites)

                    is_reductive = (
                        getattr(proc, "reductive", False)
                        or getattr(proc, "stress", None) == "unstressed"
                    )

                    # Spočti fitness komponenty
                    art = proc.ease
                    if code.stress_strength == "strong" and is_reductive:
                        art *= multiplier

                    innovations.append({
                        "var_id": var_id,
                        "variant_id": ev["variant"],
                        "group_id": grp_id,
                        "family": ev["change"],
                        "is_reductive": is_reductive,
                        "hits_ending": hits_ending,
                        "hits_root": hits_root,
                        "art": art,
                    })

        # Zaznamenej slabost na konci běhu
        for group in world.groups.values():
            code = group.main_code
            for fn in CELLS:
                w = syntax.weakness(world, code, fn)
                weakness_by_fn[fn].append(w)

        # Vyhodnoť osud variant
        phonologized_vars = {
            (e["variable"], e["group"])
            for e in sim.history.events
            if e["kind"] == "phonologized"
        }
        established_vars = {
            (e["variant"], e["group"])
            for e in sim.history.events
            if e["kind"] == "established"
        }

        for inv in innovations:
            if not inv["is_reductive"]:
                continue

            var_grp = (inv["var_id"], inv["group_id"])
            varnt_grp = (inv["variant_id"], inv["group_id"])

            is_est = varnt_grp in established_vars
            is_ph = var_grp in phonologized_vars

            fam = inv["family"]

            # Ending
            if inv["hits_ending"] > 0:
                ending_stats["n"] += 1
                if is_est:
                    ending_stats["established"] += 1
                    ending_stats["phonologized_total"] += 1
                elif is_ph:
                    ending_stats["phonologized_only"] += 1
                    ending_stats["phonologized_total"] += 1
                else:
                    ending_stats["extinct_no_phon"] += 1
                    ending_stats["extinct_total"] += 1

                if fam in by_family:
                    by_family[fam]["n"] += 1
                    if is_est:
                        by_family[fam]["established"] += 1
                    elif is_ph:
                        by_family[fam]["phonologized_only"] += 1
                    else:
                        by_family[fam]["extinct_no_phon"] += 1

                fit_sums["art"] += inv["art"]

            # Root
            if inv["hits_root"] > 0 and inv["hits_ending"] == 0:
                root_stats["n"] += 1
                if is_est:
                    root_stats["established"] += 1
                    root_stats["phonologized_total"] += 1
                elif is_ph:
                    root_stats["phonologized_only"] += 1
                    root_stats["phonologized_total"] += 1
                else:
                    root_stats["extinct_no_phon"] += 1
                    root_stats["extinct_total"] += 1

    elapsed = time.perf_counter() - started

    weakness_summary = {}
    for fn, vals in sorted(weakness_by_fn.items()):
        arr = np.array(vals)
        weakness_summary[fn] = {
            "median": float(np.median(arr)),
            "p90": float(np.percentile(arr, 90)),
            "max": float(np.max(arr)),
            "mean": float(np.mean(arr)),
            "gt_0": float(np.mean(arr > 0)),
        }

    n_end = max(1, ending_stats["n"])
    mean_art = fit_sums["art"] / n_end

    return {
        "condition": condition_name,
        "multiplier": multiplier,
        "rule": rule,
        "strength": strength,
        "seconds": elapsed,
        "ending_stats": ending_stats,
        "root_stats": root_stats,
        "by_family": by_family,
        "mean_art_ending": mean_art,
        "weakness": weakness_summary,
        "category_loss_events": category_loss_events,
        "stress_rule_changes": stress_rule_changes,
        "stress_strength_changes": stress_strength_changes,
    }


def main() -> None:
    print("=== MĚŘENÍ CITLIVOSTI SÍLY PŘÍZVUKU (krok D2) ===")
    print(f"Seedy: 1..{len(SEEDS)} ({len(SEEDS)} běhů), {YEARS} let, vesnic: 6\n")

    conditions: list[tuple[str, StressRule, Literal["weak", "strong"]]] = [
        ("initial_strong", "initial", "strong"),
        ("penult_strong", "penult", "strong"),
        ("evolving_weak", "penult", "weak"),
    ]

    results: list[dict[str, Any]] = []

    for cond_name, rule, strength in conditions:
        print(f"--- Podmínka: {cond_name} ({rule} + {strength}) ---")
        for m in MULTIPLIERS:
            print(f"Spouštím M = {m} ... ", end="", flush=True)
            res = run_condition_m(cond_name, m, rule, strength)
            print(f"hotovo ({res['seconds']:.1f} s)")
            results.append(res)

    out_path = "/tmp/cee-prosody-sensitivity.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nVýsledky uloženy do {out_path}")

    # Vypiš tabulky
    print("\n### TABULKA 1: Eroze reduktivních koncovek podle násobku M")
    print(
        "| Podmínka | M | N | Ustáleno | Jen fonol. | Zaniklo | Fonol. celkem | Art. ease | CatLoss |"
    )
    print(
        "|---|---|---|---|---|---|---|---|---|"
    )
    for r in results:
        es = r["ending_stats"]
        n = es["n"]
        est_pct = (es["established"] / n * 100) if n else 0
        ph_pct = (es["phonologized_only"] / n * 100) if n else 0
        ext_pct = (es["extinct_no_phon"] / n * 100) if n else 0
        tot_ph_pct = (es["phonologized_total"] / n * 100) if n else 0
        print(
            f"| {r['condition']} | {r['multiplier']} | {n} | "
            f"{es['established']} ({est_pct:.1f} %) | {es['phonologized_only']} ({ph_pct:.1f} %) | "
            f"{es['extinct_no_phon']} ({ext_pct:.1f} %) | {es['phonologized_total']} ({tot_ph_pct:.1f} %) | "
            f"+{r['mean_art_ending']:.3f} | {r['category_loss_events']} |"
        )

    print("\n### TABULKA 2: Rozbor redukčních rodin na koncovkách (initial + strong)")
    print("| M | Rodina | N | Ustáleno | Jen fonol. | Zaniklo bez fon. |")
    print("|---|---|---|---|---|---|")
    for r in results:
        if r["condition"] == "initial_strong":
            for fam, st in sorted(r["by_family"].items()):
                n = st["n"]
                est_pct = (st["established"] / n * 100) if n else 0
                ph_pct = (st["phonologized_only"] / n * 100) if n else 0
                ext_pct = (st["extinct_no_phon"] / n * 100) if n else 0
                print(
                    f"| {r['multiplier']} | {fam} | {n} | {st['established']} ({est_pct:.1f} %) | "
                    f"{st['phonologized_only']} ({ph_pct:.1f} %) | {st['extinct_no_phon']} ({ext_pct:.1f} %) |"
                )

    print("\n### TABULKA 3: Slabost (weakness) v roce 3 000")
    print("| Podmínka | M | OBJ (med / max) | PL (med / max) | PAST (med / max) | FUT (med / max) | DEF (med / max) |")
    print("|---|---|---|---|---|---|---|")
    for r in results:
        w = r["weakness"]

        def fmt(fn: str) -> str:
            d = w[fn]
            return f"{d['median']:.3f} / {d['max']:.3f}"

        print(
            f"| {r['condition']} | {r['multiplier']} | {fmt('OBJ')} | {fmt('PL')} | {fmt('PAST')} | {fmt('FUTURE')} | {fmt('DEFINITE')} |"
        )


if __name__ == "__main__":
    main()
