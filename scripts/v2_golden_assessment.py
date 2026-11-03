"""Zlatá data hodnocení: záznam vstupů a výstupů ze skutečných běhů.

Za běhu scénářů (grid-5x5, shift, valley-50 zkráceně) v Pythonu (``CEE_NATIVE=0``,
tedy referenční implementace) zaznamená případy, na kterých
``tests/v2/test_v2_native_assess.py`` ověří Rust (``cee_core``):

- ``assess``: dávka hodnocení zvukového procesu (``assessment._assess_batch``):
  změna, pravidlo přízvuku, pro každou skupinu tvary slov vzorku a jejich váhy,
  pořadí a cena dvojic nových homofonů (``assessment._pair``) a výsledné
  ``ProcessAssessment``. Rust počítá matici a dvojice, ostatní skládá Python
  stejným kódem jako ve hře;
- ``supports``: opory kandidátů zvukových změn nad počty prostředí
  (``_CombinedSoundCandidates.eval_supports``): inventář (z něj se kandidáti
  sestaví znovu), prostředí, počty (celé rozdíly i s zápornými hodnotami) a opory.

Záznam je výřez: případů se vzorkuje pevnou funkcí (bez náhody), ať je soubor
pod 1 MB a vznikl pokaždé stejný.

Použití:  python scripts/v2_golden_assessment.py [--output tests/v2/data/golden_assessment.json.gz]
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
from typing import Any

os.environ["CEE_NATIVE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from cee.v2 import assessment  # noqa: E402
from cee.v2.changes import sound  # noqa: E402
from cee.v2.language.processes import Process  # noqa: E402
from cee.v2.simulation import Simulation  # noqa: E402

golden_bank = import_module("v2_golden_bank")
digest_worlds = import_module("v2_digests").worlds

#: Scénáře a počet let; valley-50 je zkrácené, ať záznam netrvá minuty.
SCENARIOS = {"grid-5x5": 1000, "shift": 900, "valley-50": 500}
RULES = golden_bank.RULES
#: Nejvýš tolik řádků (skupin) hodnocení po vzorkování a aspoň tolik na změnu.
ASSESS_ROWS = 260
#: Opory: nejvýš tolik případů, z nich aspoň tolik s rozdílovými (zápornými) počty a s hláskou mimo inventář.
SUPPORT_CASES = 160
SUPPORT_DELTAS = 50
SUPPORT_MISSING = 20
MINIMUM = 2


def keep(key: object, share: int) -> bool:
    """Pevný výběr: zhruba každý ``share``-tý případ (podle otisku, ne náhodou)."""
    digest = hashlib.blake2b(repr(key).encode(), digest_size=4).digest()
    return int.from_bytes(digest, "little") % share == 0


class Recorder:
    def __init__(self) -> None:
        self.processes: dict[str, tuple[Process, int]] = {}
        self.assess: list[dict[str, Any]] = []
        self.supports: list[dict[str, Any]] = []

    def index(self, process: Process) -> int:
        found = self.processes.get(process.key)
        if found is None:
            found = self.processes[process.key] = (process, len(self.processes))
        return found[1]


def record(recorder: Recorder, years: dict[str, int]) -> None:
    original_batch = assessment._assess_batch_python
    original_pair = assessment._pair
    original_supports = sound._CombinedSoundCandidates.eval_supports

    def supports(self: Any, prev: Any, seg: Any, foll: Any, stressed: Any, foll2: Any, counts: Any, table: Any) -> Any:
        result = original_supports(self, prev, seg, foll, stressed, foll2, counts, table)
        if len(counts):
            cols = self.masks.cols
            missing = any(
                bool((cols[np.minimum(np.searchsorted(cols, ids), len(cols) - 1)] != ids).any())
                for ids in (prev, seg, foll, foll2)
            )
            recorder.supports.append({
                "inventory": list(self.inventory), "previous": prev.tolist(), "segment": seg.tolist(),
                "following": foll.tolist(), "stressed": stressed.tolist(), "following2": foll2.tolist(),
                "count": counts.tolist(), "result": result.tolist(), "missing": missing,
            })
        return result

    def batch(world: Any, group_ids: list[str], variable_id: str) -> Any:
        pairs: list[tuple[str, str, str, float]] = []

        def pair(world_: Any, frequency: Any, first: str, second: str, group_id: str) -> float:
            value = original_pair(world_, frequency, first, second, group_id)
            pairs.append((group_id, first, second, value))
            return value

        assessment._pair = pair
        try:
            results = original_batch(world, group_ids, variable_id)
        finally:
            assessment._pair = original_pair
        if world.table is None:
            return results
        process = world.processes[variable_id]
        by_rule: dict[str, list[int]] = {}
        for position, group_id in enumerate(group_ids):
            by_rule.setdefault(world.groups[group_id].main_code.stress_rule, []).append(position)
        for rule, positions in sorted(by_rule.items()):
            vocabularies = [assessment._vocabulary(world, group_ids[position]) for position in positions]
            width = max((len(vocabulary.ids) for vocabulary in vocabularies), default=0)
            if width == 0:
                continue
            rows = []
            table = world.form_bank().process_table(process, rule)
            for position, vocabulary in zip(positions, vocabularies):
                group_id = group_ids[position]
                numbers = {name: number for number, name in enumerate(vocabulary.morphemes)}
                found = [(numbers[first], numbers[second], value)
                         for group, first, second, value in pairs if group == group_id]
                result = results[position]
                changed = table.results(vocabulary.ids)
                rows.append({
                    # Čísla tvarů v bance při záznamu.
                    "ids": vocabulary.ids.tolist(), "changed": [int(item) for item in changed],
                    "banked": {int(i): list(world.form_bank().forms[int(i)])
                               for i in [*vocabulary.ids.tolist(), *(int(item) for item in changed if item >= 0)]},
                    "weights": [float(weight) for weight in vocabulary.weights],
                    "total": vocabulary.total, "pairs": [list(item) for item in found],
                    "result": None if result is assessment.NEUTRAL else [
                        result.coverage, result.merge_mass, result.short_share,
                        result.markedness_delta, result.dispersion_delta],
                })
            recorder.assess.append({
                "process": recorder.index(process), "rule": RULES.index(rule), "width": width, "rows": rows,
            })
        return results

    assessment._assess_batch_python = batch
    sound._CombinedSoundCandidates.eval_supports = supports  # type: ignore[method-assign]
    try:
        for name, build, default_years in digest_worlds(False):
            if name not in years:
                continue
            world, events = build()
            Simulation(world, events=events).run(min(years[name], default_years))
            print(f"{name}: {len(recorder.assess)} dávek hodnocení", flush=True)
    finally:
        assessment._assess_batch_python = original_batch
        sound._CombinedSoundCandidates.eval_supports = original_supports  # type: ignore[method-assign]


def interesting(case: dict[str, Any]) -> bool:
    return any(row["result"] is not None and (row["pairs"] or row["result"][4] != 0.0) for row in case["rows"])


def build(recorder: Recorder) -> dict[str, object]:
    forms: list[list[int]] = []
    form_ids: dict[tuple[int, ...], int] = {}

    def intern(form: list[int]) -> int:
        key = tuple(form)
        found = form_ids.get(key)
        if found is None:
            found = form_ids[key] = len(forms)
            forms.append(list(key))
        return found

    # Dávky se zajímavými řádky (nové homofony, zisk rozptylu) mají přednost; zbytek
    # se vzorkuje, ale každá změna si ponechá aspoň ``MINIMUM`` dávky.
    cases = [case for case in recorder.assess if any(row["result"] is not None for row in case["rows"])]
    rows_total = sum(len(case["rows"]) for case in cases)
    share = max(1, -(-rows_total // ASSESS_ROWS))
    kept: list[dict[str, Any]] = []
    per_process: dict[int, int] = {}
    for number, case in enumerate(cases):
        count = per_process.get(case["process"], 0)
        key = (case["process"], case["rule"], number)
        if count < MINIMUM or keep(key, max(1, share // 4) if interesting(case) else share):
            kept.append(case)
            per_process[case["process"]] = count + 1
    # Strop na počet řádků (soubor pod 1 MB): zajímavé dávky zůstanou, ostatní se ořezávají odzadu.
    while sum(len(case["rows"]) for case in kept) > ASSESS_ROWS:
        for position in range(len(kept) - 1, -1, -1):
            if not interesting(kept[position]) and per_process[kept[position]["process"]] > MINIMUM:
                per_process[kept[position]["process"]] -= 1
                del kept[position]
                break
        else:
            break
    assess = []
    for case in kept:
        # Tvary dávky podle čísla v bance při záznamu (test banku plní ve stejném pořadí;
        # pořadí dvojic nových homofonů na číslech tvarů nezávisí, viz ``assessment._new_pairs``).
        banked: dict[int, list[int]] = {}
        for row in case["rows"]:
            banked.update(row["banked"])
        numbers = sorted(banked)
        positions = {number: position for position, number in enumerate(numbers)}
        assess.append({
            "process": case["process"], "rule": case["rule"], "width": case["width"],
            "order": [intern(banked[number]) for number in numbers],
            "rows": [
                {
                    "ids": [positions[number] for number in row["ids"]], "weights": row["weights"],
                    "total": row["total"], "pairs": row["pairs"], "result": row["result"],
                }
                for row in case["rows"]
            ],
        })
    # Opory: případy s rozdílovými počty a s hláskou mimo inventář mají přednost, zbytek pevným výběrem.
    deltas = [case for case in recorder.supports if any(count < 0 for count in case["count"])]
    missing = [case for case in recorder.supports if case["missing"]]
    rest = [case for case in recorder.supports if case not in deltas and case not in missing]
    share = max(1, -(-len(rest) // max(1, SUPPORT_CASES - SUPPORT_DELTAS - SUPPORT_MISSING)))
    chosen = deltas[::max(1, len(deltas) // SUPPORT_DELTAS)][:SUPPORT_DELTAS]
    chosen += missing[::max(1, len(missing) // SUPPORT_MISSING)][:SUPPORT_MISSING]
    chosen += [case for number, case in enumerate(rest) if keep(number, share)]
    supports = [
        {key: value for key, value in case.items() if key != "missing"} | {"missing": case["missing"]}
        for case in chosen[:SUPPORT_CASES + SUPPORT_DELTAS + SUPPORT_MISSING]
    ]
    return {
        "supports": supports,
        "table": golden_bank.table_fingerprint(),
        "processes": [golden_bank.describe(process) for process, _ in sorted(
            recorder.processes.values(), key=lambda pair: pair[1])],
        "forms": forms, "assess": assess,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="tests/v2/data/golden_assessment.json.gz")
    args = parser.parse_args()
    recorder = Recorder()
    record(recorder, SCENARIOS)
    data = build(recorder)
    output = Path(args.output)
    if not data["supports"] and output.exists():
        # Opory zvukových změn se od B5 počítá ``SoundIndex``, takže je ``eval_supports`` za běhu
        # nezavolá; zlatá data opor (jádro ``sound_supports``) se proto ponechají z dosavadního souboru.
        with gzip.open(output) as handle:
            data["supports"] = json.loads(handle.read())["supports"]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
        handle.write(json.dumps(data, separators=(",", ":"), sort_keys=True).encode())
    rows = sum(len(case["rows"]) for case in data["assess"])  # type: ignore[attr-defined]
    print(f"{output}: {len(data['assess'])} dávek, {rows} řádků, {len(data['supports'])} opor, "  # type: ignore[arg-type]
          f"{output.stat().st_size / 1024:.0f} kB")


if __name__ == "__main__":
    main()
