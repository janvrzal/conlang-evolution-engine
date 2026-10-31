"""Obrození jazyka (M6f): hlavní město jazyka ``a`` a region ``x`` jazyka ``b``.

Stát od roku 0 vynucuje úřední jazyk; region má vlastní identitu
(``distinct``). Varianty obrození se liší tím, co se stane v roce 75 (jazyk
ještě žije) nebo v roce 400 (jazyk už vymřel). Vypíše podíl obyvatel
regionu, kteří doma mluví jazykem ``b``. Demografie je deterministická,
stačí jeden seed.

Použití:  python scripts/v2_revival.py
"""

from __future__ import annotations

import multiprocessing

from cee.v2.events import WorldEvent
from cee.v2.polity import Revival, Schools, Secession, Standard, State, language_census
from cee.v2.scenarios import ProtoLanguage, Region, region_world
from cee.v2.simulation import Simulation

YEARS = (75, 150, 300, 400, 500, 700, 1000)
STATE = State(0.0, "k", ("capital", "x"), "capital", policy="enforced")
VARIANTS: dict[str, list[WorldEvent]] = {
    "bez obrození": [STATE],
    "hnutí od 75, stát trvá": [STATE, Revival(75.0, ("x",))],
    "národní hnutí, norma a škola od 75": [
        STATE, Revival(75.0, ("x",), strength="national"), Standard(75.0, "x"), Schools(75.0, "x"),
    ],
    "odtržení a národní obrození od 75": [
        STATE, Secession(75.0, "x-state", ("x",), "x"), Revival(75.0, ("x",), strength="national"),
        Standard(75.0, "x-state"), Schools(75.0, "x-state"),
    ],
    "vymřelý jazyk z písma: odtržení a obrození od 400": [
        Standard(0.0, "x"), STATE, Secession(400.0, "x-state", ("x",), "x"),
        Revival(400.0, ("x",), strength="national"),
    ],
    "totéž se školou v obrozeném jazyce": [
        Standard(0.0, "x"), STATE, Secession(400.0, "x-state", ("x",), "x"),
        Revival(400.0, ("x",), strength="national"), Schools(400.0, "x"),
    ],
}


def run(name: str) -> tuple[str, list[float]]:
    regions = (
        Region("capital", (0.0, 0.0), density=2.0, neighbours=("x",), language="a", villages=4),
        Region("x", (60.0, 0.0), neighbours=("capital",), language="b", villages=4, identity="distinct"),
    )
    world = region_world(regions, seed=1, languages=(ProtoLanguage("a"), ProtoLanguage("b")))
    simulation = Simulation(world, events=VARIANTS[name])
    shares = []
    for year in YEARS:
        simulation.run(year)
        shares.append(language_census(world)["x"]["home"].get("b", 0.0))
    return name, shares


def main() -> None:
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        results = pool.map(run, list(VARIANTS))
    print("| varianta | " + " | ".join(str(year) for year in YEARS) + " |")
    print("|---|" + "---:|" * len(YEARS))
    for name, shares in results:
        print(f"| {name} | " + " | ".join(f"{share:.2f}" for share in shares) + " |")


if __name__ == "__main__":
    main()
