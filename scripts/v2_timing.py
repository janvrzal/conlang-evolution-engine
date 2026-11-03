"""Stopkami měří fáze a horké body enginu v2, včetně otisku historie.

Použití: ``python scripts/v2_timing.py --scenario valley-50``.
Měření jsou inkluzivní: například časy tlaků jsou součástí času přenosu.
"""

from __future__ import annotations

import argparse
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable, Iterator

import cee.v2.assessment as assessment_module
import cee.v2.pressures.lexical as lexical_pressure_module
import cee.v2.pressures.linguistic as linguistic_pressure_module
import cee.v2.pressures.morphological as morphological_pressure_module
import cee.v2.simulation as simulation_module
from cee.v2 import phonology
from cee.v2.simulation import Simulation

if __package__:
    digest_worlds = import_module("scripts.v2_digests").worlds
else:
    # Při spuštění souboru je adresář scripts první položkou v sys.path.
    digest_worlds = import_module("v2_digests").worlds


@dataclass
class Timing:
    """Součty stopkami měřených volání."""

    calls: dict[str, int]
    seconds: dict[str, float]

    @classmethod
    def create(cls) -> Timing:
        return cls(defaultdict(int), defaultdict(float))

    def add(self, key: str, elapsed: float) -> None:
        self.calls[key] += 1
        self.seconds[key] += elapsed


def timed_wrapper(label: str, timing: Timing, original: Callable[..., Any]) -> Callable[..., Any]:
    """Vytvoří transparentní obal; změří i volání končící výjimkou."""

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            timing.add(label, time.perf_counter() - started)

    wrapped.__name__ = getattr(original, "__name__", "timed")
    wrapped.__doc__ = getattr(original, "__doc__", None)
    return wrapped


@contextmanager
def patched(owner: Any, name: str, replacement: Any) -> Iterator[None]:
    """Dočasně vymění atribut a zachová původní způsob jeho vyhledání."""
    namespace = getattr(owner, "__dict__", {})
    had_local = name in namespace
    original = namespace[name] if had_local else getattr(owner, name)
    setattr(owner, name, replacement)
    try:
        yield
    finally:
        if had_local:
            setattr(owner, name, original)
        else:
            delattr(owner, name)


@contextmanager
def instrument(
    simulation: Simulation, timing: Timing, *, include_helpers: bool = False
) -> Iterator[None]:
    """Dočasně obalí měřené funkce a vždy obnoví původní atributy."""
    patches: list[Any] = []

    def patch(owner: Any, name: str, label: str) -> None:
        manager = patched(owner, name, timed_wrapper(label, timing, getattr(owner, name)))
        manager.__enter__()
        patches.append(manager)
    try:
        for phase in ("_innovate", "_transmit"):
            patch(simulation, phase, f"phase.{phase[1:]}")
        # Každou konkrétní třídu obalíme zvlášť, i když metodu dědí.
        for change_type in {type(change) for change in simulation.changes}:
            patch(change_type, "sites", f"change.sites.{change_type.kind}")
        # Tlak měříme jednou na každé konkrétní třídě, i pro zděděné scores().
        pressure_types = {
            type(pressure)
            for weighted in simulation.pressures.values()
            for pressure, _ in weighted
        }
        for pressure_type in pressure_types:
            patch(pressure_type, "scores", f"pressure.{pressure_type.__name__}")
        patch(phonology, "restructure", "phonology.restructure")
        patch(simulation_module, "observe", "observe.observe")
        if include_helpers:
            patch(assessment_module, "_assess_batch", "assessment._assess_batch")
            patch(linguistic_pressure_module, "_process_scores", "pressure.linguistic._process_scores")
            patch(morphological_pressure_module, "_form_scores", "pressure.morphological._form_scores")
            patch(lexical_pressure_module, "_clarity_scores", "pressure.lexical._clarity_scores")
            for change_type in {type(change) for change in simulation.changes}:
                if hasattr(change_type, "total_rate"):
                    patch(change_type, "total_rate", f"change.total_rate.{change_type.kind}")
        yield
    finally:
        for manager in reversed(patches):
            manager.__exit__(None, None, None)


def worlds(quick: bool = False) -> dict[str, tuple[Callable[[], tuple[Any, tuple[Any, ...]]], int]]:
    """Scénáře a roky bere přímo z digest skriptu."""
    return {name: (build, years) for name, build, years in digest_worlds(quick)}


def measure(name: str, build: Callable[[], tuple[Any, tuple[Any, ...]]], years: int,
            warmup: bool = False, include_helpers: bool = False) -> None:
    if warmup:
        world, events = build()
        Simulation(world, events=events).run(years)
    world, events = build()
    simulation = Simulation(world, events=events)
    timing = Timing.create()
    started = time.perf_counter()
    with instrument(simulation, timing, include_helpers=include_helpers):
        simulation.run(years)
    elapsed = time.perf_counter() - started
    print(f"{name}: total {elapsed:.3f} s; digest {simulation.history.digest()}")
    for key in sorted(timing.seconds):
        print(f"  {key:32s} {timing.seconds[key]:9.3f} s  {timing.calls[key]:7d} volání")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=worlds(), action="append",
                        help="scénář; lze zadat opakovaně, výchozí jsou všechny")
    parser.add_argument("--quick", action="store_true",
                        help="použije stejnou zkrácenou sadu jako scripts/v2_digests.py")
    parser.add_argument("--years", type=int,
                        help="přepíše počet let běhu pro každý vybraný scénář")
    parser.add_argument("--warmup", action="store_true",
                        help="před měřením provede jeden nezapočítaný běh")
    parser.add_argument("--helpers", action="store_true",
                        help="navíc měří assessment a helpery tří tlaků (inkluzivně)")
    args = parser.parse_args()
    scenario_set = worlds(args.quick)
    selected = args.scenario or list(scenario_set)
    for name in selected:
        if name not in scenario_set:
            parser.error(f"scénář {name!r} není dostupný v této sadě")
        build, years = worlds(False)[name]
        measure(name, build, args.years if args.years is not None else years,
                args.warmup, args.helpers)


if __name__ == "__main__":
    main()
