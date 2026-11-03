"""Profil přenosu (krok A5, zbytek): příprava, míšení, kontakt, instituce, tlaky, drift a převody slotů.

Změří vnořené časy (``perf_counter``, bez ``cProfile``) částí ``transmission.prepare``,
``transmission.transmit`` a následného zpracování v ``Simulation._transmit``. Časy
jsou *včetně* podřízených volání, takže se vnořené řádky nesčítají. Vypíše také
špičku paměti procesu a velikost a zaplnění živých fondů na konci běhu.

Použití:  python scripts/v2_profile_transmission.py [--plain] valley-50|grid-5x5|grid-COLSxROWS [roky]
          (--plain bez měření částí, jen celkový čas, paměť, otisk a fondy)
Rust:     PYTHONPATH=src:.:rust/cee_core/target/py
"""

from __future__ import annotations

import resource
import sys
import time
from collections import defaultdict
from collections.abc import Callable
from functools import wraps
from importlib import import_module
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cee.v2 import contact, institutions, native, phases_transmission  # noqa: E402
from cee.v2 import pools as pools_module  # noqa: E402
from cee.v2 import simulation as simulation_module  # noqa: E402
from cee.v2 import transmission as transmission_module  # noqa: E402
from cee.v2.pressures import base as pressure_base  # noqa: E402
from cee.v2.scenarios import village_grid  # noqa: E402
from cee.v2.simulation import Simulation  # noqa: E402

SECONDS: dict[str, float] = defaultdict(float)
CALLS: dict[str, int] = defaultdict(int)


def timed(name: str, function: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            SECONDS[name] += time.perf_counter() - started
            CALLS[name] += 1
    return wrapper


def patch(owner: Any, names: tuple[str, ...], prefix: str) -> None:
    for name in names:
        if hasattr(owner, name):
            setattr(owner, name, timed(prefix + name, getattr(owner, name)))


def install() -> None:
    patch(Simulation, ("_transmit", "_plan", "_changes", "_crossings", "_follow_vocabulary", "_activations",
                       "_trace_cells", "_trace", "_observe", "_innovate"), "Simulation.")
    patch(simulation_module, ("prepare", "transmit"), "Simulation.")
    patch(transmission_module, ("mixing_matrix", "fitness_of", "_channels"), "transmission.")
    # Čisté funkce polí (po dělení přenosu); ``mix`` a ``normalized`` se volají i uvnitř ``hear`` a ``settle``.
    patch(phases_transmission, ("mixing_from_links", "components", "mix", "hear", "settle", "normalized"), "arrays.")
    patch(pools_module.PoolBlock, ("set_state", "stage_state", "commit_state", "_dense_arrays", "add_share"), "pools.")
    patch(pools_module.LivePools, ("get", "dominant", "frequency", "innovate", "release", "load"), "pools.")
    patch(contact, ("channel_shares", "distinct_channels", "borrowing_factor", "interference_factor"), "contact.")
    patch(institutions, ("reading_factor", "school_factor", "liturgy_factor"), "institutions.")
    patch(pressure_base.PressureBatch, ("slot_numbers", "slot_column", "slot_values", "payload"), "batch.")
    patch(pressure_base.PressureBatch, ("__init__",), "batch.")
    for pressure in _subclasses(pressure_base.Pressure):
        if "scores" in vars(pressure):
            pressure.scores = timed(f"pressure.{pressure.__name__}", pressure.scores)  # type: ignore[method-assign]


def _subclasses(cls: type) -> list[type]:
    found = []
    for sub in cls.__subclasses__():
        found.append(sub)
        found.extend(_subclasses(sub))
    return found


def pool_stats(simulation: Simulation) -> dict[str, float]:
    """Velikost živých fondů: buňky husté a se skutečným výskytem, paměť řídkého a hustého uložení."""
    live = simulation.world.live
    if hasattr(live, "stats"):
        stats = live.stats()
        return {"variables": stats["variables"], "groups": stats["groups"], "dense_cells": stats["dense_cells"],
                "occupied": stats["entries"], "dense_MB": stats["dense_bytes"] / 1e6,
                "sparse_MB": stats["sparse_bytes"] / 1e6}
    cells = occupied = nbytes = rows = 0
    for block in live.iter_blocks():
        rows += len(block)
        cells += block.freqs.size
        occupied += int(((block.freqs > 0) | (block.previous != 0)).sum())
        nbytes += block.freqs.nbytes + block.previous.nbytes + block.present.nbytes + block.slot_keys.nbytes
    return {"variables": rows, "groups": len(live.group_ids), "dense_cells": cells, "occupied": occupied,
            "dense_MB": nbytes / 1e6, "sparse_MB": float("nan")}


def main() -> None:
    plain = "--plain" in sys.argv
    sys.argv = [argument for argument in sys.argv if argument != "--plain"]
    name = sys.argv[1]
    digest_worlds = import_module("v2_digests").worlds
    known = {scenario: (build, years) for scenario, build, years in digest_worlds(False)}
    if name in known:
        build, years = known[name]
    elif name.startswith("grid-") and "x" in name:
        columns, rows = (int(part) for part in name[5:].split("x"))
        years = 1000

        def build() -> Any:
            return village_grid(columns, rows, seed=1, syntax=True, semantics=True), ()
    else:
        raise SystemExit(f"Neznámý scénář {name}.")
    if len(sys.argv) > 2:
        years = int(sys.argv[2])
    world, events = build()
    simulation = Simulation(world, events=events)
    if not plain:
        install()
    started, cpu_started = time.perf_counter(), time.process_time()
    simulation.run(years)
    total, cpu = time.perf_counter() - started, time.process_time() - cpu_started
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6  # macOS: bajty
    print(f"{name}, {years} let, jádro: {native.status()}, celkem {total:.1f} s (procesor {cpu:.1f} s), špička paměti {peak:.0f} MB, "
          f"otisk {simulation.history.digest()[:16]}")
    if plain:
        print("fondy: " + ", ".join(f"{key} {value:.4g}" for key, value in pool_stats(simulation).items()))
        return
    print(f"{'část (včetně podřízených volání)':50s} {'s':>7s} {'%':>6s} {'volání':>9s}")
    groups = (
        ("přenos celkem (_transmit)", ("Simulation._transmit",)),
        ("  prepare (matice vazeb, komponenty, kanály)", ("Simulation.prepare",)),
        ("    mixing_from_links", ("arrays.mixing_from_links",)),
        ("    components", ("arrays.components",)),
        ("    kanály elity a obchodu (channel_shares)", ("contact.channel_shares", "contact.distinct_channels")),
        ("  transmit (blok po bloku)", ("Simulation.transmit",)),
        ("    hear (míšení, kontakt, kanály)", ("arrays.hear",)),
        ("      z toho mix", ("arrays.mix",)),
        ("      filtr kontaktu (borrowing_factor, po jedné)", ("contact.borrowing_factor",)),
        ("      instituce (čtení, škola, liturgie, po jedné)",
         ("institutions.reading_factor", "institutions.school_factor", "institutions.liturgy_factor")),
        ("    tlaky (fitness_of)", ("transmission.fitness_of",)),
        ("      PressureBatch (slot_numbers, column, values, payload)",
         ("batch.__init__", "batch.slot_numbers", "batch.slot_column", "batch.slot_values", "batch.payload")),
        ("    settle (výběr, trend, drift, ustálení)", ("arrays.settle",)),
        ("      z toho normalized", ("arrays.normalized",)),
        ("  _plan (události z polí + řídký zápis stavu)", ("Simulation._plan",)),
        ("    z toho _changes (milníky, převod slotů)", ("Simulation._changes",)),
        ("    z toho stage_state (hustý -> řídký)", ("pools.stage_state",)),
        ("  commit_state", ("pools.commit_state",)),
        ("  _follow_vocabulary", ("Simulation._follow_vocabulary",)),
        ("  fondy: release", ("pools.release",)),
        ("fondy: innovate (add_share)", ("pools.innovate",)),
        ("fondy: get + dominant + frequency", ("pools.get", "pools.dominant", "pools.frequency")),
        ("fondy: hustý pohled z řídkého (_dense_arrays)", ("pools._dense_arrays",)),
        ("Simulation._innovate", ("Simulation._innovate",)),
        ("Simulation._observe", ("Simulation._observe",)),
    )
    for label, keys in groups:
        seconds = sum(SECONDS[key] for key in keys)
        print(f"{label:50s} {seconds:7.2f} {100 * seconds / total:6.1f} {sum(CALLS[key] for key in keys):9d}")
    print("\ntlaky podle třídy (včetně volaných pomocných funkcí)")
    for key in sorted((key for key in SECONDS if key.startswith("pressure.")), key=lambda key: -SECONDS[key]):
        print(f"  {key:48s} {SECONDS[key]:7.2f} {100 * SECONDS[key] / total:6.1f} {CALLS[key]:9d}")
    stats = pool_stats(simulation)
    print("\nfondy na konci: " + ", ".join(f"{key} {value:.4g}" for key, value in stats.items()))
    print(f"zaplnění buněk: {100 * stats['occupied'] / max(1, stats['dense_cells']):.1f} % "
          f"(buňky skupina × slot s výskytem proti přiděleným)")


if __name__ == "__main__":
    main()
