"""Ukázkový stát čtyř jazyků (``scenarios.kingdom``, M6f): kdo přejde a kdo ne.

Pro každou variantu politiky vypíše podíl obyvatel regionů, kteří doma
mluví svým původním jazykem, v čase. Demografie kódů je deterministická
(nezávisí na proudu náhody), proto stačí jeden seed.

Použití:  python scripts/v2_kingdom.py
"""

from __future__ import annotations

import multiprocessing
from typing import Any

from cee.v2.polity import language_census
from cee.v2.scenarios import kingdom
from cee.v2.simulation import Simulation

YEARS = (300, 600, 700, 900, 1500)
REGIONS = (("plain", "b"), ("south", "d"), ("mountains", "c"))
VARIANTS: dict[str, dict[str, Any]] = {
    "tolerantní": {"policy": "tolerant"},
    "podporovaný jazyk": {"policy": "promoted"},
    "podporovaný, od 600 vynucovaný": {"policy": "promoted", "modern": 600.0},
    "lingua franca, tolerantní stát": {"policy": "tolerant", "lingua_franca": True},
}


def run(name: str) -> tuple[str, list[dict[str, float]]]:
    world, events = kingdom(1, **VARIANTS[name])
    simulation = Simulation(world, events=events)
    frames = []
    for year in YEARS:
        simulation.run(year)
        census = language_census(world)
        frames.append({region: census[region]["home"].get(language, 0.0) for region, language in REGIONS})
    return name, frames


def main() -> None:
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        results = pool.map(run, list(VARIANTS))
    print("| varianta | region | " + " | ".join(str(year) for year in YEARS) + " |")
    print("|---|---|" + "---:|" * len(YEARS))
    for name, frames in results:
        for region, _ in REGIONS:
            cells = " | ".join(f"{frame[region]:.2f}" for frame in frames)
            print(f"| {name} | {region} | {cells} |")


if __name__ == "__main__":
    main()
