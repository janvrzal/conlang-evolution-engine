"""Zlatá data pozorování (``cee.v2.observe``): rysy skupin, kandidáti, dialekty, jazyky, vzdálenosti, tvary.

Ze skutečných běhů (grid-5x5, shift, valley-50 zkráceně, svět s elitou a obchodem, svět s církví,
písmem a školou a dva malé světy pro vzácné cesty) zaznamená v pár tickách každého scénáře vstupy
a výstupy pozorování; viz ``tests/v2/golden_observe.py`` (obsah záznamu ticku). Ticky vybírá
deterministicky ``rng.Stream``. Záznam pořizuje Python reference (``CEE_NATIVE=0``), Rust ho ověřuje
v ``test_v2_golden_observe.py`` bit po bitu.

**Vstup.** Stav světa v ticku (stav na začátku inovační fáze) a dosavadní linie skupin
(``LineageTracker``, který se mezi zaznamenanými ticky téhož scénáře předává). Snímek světa
(pickle checkpointu) má 1 až 3 MB, a nevejde se tedy do limitu 1 MB na soubor, proto se stav vyrobí
během scénáře (``tests/v2/golden_worlds.py``, bitově shodný s otisky ``scripts/v2_digests.py``).

Soubor ``tests/v2/data/golden_observe.json.gz`` je při opakovaném běhu bajt po bajtu stejný.

Použití:  python scripts/v2_golden_observe.py [--output-dir tests/v2/data] [--scenarios ...]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

os.environ["CEE_NATIVE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cee.v2.observe import LineageTracker  # noqa: E402
from cee.v2.simulation import Simulation  # noqa: E402
from tests.v2 import golden_observe as observed  # noqa: E402
from tests.v2 import golden_worlds as worlds  # noqa: E402

#: Kolik ticků vzorku má každý scénář.
SAMPLE_TICKS = {"grid-5x5": 4, "shift": 4, "valley-50": 3, "trade-elite": 3, "church-school": 3,
                "rare-grammar": 3, "rare-sounds": 3}


def record(name: str) -> dict[str, Any]:
    simulation, ticks = worlds.new_simulation(name)
    chosen = set(worlds.sample_ticks(name, ticks, SAMPLE_TICKS[name], "observe"))
    trackers = [LineageTracker() for _ in observed.THRESHOLDS]
    records: list[dict[str, Any]] = []

    def probe(running: Simulation) -> None:
        if running.tick in chosen:
            records.append(observed.record_tick(running, name, trackers, False))

    with worlds.probing_innovation(simulation, probe):
        simulation.run(simulation.world.start_year + ticks * worlds.DT)
    return {"ticks": ticks, "records": records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="tests/v2/data")
    parser.add_argument("--scenarios", nargs="*", default=list(worlds.SCENARIOS), help="jen tyto scénáře (zkouška)")
    args = parser.parse_args()
    scenarios: dict[str, Any] = {}
    for name in args.scenarios:
        scenarios[name] = record(name)
        print(f"{name}: {scenarios[name]['ticks']} ticků, {len(scenarios[name]['records'])} záznamů", flush=True)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "golden_observe.json.gz"
    worlds.write_gzip(path, {"scenarios": scenarios})
    print(f"{path}: {path.stat().st_size / 1024:.0f} kB")


if __name__ == "__main__":
    main()
