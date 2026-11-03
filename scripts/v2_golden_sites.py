"""Zlatá data hledání míst inovací (``Change.sites``, ``rates``, ``total_rate``, ``weighted_sites``).

Pro každý druh změny z ``DEFAULT_CHANGES`` zaznamená ze skutečných běhů (grid-5x5, shift,
valley-50 zkráceně, svět s elitou a obchodem, svět s církví, písmem a školou a dva malé světy
pro vzácné cesty) výsledek hledání míst ve skupině na začátku inovační fáze ticku. Tik a skupiny
vzorku vybírá deterministicky ``rng.Stream``; vedle vzorku (všechny druhy změn ve vybraných
skupinách) se přidají záznamy, které doplní pokrytí: druh změny, který vzorek nezastihl, dostane
první nalezený stav, kde má místa a nenulovou míru.

Soubor ``tests/v2/data/golden_sites.json.gz``:

- ``strings``: tabulka řetězců míst (ID proměnných); místa v záznamech jsou čísla do ní;
- ``scenarios``: pro každý scénář počet ticků a ``entries``. Záznam je (``tick``, ``group``,
  ``kind``) a výsledek: ``sites`` (seřazená místa), ``rates`` (míry po místech) nebo u druhů
  s jednotnou mírou ``rate`` a ``rate_scale``, ``total_rate``, ``weighted`` (``same``: místa
  pro ``weighted_sites`` jsou ``sites``, ``empty``: žádná) a ``weights`` (normalizované váhy
  nebo ``None`` u jednotné míry). Čísla jsou ``float64`` zapsaná tak, že se čtou zpět na stejný bit.

**Vstup.** Stav světa na začátku ``Simulation._innovate`` v daném ticku (po událostech) a skupina
(její hlavní kód). Snímek světa (pickle checkpointu) má 1 až 3 MB, a nevejde se tedy do limitu
1 MB na soubor, proto se stav vyrobí během scénáře (``tests/v2/golden_worlds.py``, bitově shodný
s otisky ``scripts/v2_digests.py``) až do ticku záznamu. Test ``test_v2_golden_sites.py`` běh
zopakuje, spočte totéž a porovná bit po bitu. S ``--snapshots ADRESÁŘ`` skript navíc uloží pickle
světa v tickách záznamů (pro ladění Rustu; do repozitáře nepatří).

Záznam je výřez a vzniká pokaždé stejný (bez náhody, bajt po bajtu).

Použití:  python scripts/v2_golden_sites.py [--output-dir tests/v2/data] [--snapshots DIR]
"""

from __future__ import annotations

import argparse
import os
import pickle
import sys
from pathlib import Path
from typing import Any

os.environ["CEE_NATIVE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cee.v2.changes import DEFAULT_CHANGES  # noqa: E402
from cee.v2.simulation import Simulation  # noqa: E402
from tests.v2 import golden_worlds as worlds  # noqa: E402

#: Kolik ticků vzorku má každý scénář, a kolik skupin v každém ticku (všechny druhy změn).
SAMPLE_TICKS = {"grid-5x5": 6, "shift": 6, "valley-50": 3, "trade-elite": 4, "church-school": 4,
                "rare-grammar": 3, "rare-sounds": 3}
SAMPLE_GROUPS = 3
#: Kolik skupin v každém ticku se prohledá kvůli doplnění pokrytí.
SCAN_GROUPS = 3


def record(name: str, strings: worlds.SiteStrings, covered: set[str], snapshots: Path | None) -> dict[str, Any]:
    simulation, ticks = worlds.new_simulation(name)
    chosen = set(worlds.sample_ticks(name, ticks, SAMPLE_TICKS[name]))
    entries: dict[tuple[int, str, str], dict[str, Any]] = {}

    def probe(running: Simulation) -> None:
        tick = running.tick
        ids = worlds.innovating_groups(running)
        sampled = tick in chosen
        scanned = worlds.sample_groups(name, tick, ids, SAMPLE_GROUPS if sampled else SCAN_GROUPS)
        if sampled:
            for group_id, context in worlds.inventory_contexts(running, scanned):
                for change in DEFAULT_CHANGES:
                    entry = worlds.site_entry(change, context, strings)
                    entries[(tick, group_id, change.kind)] = entry
                    if worlds.informative(entry):
                        covered.add(change.kind)
        else:
            for group_id, context in worlds.inventory_contexts(running, scanned):
                for change in DEFAULT_CHANGES:
                    if change.kind in covered or not change.sites(context):
                        continue
                    entry = worlds.site_entry(change, context, strings)
                    if worlds.informative(entry):
                        entries[(tick, group_id, change.kind)] = entry
                        covered.add(change.kind)
        if sampled and snapshots is not None:
            import copy
            path = snapshots / f"{name}-{tick:03d}.pickle"
            path.write_bytes(pickle.dumps(copy.deepcopy(running.world), protocol=5))

    with worlds.probing_innovation(simulation, probe):
        simulation.run(simulation.world.start_year + ticks * worlds.DT)
    order = {kind: index for index, kind in enumerate(worlds.KINDS)}
    listed = [{"tick": tick, "group": group_id, **entry}
              for (tick, group_id, _), entry in sorted(entries.items(), key=lambda item: (
                  item[0][0], item[0][1], order[item[0][2]]))]
    return {"ticks": ticks, "entries": listed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="tests/v2/data")
    parser.add_argument("--snapshots", default=None, help="adresář pro pickle světa v tickách záznamů (nepovinné)")
    parser.add_argument("--scenarios", nargs="*", default=list(worlds.SCENARIOS), help="jen tyto scénáře (zkouška)")
    args = parser.parse_args()
    snapshots = None if args.snapshots is None else Path(args.snapshots)
    if snapshots is not None:
        snapshots.mkdir(parents=True, exist_ok=True)
    strings = worlds.SiteStrings()
    covered: set[str] = set()
    scenarios: dict[str, Any] = {}
    for name in args.scenarios:
        scenarios[name] = record(name, strings, covered, snapshots)
        count = len(scenarios[name]["entries"])
        print(f"{name}: {scenarios[name]['ticks']} ticků, {count} záznamů, pokryto {len(covered)} druhů změn",
              flush=True)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "golden_sites.json.gz"
    worlds.write_gzip(path, {"strings": strings.table, "scenarios": scenarios})
    print(f"{path}: {path.stat().st_size / 1024:.0f} kB")
    missing = [change.kind for change in DEFAULT_CHANGES if change.kind not in covered]
    print("bez neprázdného záznamu:", ", ".join(missing) if missing else "žádný")


if __name__ == "__main__":
    main()
