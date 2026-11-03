"""Porovnání světa v ticku 0: Python engine v2 proti Rustu (``cee export-tick0``).

Pro scénáře z ``scripts/v2_digests.py`` (a ostatní scénáře ``scenarios.py``) postaví svět
v Pythonu, vyexportuje ho v ticku 0 (``export.export``) a porovná s exportem binárky
``cee export-tick0 <scénář>``: území, skupiny, vazby, slovní zásoba (tvary, původ),
gramatika a zbytek dokumentu. Desetinná čísla se porovnávají s tolerancí 1e-12.

Souběžná variabilita slovní zásoby (``variation.seed``) není v Rustu v R0, proto se
Python staví s ``standing_variation = 0``. Export ticku 0 jí stejně není dotčený (slova
autora zůstávají převládající); ``--with-variation`` to ověří s výchozími parametry.

Použití:  PYTHONPATH=src python scripts/v2_compare_tick0.py [--binary rust/target/debug/cee] [scénář ...]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from cee.v2 import export
from cee.v2.parameters import Parameters
from cee.v2.scenarios import (
    conquest, conversion, diglossia, island_and_city, kingdom, known_tree, language_shift, market_town,
    migration_region, village_grid,
)
from cee.v2.simulation import Simulation


def scenarios(variation: bool = False) -> dict[str, Any]:
    p = Parameters() if variation else Parameters(standing_variation=0.0)
    none = lambda world: (world, ())  # noqa: E731
    return {
        "phonology": lambda: none(village_grid(4, seed=2, phonology=True, params=p)),
        "morphology": lambda: none(village_grid(4, seed=2, morphology=True, semantics=True, params=p)),
        "syntax": lambda: none(village_grid(4, seed=2, syntax=True, semantics=True, params=p)),
        "grid-5x5": lambda: none(village_grid(5, 5, seed=2, morphology=True, semantics=True, params=p)),
        "valley-50": lambda: none(village_grid(10, 5, seed=1, syntax=True, semantics=True, params=p)),
        "shift": lambda: _with(language_shift(2, start=300.0), p),
        "island-city": lambda: none(_params(island_and_city(2), p)),
        "diglossia": lambda: diglossia(1),
        "conquest": lambda: conquest(1),
        "market": lambda: market_town(1),
        "migration": lambda: none(migration_region(1)),
        "conversion": lambda: conversion(1),
        "tree": lambda: known_tree(1),
        "kingdom": lambda: kingdom(1),
    }


def _params(world, p):
    object.__setattr__(world, "params", p)
    return world


def _with(pair, p):
    world, events = pair
    return _params(world, p), events


def differences(left: Any, right: Any, path: str = "", out: list[str] | None = None) -> list[str]:
    out = [] if out is None else out
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                out.append(f"{path}/{key}: {'chybí v Pythonu' if key not in left else 'chybí v Rustu'}")
            else:
                differences(left[key], right[key], f"{path}/{key}", out)
    elif isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            out.append(f"{path}: délka {len(left)} vs {len(right)}")
        for index, (a, b) in enumerate(zip(left, right)):
            differences(a, b, f"{path}[{index}]", out)
    elif isinstance(left, (int, float)) and isinstance(right, (int, float)) and not isinstance(left, bool):
        if abs(left - right) > 1e-12 * max(1.0, abs(left), abs(right)):
            out.append(f"{path}: {left!r} vs {right!r}")
    elif left != right:
        out.append(f"{path}: {left!r} vs {right!r}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", default="rust/target/debug/cee")
    parser.add_argument("--with-variation", action="store_true",
                        help="Python s výchozí souběžnou variabilitou (export ticku 0 by se neměl změnit)")
    parser.add_argument("names", nargs="*")
    args = parser.parse_args()
    table = scenarios(args.with_variation)
    failed = 0
    for name in args.names or list(table):
        if name.endswith(".json"):  # popis světa (WorldSpec)
            from cee.v2.spec import build

            world, events, _ = build(json.loads(Path(name).read_text(encoding="utf-8")))
        else:
            world, events = table[name]()
        python = json.loads(json.dumps(export.export(Simulation(world, events=events)), sort_keys=True))
        run = subprocess.run([args.binary, "export-tick0", name], capture_output=True, text=True)
        if run.returncode != 0:
            print(f"{name:12s} Rust selhal: {run.stderr.strip()[:200]}")
            failed += 1
            continue
        rust = json.loads(run.stdout)
        found = differences(python, rust)
        # události scénářů Python exportuje do ``events`` jen po provedení; v ticku 0 jsou prázdné.
        sections = sorted({line.split("/")[1].split("[")[0].split(":")[0] for line in found})
        print(f"{name:12s} {'shoda' if not found else f'{len(found)} rozdílů v {sections}'}")
        for line in found[:8]:
            print(f"    {line}")
        failed += bool(found)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
