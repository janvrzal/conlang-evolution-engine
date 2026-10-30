"""Měření řetězce eroze koncovek (krok D2b).

Sleduje kauzální řetěz:
redukce (V -> ə) -> apokopa (ə -> ∅) -> splynutí tvarů -> CategoryLoss / Periphrasis

Testuje citlivost:
1. CLARITY_DELETE_SCHWA v {-0.15, -0.05, -0.02}
2. CODA_TOLERANCE_SCALE v {0.0, 0.5, 1.0}

Přes 20 seedů, 3 000 let, pro podmínky initial_strong, penult_strong, evolving_weak.
"""

from __future__ import annotations

import json
import time
from typing import Any, Literal

import numpy as np

from cee.v2 import syntax
from cee.v2.changes import sound
from cee.v2.language.processes import StressRule
from cee.v2.pressures import linguistic
from cee.v2.scenarios import FULL_GRAMMAR, village_grid
from cee.v2.simulation import Simulation

SEEDS = range(1, 21)
YEARS = 3000
CELLS = ("PAST", "FUTURE", "PL", "OBJ", "DEFINITE")


def run_chain_experiment(
    cond_name: str,
    rule: StressRule,
    strength: Literal["weak", "strong"],
    clarity_schwa: float,
    coda_tol: float,
    stress_mult: float = 1.5,
    clarity_full: float = -0.15,
    seeds: range = SEEDS,
) -> dict[str, Any]:
    # 1. Nastavení a ověření propagace
    sound.CLARITY_DELETE_SCHWA = clarity_schwa
    sound.CLARITY_DELETE_FULL = clarity_full
    linguistic.CODA_TOLERANCE_SCALE = coda_tol
    linguistic.STRESS_STRENGTH_MULTIPLIER = stress_mult

    assert sound.CLARITY_DELETE_SCHWA == clarity_schwa
    assert linguistic.CODA_TOLERANCE_SCALE == coda_tol

    started = time.perf_counter()
    weakness_by_fn: dict[str, list[float]] = {fn: [] for fn in CELLS}

    stats: dict[str, Any] = {
        "vowel_reduction": {"n": 0, "est": 0, "ph": 0, "ext": 0},
        "apocope_schwa": {"n": 0, "est": 0, "ph": 0, "ext": 0},
        "apocope_full": {"n": 0, "est": 0, "ph": 0, "ext": 0},
        "coda_loss": {"n": 0, "est": 0, "ph": 0, "ext": 0},
        "category_loss_events": 0,
        "periphrasis_events": 0,
    }

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
                    stats["category_loss_events"] = int(stats["category_loss_events"]) + 1
                elif kind == "innovation" and ev.get("change") == "periphrasis":
                    stats["periphrasis_events"] = int(stats["periphrasis_events"]) + 1
                elif kind == "innovation" and ev.get("variable") in world.processes:
                    var_id = ev["variable"]
                    grp_id = ev["group"]
                    code = world.groups[grp_id].main_code
                    proc = world.processes[var_id]

                    hits_ending = 0
                    assert world.table is not None
                    for u_id in code.phonology.vocabulary:
                        u = world.unit_of(code, u_id)
                        m = world.morphemes[u_id]
                        sites = proc.sites(u.form, world.table, code.stress_rule)
                        if sites and m.cell in CELLS and u.boundary is not None:
                            for s in sites:
                                if s >= u.boundary:
                                    hits_ending += 1

                    fam = proc.family
                    if hits_ending > 0 and fam in ("vowel_reduction", "apocope", "coda_loss"):
                        is_schwa = getattr(proc, "is_schwa", False) or proc.label.startswith("ə → ∅")
                        innovations.append({
                            "var_id": var_id,
                            "variant_id": ev["variant"],
                            "group_id": grp_id,
                            "family": fam,
                            "is_schwa": is_schwa,
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
            var_grp = (inv["var_id"], inv["group_id"])
            varnt_grp = (inv["variant_id"], inv["group_id"])
            is_est = varnt_grp in established_vars
            is_ph = var_grp in phonologized_vars

            fam = inv["family"]
            target_key = fam
            if fam == "apocope":
                target_key = "apocope_schwa" if inv["is_schwa"] else "apocope_full"

            if target_key in stats:
                st = stats[target_key]
                assert isinstance(st, dict)
                st["n"] += 1
                if is_est:
                    st["est"] += 1
                elif is_ph:
                    st["ph"] += 1
                else:
                    st["ext"] += 1

    elapsed = time.perf_counter() - started

    weakness_summary = {}
    for fn, vals in sorted(weakness_by_fn.items()):
        arr = np.array(vals)
        weakness_summary[fn] = {
            "median": float(np.median(arr)),
            "max": float(np.max(arr)),
            "mean": float(np.mean(arr)),
        }

    return {
        "condition": cond_name,
        "rule": rule,
        "strength": strength,
        "clarity_schwa": clarity_schwa,
        "coda_tol": coda_tol,
        "seconds": elapsed,
        "stats": stats,
        "weakness": weakness_summary,
    }


def main() -> None:
    print("=== MĚŘENÍ ŘETĚZCE EROZE KONCOVEK (krok D2b) ===")
    print(f"Seedy: 1..{len(SEEDS)}, {YEARS} let, vesnic: 6\n")

    runs: list[dict[str, Any]] = []

    # 1. Citlivost na CLARITY_DELETE_SCHWA (initial_strong, coda_tol=0.5)
    print("--- 1. Citlivost na CLARITY_DELETE_SCHWA (initial_strong, coda_tol=0.5) ---")
    for cla_schwa in [-0.15, -0.05, -0.02]:
        print(f"Spouštím clarity_schwa = {cla_schwa} ... ", end="", flush=True)
        r = run_chain_experiment("initial_strong", "initial", "strong", clarity_schwa=cla_schwa, coda_tol=0.5)
        print(f"hotovo ({r['seconds']:.1f} s)")
        runs.append(r)

    # 2. Citlivost na CODA_TOLERANCE_SCALE (initial_strong, clarity_schwa=-0.05)
    print("\n--- 2. Citlivost na CODA_TOLERANCE_SCALE (initial_strong, clarity_schwa=-0.05) ---")
    for c_tol in [0.0, 1.0]:  # 0.5 už máme z bodu 1
        print(f"Spouštím coda_tol = {c_tol} ... ", end="", flush=True)
        r = run_chain_experiment("initial_strong", "initial", "strong", clarity_schwa=-0.05, coda_tol=c_tol)
        print(f"hotovo ({r['seconds']:.1f} s)")
        runs.append(r)

    # 3. Podmínky penult_strong a evolving_weak (výchozí parametry D2b: cla=-0.05, tol=0.5)
    print("\n--- 3. Ostatní podmínky s výchozími parametry D2b (cla=-0.05, tol=0.5) ---")
    for cond_name, rule, strength in [
        ("penult_strong", "penult", "strong"),
        ("evolving_weak", "penult", "weak"),
    ]:
        print(f"Spouštím {cond_name} ... ", end="", flush=True)
        r = run_chain_experiment(cond_name, rule, strength, clarity_schwa=-0.05, coda_tol=0.5)  # type: ignore[arg-type]
        print(f"hotovo ({r['seconds']:.1f} s)")
        runs.append(r)

    # Obnov výchozí konstanty
    sound.CLARITY_DELETE_SCHWA = -0.05
    sound.CLARITY_DELETE_FULL = -0.15
    linguistic.CODA_TOLERANCE_SCALE = 0.0
    linguistic.STRESS_STRENGTH_MULTIPLIER = 1.5

    out_file = "/tmp/cee-erosion-chain.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(runs, f, indent=2, ensure_ascii=False)
    print(f"\nVýsledky uloženy do {out_file}\n")

    # Tiskneme tabulku řetězce
    print("### TABULKA ŘETĚZCE EROZE")
    print("| Podmínka | cla_schwa | coda_tol | Redukce vokálů (est/n) | Apokopa ə (est/n) | Apokopa plná (est/n) | CodaLoss (est/n) | PL weakness (med/max) | CatLoss | Perifráze |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        st = r["stats"]
        vr = st["vowel_reduction"]
        aps = st["apocope_schwa"]
        apf = st["apocope_full"]
        cl = st["coda_loss"]
        w = r["weakness"]["PL"]
        print(
            f"| {r['condition']} | {r['clarity_schwa']} | {r['coda_tol']} | "
            f"{vr['est']}/{vr['n']} | {aps['est']}/{aps['n']} | {apf['est']}/{apf['n']} | {cl['est']}/{cl['n']} | "
            f"{w['median']:.3f} / {w['max']:.3f} | {st['category_loss_events']} | {st['periphrasis_events']} |"
        )


if __name__ == "__main__":
    main()
