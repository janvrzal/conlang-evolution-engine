"""Kalibrace M7: retence základní slovní zásoby na ``region_world``.

Měří, kolik pojmů vyjadřuje vesnice po 1 000, 2 000 a 3 000 letech pořád
zděděným slovem, zvlášť pro Swadeshův seznam (100 pojmů) a pro rozšíření
o kulturní slovní zásobu. Cíl glottochronologie: Swadeshův seznam asi 86 %
za tisíciletí (Lees 1953; rozptyl mezi jazyky asi 75–95 %). Tempo slovních
změn se ladí jedním násobkem ``Parameters.change_rates`` pro všechny
lexikální rodiny, aby se neměnil jejich poměr.

Druhý parametr je převod hustoty osídlení na velikost vesnice
(``Parameters.population_per_density``): menší vesnice znamenají silnější
drift, a tedy rychlejší šíření nových slov bez výhody.

Třetí je míra pozadí dějin (``--backgrounds``, viz :mod:`cee.v2.background`)
a ``--contact``: polovina krajů mluví jiným jazykem, takže na hranici
vznikají výpůjčky. Zděděné slovo je jen to, které skupina měla od počátku
ve svém jazyce; slovo druhého jazyka se počítá jako výpůjčka.
Cíl: izolovaný jazyk asi 95–97 % za tisíciletí (islandština, Bergsland
& Vogt 1962), jazyk v kontaktu asi 85–88 %.

Použití:  python scripts/v2_calibrate_retention.py --backgrounds none normal --contact --seeds 1-8
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import statistics

from cee.data.core_vocabulary import SWADESH_CORE
from cee.v2.background import generate
from cee.v2.changes import LEXICAL_CHANGES
from cee.v2.parameters import Parameters
from cee.v2.scenarios import ProtoLanguage, Region, region_world
from cee.v2.simulation import Simulation

YEARS = (1000, 2000, 3000)


def world(seed: int, scale: float, population: float = 500.0, background: str = "none",
          contact: bool = False, overrides: tuple[tuple[str, float], ...] = ()):
    """Šest krajů 3 × 2; s ``contact`` mluví spodní řada jazykem ``b``."""
    regions = tuple(
        Region(f"r{i}", (60.0 * (i % 3), 60.0 * (i // 3)), language="b" if contact and i >= 3 else "a",
               villages=3,
               neighbours=tuple(f"r{j}" for j in range(6)
                                if j != i and abs(j % 3 - i % 3) + abs(j // 3 - i // 3) == 1))
        for i in range(6)
    )
    rates = {change.kind: scale for change in LEXICAL_CHANGES}
    # ``w.jméno=váha`` přepíše váhu tlaku (``Parameters.pressure_weights``),
    # ``r.druh=násobek`` tempo jedné změny (``Parameters.change_rates``).
    weights = {name[2:]: value for name, value in overrides if name.startswith("w.")}
    rates.update({name[2:]: scale * value for name, value in overrides if name.startswith("r.")})
    fields = {name: value for name, value in overrides if not name.startswith(("w.", "r."))}
    params = Parameters(change_rates=rates, population_per_density=population, pressure_weights=weights, **fields)
    languages = (ProtoLanguage("a"), ProtoLanguage("b")) if contact else (ProtoLanguage("a"),)
    built = region_world(regions, seed=seed, languages=languages, semantics=True, params=params)
    events = generate([(r.id, r.neighbours, r.language) for r in regions], start=0.0, end=float(YEARS[-1]),
                      level_name=background, seed=seed, params=params)
    return built, events


def inherited(world_) -> dict[str, dict[str, set[str]]]:
    """Zděděná slova každého jazyka na počátku: jazyk → proměnná → varianty."""
    found: dict[str, dict[str, set[str]]] = {}
    for group_id in world_.group_ids():
        group = world_.groups[group_id]
        if group.written:
            continue
        own = found.setdefault(group.main_code.language, {})
        for variable_id, variable in world_.variables.items():
            if variable.kind != "lexical":
                continue
            distribution = world_.distribution(group_id, variable_id)
            if distribution is not None:
                own.setdefault(variable_id, set()).add(distribution.dominant()[0])
    return found


def kept(world_, group_id: str, start: dict[str, set[str]]) -> tuple[list[bool], list[bool], list[bool], list[bool]]:
    """Zděděné slovo vlastního jazyka (jádro, rozšíření) a výpůjčka (jádro, rozšíření).

    Výpůjčka je slovo s morfémem jiného jazyka, ať je v dárci zděděné, nebo nové.
    """
    language = world_.groups[group_id].main_code.language
    core, extension, loans, cultural = [], [], [], []
    for variable_id, variable in world_.variables.items():
        if variable.kind != "lexical":
            continue
        distribution = world_.distribution(group_id, variable_id)
        if distribution is None:
            continue
        variant = world_.variants[distribution.dominant()[0]]
        own = variant.origin.change is None and variant.id in start.get(variable_id, ())
        morpheme = variant.payload.get("morpheme")
        foreign = morpheme is not None and world_.morphemes[str(morpheme)].language != language
        concept = variable.key.split(":", 1)[-1]
        (core if concept in SWADESH_CORE else extension).append(own)
        (loans if concept in SWADESH_CORE else cultural).append(foreign)
    return core, extension, loans, cultural


def run(job: tuple[int, float, float, str, bool, tuple[tuple[str, float], ...]]) -> dict:
    seed, scale, population, background, contact, overrides = job
    w, events = world(seed, scale, population, background, contact, overrides)
    start = inherited(w)
    simulation = Simulation(w, events=events)
    out = {"seed": seed, "scale": scale, "population": population, "background": background,
           "contact": contact, "set": " ".join(f"{name}={value:g}" for name, value in overrides)}
    for year in YEARS:
        simulation.run(float(year))
        core, extension, loans, cultural = [], [], [], []
        for group_id in w.group_ids():
            group = w.groups[group_id]
            # Cizí elity (``kraj+dobyvatel``) nejsou mluvčí místního jazyka.
            if group.written or group.domain != "home" or "+" in group_id:
                continue
            c, e, b, k = kept(w, group_id, start.get(group.main_code.language, {}))
            core += c
            extension += e
            loans += b
            cultural += k
        out[year] = (sum(core) / len(core), sum(extension) / len(extension), sum(loans) / len(loans),
                     sum(cultural) / len(cultural))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scales", type=float, nargs="+", default=[1.0])
    parser.add_argument("--populations", type=float, nargs="+", default=[500.0])
    parser.add_argument("--backgrounds", nargs="+", default=["none"])
    parser.add_argument("--contact", action="store_true", help="druhý jazyk v polovině krajů")
    parser.add_argument("--set", nargs="+", default=[""], metavar="NÁZEV=HODNOTA[,NÁZEV=HODNOTA]",
                        help="varianty přepisů číselných polí Parameters, každá zvlášť")
    parser.add_argument("--seeds", default="1-8")
    # Jeden běh potřebuje asi 1,5 GB paměti; víc procesů na 16 GB stroji vede do swapu.
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    first, last = (int(x) for x in args.seeds.split("-"))
    variants = [tuple((name, float(value)) for name, value in (item.split("=") for item in option.split(",") if item))
                for option in args.set]
    jobs = [(seed, scale, population, background, args.contact, overrides) for scale in args.scales
            for population in args.populations for background in args.backgrounds for overrides in variants
            for seed in range(first, last + 1)]
    with multiprocessing.get_context("spawn").Pool(args.workers) as pool:
        results = pool.map(run, jobs)
    for key in sorted({(r["scale"], r["population"], r["background"], r["set"]) for r in results}):
        rows = [r for r in results if (r["scale"], r["population"], r["background"], r["set"]) == key]
        scale, population, background, overrides = key
        line = [f"škála {scale:<4} populace {population:<5.0f} pozadí {background:<9} {overrides}"]
        for year in YEARS:
            core = statistics.mean(r[year][0] for r in rows)
            ext = statistics.mean(r[year][1] for r in rows)
            loans = statistics.mean(r[year][2] for r in rows)
            cultural = statistics.mean(r[year][3] for r in rows)
            line.append(f"{year}: jádro {core:.3f} ({core ** (1000 / year):.3f}/tis.) rozšíření {ext:.3f}"
                        f" výpůjčky {loans:.3f}/{cultural:.3f}")
        print(" | ".join(line), flush=True)
    print(json.dumps(results))


if __name__ == "__main__":
    main()
