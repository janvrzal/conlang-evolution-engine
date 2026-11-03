"""Kalibrace domén slov v mechanismech kontaktu proti WOLD (krok 3 plánu pojmů).

Tři pokusy, vždy na ``region_world`` ze šesti krajů 3 × 2 po třech vesnicích
(jako ``v2_calibrate_retention.py``). Výpůjčka je slovo domácí skupiny, jehož
převládající morfém patří jinému jazyku; cizí elity (``kraj+dobyvatel``) se
nepočítají. Slova se sčítají přes vesnice a seedy po pojmech.

``fields`` (kontaktní svět): dva jazyky, spodní řada mluví ``b``, volitelně
s pozadím dějin. Podíl přejatých slov po sémantických oblastech WOLD se
porovná s průměrnou půjčitelností oblasti ve WOLD (Haspelmath & Tadmor 2009,
``concept_data``; průměr významů doložených aspoň v 10 jazycích) pořadovou
korelací (Spearman). Oblasti mají s výchozím slovníkem 1 až 29 pojmů, proto
se bere jen oblast aspoň s ``--min-concepts`` pojmy a doporučuje se i
``--vocabulary 500`` (víc pojmů v každé oblasti). Tabulka domén a korelace
na úrovni pojmů jsou vedlejší.

``elite``: horní řada (``a``) dostane v roce 100 cizí elitu z řady ``b``
(``background.ForeignElite``), v roce 400 splyne s místními
(``EliteAssimilation``). Srovnává se s kontrolou bez elity: podíl pojmů
domény ``power`` mezi výpůjčkami z ``b`` a poměr šancí, že pojem ``power``
je přejatý, proti ostatním pojmům. Doporučený slovník ``--vocabulary 500``
(78 pojmů ``power``; výchozí jich má 8).

``liturgy``: tři vesnice kraje ``a`` v řadě a vzdálený kraj ``c`` s psaným
kódem (``Codification``); v roce 200 vesnice ``a`` přijmou liturgii v ``c``
(``ReligiousChange``). Totéž pro doménu ``religion`` (výchozí slovník má
2 takové pojmy, 500 jich má 5, 1000 jich má 19: doporučeno ``--vocabulary 1000``
nebo víc seedů).

Přepisy ``Parameters``: ``--set název=hodnota[,název=hodnota]`` (číselná
pole), ``--domains kanál.doména=váha[,…]`` (``Parameters.channel_domains``,
pokud existuje). Víc variant za ``--set``/``--domains`` se zadává odděleně;
každá varianta je zvláštní běh.

Použití::

    python scripts/v2_calibrate_domains.py fields --seeds 1-8 --years 1000 2000 3000
    python scripts/v2_calibrate_domains.py fields --vocabulary 500 --background normal
    python scripts/v2_calibrate_domains.py elite --vocabulary 500 --domains power.elite=1 ...
    python scripts/v2_calibrate_domains.py liturgy --vocabulary 1000

Skript s ``multiprocessing`` se spouští ze souboru (spawn); jeden běh potřebuje
asi 1,5 GB paměti, výchozí jsou 3 procesy.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
for entry in (REPO_ROOT / "src", REPO_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from cee.v2 import concept_data  # noqa: E402
from cee.v2 import vocabulary as vocab  # noqa: E402
from cee.v2.background import EliteAssimilation, ForeignElite, generate  # noqa: E402
from cee.v2.changes import LEXICAL_CHANGES  # noqa: E402
from cee.v2.events import Codification, ReligiousChange  # noqa: E402
from cee.v2.parameters import Parameters  # noqa: E402
from cee.v2.scenarios import ProtoLanguage, Region, region_world  # noqa: E402
from cee.v2.simulation import Simulation  # noqa: E402

ELITE_YEAR, ASSIMILATION_YEAR, LITURGY_YEAR = 100.0, 400.0, 200.0


def regions_for(scenario: str) -> tuple[Region, ...]:
    """Šest krajů 3 × 2 (dole jazyk ``b``); u liturgie tři kraje ``a`` a vzdálený ``c``."""
    if scenario == "liturgy":
        chain = tuple(Region(f"r{i}", (60.0 * i, 0.0), language="a", villages=3,
                             neighbours=tuple(f"r{j}" for j in (i - 1, i + 1) if 0 <= j < 3)) for i in range(3))
        return (*chain, Region("r3", (900.0, 0.0), language="c", villages=1))
    return tuple(
        Region(f"r{i}", (60.0 * (i % 3), 60.0 * (i // 3)), language="b" if i >= 3 else "a", villages=3,
               neighbours=tuple(f"r{j}" for j in range(6)
                                if j != i and abs(j % 3 - i % 3) + abs(j // 3 - i // 3) == 1))
        for i in range(6)
    )


def parameters(scale: float, overrides: dict[str, float], domains: dict[str, dict[str, float]]) -> Parameters:
    rates = {change.kind: scale for change in LEXICAL_CHANGES}
    extra: dict[str, Any] = dict(overrides)
    if domains:
        extra["channel_domains"] = domains
    return Parameters(change_rates=rates, **extra)


def build(job: dict[str, Any]):
    scenario, seed = job["scenario"], job["seed"]
    regions = regions_for(scenario)
    params = parameters(1.0, job["overrides"], job["domains"])
    languages = tuple(ProtoLanguage(name) for name in ("a", "b", "c") if any(r.language == name for r in regions))
    size = job["vocabulary"]
    world = region_world(regions, seed=seed, languages=languages, semantics=True, params=params,
                         vocabulary=None if size == vocab.DEFAULT_SIZE else vocab.resolve(size))
    end = float(max(job["years"]))
    events: list = []
    if scenario in ("fields", "elite"):
        events += generate([(r.id, r.neighbours, r.language) for r in regions], start=0.0, end=end,
                           level_name=job["background"], seed=seed, params=params)
    if scenario == "elite" and job["variant"] == "elite":
        for top, bottom in (("r0", "r3"), ("r1", "r4"), ("r2", "r5")):
            events.append(ForeignElite(ELITE_YEAR, bottom, top))
            events.append(EliteAssimilation(ASSIMILATION_YEAR, bottom, top))
    if scenario == "liturgy" and job["variant"] == "liturgy":
        events.append(Codification(100.0, "r3-v0", ("r3-v0",), 0.1))
        events.append(ReligiousChange(LITURGY_YEAR, "written:r3-v0", tuple(
            f"r{i}-v{j}" for i in range(3) for j in range(3)), 0.3))
    return world, events


def loans(world, *, foreign: str | None = None) -> dict[str, list[int]]:
    """Pojem → [počet vesnic s výpůjčkou, počet vesnic] pro domácí skupiny jazyka ``a``."""
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for group_id in world.group_ids():
        group = world.groups[group_id]
        if group.written or group.domain != "home" or "+" in group_id:
            continue
        if group.main_code.language != "a" and foreign is not None:
            continue
        language = group.main_code.language
        for variable_id, variable in world.variables.items():
            if variable.kind != "lexical":
                continue
            distribution = world.distribution(group_id, variable_id)
            if distribution is None:
                continue
            variant = world.variants[distribution.dominant()[0]]
            morpheme = variant.payload.get("morpheme")
            origin = None if morpheme is None else world.morphemes[str(morpheme)].language
            concept = variable.key.split(":", 1)[-1]
            entry = counts[concept]
            entry[1] += 1
            if origin is not None and origin != language and (foreign is None or origin == foreign):
                entry[0] += 1
    return dict(counts)


def run(job: dict[str, Any]) -> dict[str, Any]:
    world, events = build(job)
    simulation = Simulation(world, events=events)
    foreign = {"fields": None, "elite": "b", "liturgy": "c"}[job["scenario"]]
    out = {key: job[key] for key in ("scenario", "variant", "seed", "set", "vocabulary", "background")}
    out["loans"] = {}
    for year in job["years"]:
        simulation.run(float(year))
        out["loans"][str(year)] = loans(world, foreign=foreign)
    return out


# --- vyhodnocení ----------------------------------------------------------------


def ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    result = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for position in range(start, end + 1):
            result[order[position]] = (start + end) / 2.0
        start = end + 1
    return result


def spearman(first: Sequence[float], second: Sequence[float]) -> float:
    if len(first) < 3:
        return float("nan")
    a, b = ranks(first), ranks(second)
    mean_a, mean_b = sum(a) / len(a), sum(b) / len(b)
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    return cov / (var_a * var_b) ** 0.5 if var_a and var_b else float("nan")


def wold_field_means() -> dict[str, float]:
    """Průměrná půjčitelnost oblasti ve WOLD (významy aspoň v 10 jazycích), jako v ``19-pojmy.md``."""
    scores: dict[str, list[float]] = defaultdict(list)
    for item in concept_data.data()["catalog"]:
        if item["borrowed"] is not None and item["languages"] >= 10:
            scores[item["field"]].append(item["borrowed"])
    return {name: sum(values) / len(values) for name, values in scores.items()}


def merge(results: Sequence[dict[str, Any]], year: str) -> dict[str, list[int]]:
    total: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for result in results:
        for concept, (borrowed, count) in result["loans"][year].items():
            total[concept][0] += borrowed
            total[concept][1] += count
    return dict(total)


def by_field(total: dict[str, list[int]]) -> dict[str, tuple[int, int, int]]:
    """Oblast → (počet pojmů, přejatých slov, slov)."""
    found: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for concept, (borrowed, count) in total.items():
        info = concept_data.info(concept)
        if info is None or not count:
            continue
        entry = found[info["field"]]
        entry[0] += 1
        entry[1] += borrowed
        entry[2] += count
    return {name: (a, b, c) for name, (a, b, c) in found.items()}


def report_fields(results: Sequence[dict[str, Any]], year: str, minimum: int) -> dict[str, float]:
    total = merge(results, year)
    fields = by_field(total)
    wold = wold_field_means()
    rows = sorted(((name, n, loan / count, wold[name]) for name, (n, loan, count) in fields.items()
                   if n >= minimum and name in wold), key=lambda row: -row[3])
    print(f"\n### rok {year}: podíl přejatých slov po oblastech WOLD (oblasti aspoň s {minimum} pojmy)")
    print(f"{'oblast':<34}{'pojmů':>6}{'engine':>9}{'WOLD':>8}")
    for name, n, share, reference in rows:
        print(f"{name:<34}{n:>6}{share:>9.3f}{reference:>8.3f}")
    rho = spearman([row[2] for row in rows], [row[3] for row in rows])
    print(f"Spearman oblasti (engine × WOLD): {rho:.3f} (n = {len(rows)})")
    pairs = [(borrowed / count, info["borrowed"]) for concept, (borrowed, count) in total.items()
             if count and (info := concept_data.info(concept)) is not None and info["borrowed"] is not None]
    concept_rho = spearman([p[0] for p in pairs], [p[1] for p in pairs])
    print(f"Spearman pojmy (n = {len(pairs)}): {concept_rho:.3f}")
    domains: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for concept, (borrowed, count) in total.items():
        domains[concept_data.domain(concept)][0] += borrowed
        domains[concept_data.domain(concept)][1] += count
    parts = [f"{name} {loan / count:.3f}" for name, (loan, count) in sorted(domains.items()) if count]
    print("podíl přejatých slov po doménách: " + ", ".join(parts))
    overall = sum(v[0] for v in total.values()) / sum(v[1] for v in total.values())
    print(f"celkem přejato {overall:.3f}")
    return {"field_rho": rho, "concept_rho": concept_rho, "overall": overall}


def enrichment(results: Sequence[dict[str, Any]], year: str, domain: str) -> tuple[float, float, int]:
    """(podíl pojmů domény mezi výpůjčkami, šance pojmu domény proti ostatním, výpůjček)."""
    total = merge(results, year)
    inside = [0, 0]
    outside = [0, 0]
    for concept, (borrowed, count) in total.items():
        target = inside if concept_data.domain(concept) == domain else outside
        target[0] += borrowed
        target[1] += count
    loans_all = inside[0] + outside[0]
    share = inside[0] / loans_all if loans_all else float("nan")
    rate_in = inside[0] / inside[1] if inside[1] else float("nan")
    rate_out = outside[0] / outside[1] if outside[1] else float("nan")
    odds = (rate_in / (1 - rate_in)) / (rate_out / (1 - rate_out)) if 0 < rate_in < 1 and 0 < rate_out < 1 else float("nan")
    return share, odds, loans_all


def report_enrichment(scenario: str, domain: str, results: Sequence[dict[str, Any]], years: Sequence[int]) -> None:
    sets = sorted({(result["variant"], result["set"]) for result in results})
    print(f"\n### {scenario}: nadreprezentace domény {domain} mezi výpůjčkami z cizího jazyka")
    print(f"{'varianta':<10}{'nastavení':<44}{'rok':>6}{'podíl':>8}{'šance':>8}{'výpůjček':>10}")
    for variant, setting in sets:
        subset = [r for r in results if (r["variant"], r["set"]) == (variant, setting)]
        for year in years:
            share, odds, count = enrichment(subset, str(year), domain)
            print(f"{variant:<10}{setting[:43]:<44}{year:>6}{share:>8.3f}{odds:>8.2f}{count:>10}")
    inside = sum(1 for concept in merge(results[:1], str(years[-1])) if concept_data.domain(concept) == domain)
    print(f"(pojmů domény {domain} ve slovníku: {inside}; očekávaný podíl při náhodě = {inside}/{len(merge(results[:1], str(years[-1])))})")


def parse_set(option: str) -> dict[str, float]:
    return {name: float(value) for name, value in (item.split("=") for item in option.split(",") if item)}


def parse_domains(option: str) -> dict[str, dict[str, float]]:
    found: dict[str, dict[str, float]] = {}
    for item in (part for part in option.split(",") if part):
        key, value = item.split("=")
        channel, domain = key.split(".")
        found.setdefault(channel, {})[domain] = float(value)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", choices=("fields", "elite", "liturgy"))
    parser.add_argument("--seeds", default="1-8")
    parser.add_argument("--years", type=int, nargs="+", default=[1000, 2000, 3000])
    parser.add_argument("--vocabulary", type=int, default=vocab.DEFAULT_SIZE)
    parser.add_argument("--background", default="none", help="míra pozadí dějin (fields, elite)")
    parser.add_argument("--set", nargs="+", default=[""], metavar="NÁZEV=HODNOTA[,…]")
    parser.add_argument("--domains", nargs="+", default=[""], metavar="KANÁL.DOMÉNA=VÁHA[,…]")
    parser.add_argument("--min-concepts", type=int, default=3)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--output", default=None, help="soubor JSON s výsledky")
    args = parser.parse_args()
    first, last = (int(x) for x in args.seeds.split("-"))
    variants = ("none", "elite") if args.scenario == "elite" else ("none", "liturgy") if args.scenario == "liturgy" \
        else ("world",)
    jobs = []
    for overrides in args.set:
        for domains in args.domains:
            label = " ".join(part for part in (overrides, "d:" + domains if domains else "") if part)
            for variant in variants:
                for seed in range(first, last + 1):
                    jobs.append({
                        "scenario": args.scenario, "variant": variant, "seed": seed, "years": args.years,
                        "vocabulary": args.vocabulary, "background": args.background,
                        "overrides": parse_set(overrides), "domains": parse_domains(domains), "set": label,
                    })
    with multiprocessing.get_context("spawn").Pool(args.workers) as pool:
        results = pool.map(run, jobs, chunksize=1)
    if args.output:
        Path(args.output).write_text(json.dumps(results), encoding="utf-8")
    labels = sorted({result["set"] for result in results})
    if args.scenario == "fields":
        for label in labels:
            print(f"\n## nastavení: {label or '(výchozí)'}; slovník {args.vocabulary}, pozadí {args.background}")
            subset = [r for r in results if r["set"] == label]
            for year in args.years:
                report_fields(subset, str(year), args.min_concepts)
    else:
        domain = "power" if args.scenario == "elite" else "religion"
        report_enrichment(args.scenario, domain, results, args.years)


if __name__ == "__main__":
    main()
