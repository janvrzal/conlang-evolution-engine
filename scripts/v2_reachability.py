"""Test dosažitelnosti cyklu gramatických kategorií (příprava M7).

Otázka: existuje v rozumných mezích konstant nastavení, při kterém flexivní
kategorie (plurál, člen, minulý a budoucí čas) nejen vznikají, ale i zanikají,
takže se typologická pestrost po 5 000 letech udrží? Nehledá nejlepší
nastavení; zkouší rohy prostoru po jednom faktoru a zapisuje, co se stalo.

Start z WALS (gramatika i pravidlo přízvuku losované z `v2_typology.json`),
`village_grid`, souvislé seedy 1..N. Kontakt se modeluje stálým podílem L2
mluvčích ve všech skupinách (``immigration`` = ``l2_share``).
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

from cee.v2 import metrics, syntax
from cee.v2.parameters import Parameters
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation
from scripts.v2_typology import capture, load_reference, sample_grammar, sample_stress_rule

YEARS = (0, 1000, 2000, 3000, 5000)
FEATURES = ("33A", "37A", "66A", "67A")
PRESENT = {"plural_present", "definite_present", "past_present", "67A-1"}
ABSENT = {"plural_absent", "definite_absent", "past_absent", "67A-2"}


@dataclass(frozen=True)
class Config:
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    strength: str | None = None
    l2_share: float = 0.0


CONFIGS = (
    Config("výchozí"),
    Config("silný přízvuk ×1,5", strength="strong"),
    Config("silný přízvuk ×2,0", {"stress_strength_multiplier": 2.0}, strength="strong"),
    Config("×2,0 + FL 1,0", {"stress_strength_multiplier": 2.0, "functional_load_scale": 1.0},
           strength="strong"),
    Config("×2,0 + FL 1,0 + tolerance kody 1,0",
           {"stress_strength_multiplier": 2.0, "functional_load_scale": 1.0, "coda_tolerance_scale": 1.0},
           strength="strong"),
    Config("L2 0,2", l2_share=0.2),
    Config("L2 0,5", l2_share=0.5),
    Config("L2 0,5, learnability 0,5", {"learnability_strength": 0.5}, l2_share=0.5),
)


def _state(value: str | None) -> str | None:
    if value in PRESENT:
        return "present"
    if value in ABSENT:
        return "absent"
    return None


def run_one(config: Config, seed: int, reference: dict[str, Any]) -> dict[str, Any]:
    grammar = sample_grammar(seed, reference)
    rule = sample_stress_rule(seed, reference)
    options: dict[str, Any] = {}
    if config.strength is not None:
        options["stress_strength"] = config.strength
    world = village_grid(6, seed=seed, syntax=True, semantics=True, phonology=True, morphology=True,
                         grammar=grammar, stress_rule=cast(Any, rule),
                         params=replace(Parameters(), **config.params), **options)
    for group in world.groups.values():
        group.immigration = config.l2_share
        group.main_code.l2_share = config.l2_share
    simulation = Simulation(world)
    frames = [capture(simulation)]
    for year in YEARS[1:]:
        simulation.run(year)
        frames.append(capture(simulation))
    losses = 0
    for event in simulation.history.of_kind("established"):
        if not str(event.get("variable", "")).startswith("construction:"):
            continue
        construction = syntax.construction_of(world, event["variant"])
        if construction.kind == "zero":
            losses += 1
    weakness_max = {
        function: max(syntax.weakness(world, group.main_code, function) for group in world.groups.values())
        for function in ("PL", "PAST", "OBJ")
    }
    states = [
        [{feature: _state(profile.get(feature)) for feature in FEATURES} for profile in frame["profiles"]]
        for frame in frames
    ]
    return {"seed": seed, "losses_established": losses, "weakness_max": weakness_max, "states": states}


def summarize(config: Config, runs: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"config": config.name, "losses_established": sum(r["losses_established"] for r in runs)}
    for feature in FEATURES:
        series = []
        for index, year in enumerate(YEARS):
            values = [lang[feature] for run in runs for lang in run["states"][index] if lang[feature] is not None]
            present = sum(value == "present" for value in values)
            series.append({"year": year, "present": present, "n": len(values)})
        final = series[-1]
        share = final["present"] / final["n"] if final["n"] else 0.0
        entropy = metrics.normalized_entropy({"present": share, "absent": 1.0 - share}, ["present", "absent"])
        lost = gained = 0
        for run in runs:
            # Přechody mezi po sobě jdoucími odečty prvního pozorovaného jazyka.
            path = [frame[0][feature] for frame in run["states"] if frame and frame[0][feature] is not None]
            lost += sum(1 for before, after in zip(path, path[1:]) if (before, after) == ("present", "absent"))
            gained += sum(1 for before, after in zip(path, path[1:]) if (before, after) == ("absent", "present"))
        result[feature] = {"series": series, "entropy_5000": abs(entropy), "lost": lost, "gained": gained}
    result["weakness_max"] = {
        function: max(run["weakness_max"][function] for run in runs) for function in ("PL", "PAST", "OBJ")
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--only", type=int, help="run just this config index (for a smoke test)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reference = load_reference()
    summaries = []
    configs = CONFIGS if args.only is None else (CONFIGS[args.only],)
    for config in configs:
        runs = []
        for seed in range(1, args.seeds + 1):
            started = time.perf_counter()
            runs.append(run_one(config, seed, reference))
            print(f"{config.name} seed={seed} {time.perf_counter() - started:.1f}s", flush=True)
        summaries.append(summarize(config, runs))
        args.output.write_text(json.dumps(summaries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
