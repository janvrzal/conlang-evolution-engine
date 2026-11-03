"""Zlatá data kroku fonologizace: záznam vstupů a výstupů ze skutečných běhů.

Za běhu scénářů (grid-5x5, shift, valley-50 zkráceně) v Pythonu (``CEE_NATIVE=0``,
tedy referenční implementace) zaznamená tři druhy případů, na kterých
``tests/v2/test_v2_native_phonology.py`` ověří Rust (``cee_core``):

- ``apply``: přepis tvaru zvukovou změnou včetně hranice kmen | koncovka
  (``Process.apply_tracked``): změna, pravidlo přízvuku, tvar, hranice, výsledek;
- ``queue``: zařazení morfému do fronty procesu (``phonology._queue``): změna,
  pravidlo, tvar, příznaky „už přepsáno“ a „už čeká“, sklon slova, četnost
  užití a potřebný logit (nebo že se morfém nezařadil);
- ``activate``: fronta nového procesu ze slovní zásoby (``phonology.activate``):
  slova se tvarem, příznakem a lexémem, sklony a četnosti lexémů a výsledná
  fronta (pořadí a logity).

Záznam je výřez: změny se berou všechny, případů se vzorkuje pevnou funkcí
(bez náhody), ať je soubor pod 1 MB a vznikl pokaždé stejný.

Použití:  python scripts/v2_golden_phonology.py [--output tests/v2/data/golden_phonology.json.gz]
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

os.environ["CEE_NATIVE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cee.v2 import phonology  # noqa: E402
from cee.v2.language.columns import ProcessQueue  # noqa: E402
from cee.v2.language.processes import Process  # noqa: E402
from cee.v2.simulation import Simulation  # noqa: E402

golden_bank = import_module("v2_golden_bank")
digest_worlds = import_module("v2_digests").worlds

#: Scénáře a počet let; valley-50 je zkrácené, ať záznam netrvá minuty.
SCENARIOS = {"grid-5x5": 1000, "shift": 900, "valley-50": 500}
RULES = golden_bank.RULES
#: Nejvýš tolik případů daného druhu po vzorkování (a aspoň ``MINIMUM`` na změnu a druh).
LIMITS = {"apply": 6000, "queue": 9000}
MINIMUM = 6
ACTIVATIONS = 24
MAX_WORDS = 500


def keep(key: object, share: int) -> bool:
    """Pevný výběr: zhruba každý ``share``-tý případ (podle otisku, ne náhodou)."""
    digest = hashlib.blake2b(repr(key).encode(), digest_size=4).digest()
    return int.from_bytes(digest, "little") % share == 0


class Recorder:
    def __init__(self) -> None:
        self.processes: dict[str, tuple[Process, int]] = {}
        self.applies: dict[tuple[Any, ...], Any] = {}
        self.queues: dict[tuple[Any, ...], Any] = {}
        self.activations: list[dict[str, Any]] = []
        self.constants: dict[str, float] = {}
        self._inserted: list[float] = []

    def index(self, process: Process) -> int:
        found = self.processes.get(process.key)
        if found is None:
            found = self.processes[process.key] = (process, len(self.processes))
        return found[1]


def record(recorder: Recorder, years: dict[str, int]) -> None:
    original_apply = Process.apply_tracked
    original_queue = phonology._queue
    original_activate = phonology.activate
    original_insert = ProcessQueue.insert

    def apply_tracked(self: Process, form: Any, table: Any, rule: Any, boundary: Any) -> Any:
        result = original_apply(self, form, table, rule, boundary)
        key = (self.key, RULES.index(rule), form, boundary)
        recorder.applies.setdefault(key, (self, None if result is None else (list(result[0]), result[1])))
        return result

    def insert(self: ProcessQueue, needed: float, name: str) -> None:
        recorder._inserted.append(needed)
        original_insert(self, needed, name)

    def queue(world: Any, code: Any, variable_id: str, morpheme_id: str) -> None:
        state = code.phonology
        process = world.processes[variable_id]
        restructured = morpheme_id in state.restructured.get(variable_id, ())
        waiting = morpheme_id in state.queued.get(variable_id, ())
        form = world.form_of(code, morpheme_id)
        lexeme = world.morphemes[morpheme_id].lexeme_id
        frequency = world.usage_frequency(code, lexeme) if process.reductive else None
        bias = phonology.word_bias(world, variable_id, morpheme_id)
        recorder._inserted.clear()
        original_queue(world, code, variable_id, morpheme_id)
        needed = recorder._inserted[0] if recorder._inserted else None
        key = (process.key, RULES.index(code.stress_rule), form, restructured, waiting, bias, frequency)
        recorder.queues.setdefault(key, (process, needed))
        threshold = world.params.restructure_threshold
        recorder.constants = {
            "threshold": threshold, "base": math.log(threshold / (1 - threshold)),
            "lead": world.params.frequency_lead,
        }

    def activate(world: Any, code: Any, variable_id: str) -> None:
        state = code.phonology
        fresh = variable_id not in state.pending and variable_id not in state.closed
        words = sorted(state.vocabulary) if fresh else []
        process = world.processes[variable_id]
        rule = code.stress_rule
        restructured = state.restructured.get(variable_id, ())
        info = None
        if fresh and 40 <= len(words) <= MAX_WORDS:
            info = {
                "words": [
                    [list(world.form_of(code, name)), name in restructured,
                     world.morphemes[name].lexeme_id] for name in words
                ],
                "process": process, "rule": RULES.index(rule), "names": words,
            }
            lexemes = sorted({entry[2] for entry in info["words"]})
            info["lexemes"] = {
                lexeme: [
                    phonology.word_bias(world, variable_id, lexeme),
                    world.usage_frequency(code, lexeme) if process.reductive else None,
                ]
                for lexeme in lexemes
            }
        original_activate(world, code, variable_id)
        if info is not None and state.pending.get(variable_id):
            queue_ = state.pending[variable_id]
            info["queue"] = [[needed, name] for needed, name in queue_.pairs()]
            recorder.activations.append(info)

    Process.apply_tracked = apply_tracked  # type: ignore[method-assign]
    ProcessQueue.insert = insert  # type: ignore[method-assign]
    phonology._queue = queue
    phonology.activate = activate
    try:
        for name, build, default_years in digest_worlds(False):
            if name not in years:
                continue
            world, events = build()
            Simulation(world, events=events).run(min(years[name], default_years))
            print(f"{name}: {len(recorder.applies)} přepisů, {len(recorder.queues)} zařazení, "
                  f"{len(recorder.activations)} aktivací", flush=True)
    finally:
        Process.apply_tracked = original_apply  # type: ignore[method-assign]
        ProcessQueue.insert = original_insert  # type: ignore[method-assign]
        phonology._queue = original_queue
        phonology.activate = original_activate


def sample(entries: dict[tuple[Any, ...], Any], limit: int, interesting: Any) -> list[tuple[tuple[Any, ...], Any]]:
    """Vzorek případů: pevný výběr, ale ``interesting`` případů (zařazení, přepis) víc a aspoň ``MINIMUM`` na změnu."""
    share = max(1, -(-len(entries) // limit))
    kept: list[tuple[tuple[Any, ...], Any]] = []
    per_process: dict[str, int] = {}
    for key, value in sorted(entries.items(), key=lambda pair: repr(pair[0])):
        count = per_process.get(key[0], 0)
        if count < MINIMUM or keep(key, share if not interesting(value) else max(1, share // 3)):
            kept.append((key, value))
            per_process[key[0]] = count + 1
    return kept


def build(recorder: Recorder) -> dict[str, object]:
    forms: list[list[int]] = []
    form_ids: dict[tuple[int, ...], int] = {}

    def intern(form: Any) -> int:
        key = tuple(form)
        found = form_ids.get(key)
        if found is None:
            found = form_ids[key] = len(forms)
            forms.append(list(key))
        return found

    applies = [
        [recorder.index(process), key[1], intern(key[2]), -1 if key[3] is None else key[3],
         None if result is None else [intern(result[0]), -1 if result[1] is None else result[1]]]
        for key, (process, result) in sample(recorder.applies, LIMITS["apply"], lambda value: value[1] is not None)
    ]
    queues = [
        [recorder.index(process), key[1], intern(key[2]), key[3], key[4], key[5], key[6], needed]
        for key, (process, needed) in sample(recorder.queues, LIMITS["queue"], lambda value: value[1] is not None)
    ]
    # Aktivace: rovnoměrně napříč zaznamenanými, nejvýš ``ACTIVATIONS``.
    step = max(1, len(recorder.activations) // ACTIVATIONS)
    activations = []
    for info in recorder.activations[::step][:ACTIVATIONS]:
        lexemes = sorted(info["lexemes"])
        activations.append({
            "process": recorder.index(info["process"]), "rule": info["rule"],
            "words": [[intern(form), flag, lexemes.index(lexeme)] for form, flag, lexeme in info["words"]],
            "lexemes": [info["lexemes"][lexeme] for lexeme in lexemes],
            # Fronta jako (index slova ve slovní zásobě, logit) v pořadí (logit, jméno);
            # slova jsou seřazená podle jména, takže index rozhoduje shodné logity stejně.
            "queue": [[info["names"].index(name), needed] for needed, name in info["queue"]],
        })
    return {
        "table": golden_bank.table_fingerprint(), "constants": recorder.constants,
        "processes": [golden_bank.describe(process) for process, _ in sorted(
            recorder.processes.values(), key=lambda pair: pair[1])],
        "forms": forms, "apply": applies, "queue": queues, "activate": activations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="tests/v2/data/golden_phonology.json.gz")
    args = parser.parse_args()
    recorder = Recorder()
    record(recorder, SCENARIOS)
    data = build(recorder)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
        handle.write(json.dumps(data, separators=(",", ":"), sort_keys=True).encode())
    print(f"{output}: {len(data['processes'])} změn, {len(data['apply'])} přepisů, {len(data['queue'])} zařazení, "
          f"{len(data['activate'])} aktivací, {output.stat().st_size / 1024:.0f} kB")


if __name__ == "__main__":
    main()
