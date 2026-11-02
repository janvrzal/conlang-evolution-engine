"""Zlatá data banky tvarů a procesů: záznam aplikací procesů ze skutečných běhů.

Za běhu scénářů (grid-5x5, shift, valley-50 zkráceně) zaznamená každou různou
aplikaci zvukového procesu na tvar: změnu (včetně masek hlásek), pravidlo
přízvuku, tvar a výsledek. Záznam slouží jako reference pro ověření Rustu
(``tests/v2/test_v2_native_bank.py``); běží vždy v Pythonu (``CEE_NATIVE=0``),
protože zaznamenává volání referenční implementace.

Použití:  python scripts/v2_golden_bank.py [--output tests/v2/data/golden_bank.json.gz] [--limit 40000]

Záznam je výřez: změny se berou všechny, tvarů se vzorkuje pevnou funkcí
(bez náhody), ať je soubor pod 1 MB a vznikl pokaždé stejný.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from importlib import import_module
from pathlib import Path

os.environ["CEE_NATIVE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from cee.v2.language.processes import Process  # noqa: E402
from cee.v2.language.segments import Pattern, default_table  # noqa: E402
from cee.v2.simulation import Simulation  # noqa: E402

digest_worlds = import_module("v2_digests").worlds

#: Scénáře a počet let; valley-50 je zkrácené, ať záznam netrvá minuty.
SCENARIOS = {"grid-5x5": 1000, "shift": 900, "valley-50": 400}
#: Kolik aplikací si ponechá každá změna bez ohledu na vzorkování.
MINIMUM = 12
RULES = ("initial", "second", "antepenult", "penult", "final")


def table_fingerprint() -> dict[str, object]:
    """Otisk tabulky hlásek: zlatá data mají smysl jen nad touž tabulkou."""
    table = default_table()
    return {"segments": len(table.ipa), "sha256": hashlib.sha256("\n".join(table.ipa).encode()).hexdigest()}


def ranges(mask: np.ndarray) -> list[list[int]]:
    """Maska hlásek jako souvislé úseky [od, do): masky bývají velké a souvislé."""
    ids = np.flatnonzero(mask)
    if not len(ids):
        return []
    breaks = np.flatnonzero(np.diff(ids) > 1)
    begins = np.concatenate([[0], breaks + 1])
    ends = np.concatenate([breaks, [len(ids) - 1]])
    return [[int(ids[begin]), int(ids[end]) + 1] for begin, end in zip(begins, ends)]


def describe(process: Process) -> dict[str, object]:
    """Popis změny v JSON: parametry a masky vzorů jako úseky čísel hlásek."""
    def pattern(value: Pattern | None) -> dict[str, object] | None:
        return None if value is None else {"key": value.key, "ranges": ranges(value.mask), "size": len(value.mask)}
    return {
        "family": process.family, "operation": process.operation, "changes": [list(pair) for pair in process.changes],
        "segment": process.segment, "stress": process.stress, "medial": process.medial, "allow": list(process.allow),
        "tone": process.tone, "target": pattern(process.target), "left": pattern(process.left),
        "right": pattern(process.right), "right2": pattern(process.right2), "key": process.key,
    }


def record(years: dict[str, int]) -> dict[str, tuple[Process, dict[tuple[str, int, tuple[int, ...]], tuple[int, ...] | None]]]:
    """Spustí scénáře a vrátí aplikace: klíč změny → (změna, {(klíč, pravidlo, tvar): výsledek})."""
    seen: dict[str, tuple[Process, dict[tuple[str, int, tuple[int, ...]], tuple[int, ...] | None]]] = {}
    original = Process._apply  # type: ignore[attr-defined]

    def wrapped(self: Process, form, table, rule, boundary):  # type: ignore[no-untyped-def]
        result = original(self, form, table, rule, boundary)
        if boundary is None:
            entry = seen.setdefault(self.key, (self, {}))
            entry[1][(self.key, RULES.index(rule), form)] = None if result is None else result[0]
        return result

    Process._apply = wrapped  # type: ignore[attr-defined, method-assign]
    try:
        for name, build, default_years in digest_worlds(False):
            if name not in years:
                continue
            world, events = build()
            Simulation(world, events=events).run(min(years[name], default_years))
            print(f"{name}: {sum(len(entry[1]) for entry in seen.values())} různých aplikací", flush=True)
    finally:
        Process._apply = original  # type: ignore[attr-defined, method-assign]
    return seen


def keep(key: tuple[str, int, tuple[int, ...]], share: int) -> bool:
    """Pevný výběr: zhruba každá ``share``-tá aplikace (podle otisku, ne náhodou)."""
    digest = hashlib.blake2b(repr(key).encode(), digest_size=4).digest()
    return int.from_bytes(digest, "little") % share == 0


def build(seen, limit: int) -> dict[str, object]:
    total = sum(len(entry[1]) for entry in seen.values())
    share = max(1, -(-total // limit))
    forms: list[tuple[int, ...]] = []
    form_ids: dict[tuple[int, ...], int] = {}

    def intern(form: tuple[int, ...]) -> int:
        found = form_ids.get(form)
        if found is None:
            found = form_ids[form] = len(forms)
            forms.append(form)
        return found

    processes, records = [], []
    for key in sorted(seen):
        process, applications = seen[key]
        ordered = sorted(applications.items(), key=lambda pair: (pair[0][1], pair[0][2]))
        # Každá změna si ponechá aspoň prvních pár aplikací, ostatní se vzorkují.
        kept = [pair for number, pair in enumerate(ordered) if number < MINIMUM or keep(pair[0], share)]
        index = len(processes)
        processes.append(describe(process))
        for (_, rule, form), result in kept:
            records.append([index, rule, intern(form), -1 if result is None else intern(result)])
    return {"table": table_fingerprint(), "processes": processes, "forms": [list(form) for form in forms],
            "records": records, "recorded": total}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="tests/v2/data/golden_bank.json.gz")
    parser.add_argument("--limit", type=int, default=40000, help="nejvýš tolik záznamů (po vzorkování)")
    args = parser.parse_args()
    data = build(record(SCENARIOS), args.limit)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Bez jména a času v hlavičce, ať je soubor při každém běhu bajt po bajtu stejný.
    with output.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
        handle.write(json.dumps(data, separators=(",", ":"), sort_keys=True).encode())
    print(f"{output}: {len(data['processes'])} změn, {len(data['records'])} záznamů z {data['recorded']}, "
          f"{output.stat().st_size / 1024:.0f} kB")


if __name__ == "__main__":
    main()
