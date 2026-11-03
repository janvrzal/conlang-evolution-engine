"""Podíl fází kroku na čase běhu (krok A5): inovace, morfologie, syntax, prozódie, sledování slovní zásoby.

Změří (``perf_counter``, bez ``cProfile``, aby režie profilátoru čas nezkreslila)
vnořené časy fází jednoho běhu scénáře z ``scripts/v2_digests.py``. Časy jsou
*včetně* podřízených volání; fáze se proto nesčítají. Zvlášť vypíše čas ve
čistých funkcích nad poli (``cee.v2.phases``, tedy v tom, co přepíše Rust)
a zbytek fáze, tedy obal z objektů.

Použití:  python scripts/v2_profile_phases.py grid-5x5|valley-50 [roky]
Rust z B2: PYTHONPATH=src:.:../CEE-rust-b2/rust/cee_core/target/py
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict
from collections.abc import Callable
from functools import wraps
from importlib import import_module
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cee.v2 import contact, morphology, native, phases, phonology, prosody, syntax  # noqa: E402
from cee.v2 import simulation as simulation_module  # noqa: E402
from cee.v2.changes import DEFAULT_CHANGES  # noqa: E402
from cee.v2.simulation import Simulation  # noqa: E402

digest_worlds = import_module("v2_digests").worlds

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


def install() -> None:
    for owner, names, prefix in (
        (Simulation, ("step", "_innovate", "_apply_innovations", "_transmit", "_changes", "_follow_vocabulary",
                      "_activations", "_trace", "_observe"), "Simulation."),
        (morphology, ("restructure", "analogy_plan"), "morphology."),
        (syntax, ("restructure", "ready_constructions"), "syntax."),
        (prosody, ("restructure", "plan"), "prosody."),
        (phonology, ("restructure",), "phonology."),
        (contact, ("community_step",), "contact."),
        (simulation_module, ("transmit", "prepare"), "transmission."),
    ):
        for name in names:
            setattr(owner, name, timed(prefix + name, getattr(owner, name)))
    for change in DEFAULT_CHANGES:
        change.total_rate = timed(f"changes.total_rate:{change.kind}", change.total_rate)  # type: ignore[method-assign]
        change.weighted_sites = timed("changes.weighted_sites", change.weighted_sites)  # type: ignore[method-assign]
    # Čisté funkce nad poli; vnitřní volání (site_weights → rate_total) se počítají obě, proto zvlášť součet jen vnějších.
    for name in dir(phases):
        function = getattr(phases, name)
        if callable(function) and getattr(function, "__module__", "") == phases.__name__ and not name.startswith("_"):
            setattr(phases, name, timed("phases." + name, function))
    simulation_module.hash_poisson = timed("phases.hash_poisson", simulation_module.hash_poisson)


def main() -> None:
    name = sys.argv[1]
    for scenario, build, years in digest_worlds(False):
        if scenario == name:
            break
    else:
        raise SystemExit(f"Neznámý scénář {name}.")
    if len(sys.argv) > 2:
        years = int(sys.argv[2])
    world, events = build()
    simulation = Simulation(world, events=events)
    install()
    started = time.perf_counter()
    simulation.run(years)
    total = time.perf_counter() - started
    print(f"{name}, {years} let, jádro: {native.status()}, celkem {total:.1f} s")
    print(f"{'fáze (včetně podřízených volání)':45s} {'s':>7s} {'%':>6s} {'volání':>9s}")
    groups = (
        ("inovace", ("Simulation._innovate",)),
        ("  z toho total_rate míst", tuple(key for key in list(SECONDS) if key.startswith("changes.total_rate:"))),
        ("  z toho weighted_sites", ("changes.weighted_sites",)),
        ("  z toho _apply_innovations", ("Simulation._apply_innovations",)),
        ("přenos celkem (_transmit)", ("Simulation._transmit",)),
        ("  transmission.transmit + prepare", ("transmission.transmit", "transmission.prepare")),
        ("  _changes (milníky)", ("Simulation._changes",)),
        ("  _follow_vocabulary", ("Simulation._follow_vocabulary",)),
        ("  _activations", ("Simulation._activations",)),
        ("  _trace", ("Simulation._trace",)),
        ("  phonology.restructure (B2)", ("phonology.restructure",)),
        ("  morphology.restructure + analogy_plan", ("morphology.restructure", "morphology.analogy_plan")),
        ("  syntax.restructure + ready_constructions", ("syntax.restructure", "syntax.ready_constructions")),
        ("  prosody.restructure + plan", ("prosody.restructure", "prosody.plan")),
        ("contact.community_step", ("contact.community_step",)),
        ("Simulation._observe", ("Simulation._observe",)),
    )
    for label, keys in groups:
        seconds = sum(SECONDS[key] for key in keys)
        print(f"{label:45s} {seconds:7.2f} {100 * seconds / total:6.1f} {sum(CALLS[key] for key in keys):9d}")
    print("\ntotal_rate míst podle změny (nejdražší)")
    kinds = sorted((key for key in SECONDS if key.startswith("changes.total_rate:")), key=lambda key: -SECONDS[key])
    for key in kinds[:8]:
        print(f"{key.split(':', 1)[1]:45s} {SECONDS[key]:7.2f} {100 * SECONDS[key] / total:6.1f} {CALLS[key]:9d}")
    pure = sorted((key for key in SECONDS if key.startswith("phases.")), key=lambda key: -SECONDS[key])
    print("\nčisté funkce nad poli (cee.v2.phases; vnořená volání se počítají dvakrát)")
    for key in pure:
        print(f"{key:45s} {SECONDS[key]:7.3f} {100 * SECONDS[key] / total:6.2f} {CALLS[key]:9d}")


if __name__ == "__main__":
    main()
