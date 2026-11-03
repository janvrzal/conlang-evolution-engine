"""Zlatá data tlaků (``Pressure.scores``): dávky ze skutečných běhů a výstupy bit po bitu.

Za běhu scénářů (grid-5x5, shift, valley-50 zkráceně, svět s elitou a obchodem, svět s církví,
písmem a školou a dva malé světy pro vzácné cesty) zaznamená ve vybraných tickách dávky
(``PressureBatch``), které ``transmission.fitness_of`` posílá tlakům, a výstup ``scores``
každého tlaku dávky. Ticky vzorku vybírá deterministicky ``rng.Stream``; vedle vzorku se
přidají dávky, které doplní pokrytí: tlak, jehož nenulový výstup vzorek nezastihl, dostane
první dávku, kde je nenulový.

Soubor ``tests/v2/data/golden_pressures.json.gz`` obsahuje pro každý scénář záznamy:

- ``tick``, ``call`` (pořadí dávky v ticku od nuly) a ``kind`` (druh proměnných dávky:
  ``lexical``, ``process``, ``form``, ``construction``, ``prosody``);
- ``batch``: **vstup jako pole bez živého světa**: ``variable_ids``, ``group_ids`` (jen
  vybrané řádky a skupiny), ``freqs`` a ``heard`` (``float64``, tvar proměnné × skupiny × sloty),
  ``numbers`` (čísla variant z registru ve slotech, −1 = prázdný slot), ``slots`` (ID variant,
  ``None`` = prázdný slot) a ``tick``;
- ``scores``: pro každý tlak dávky (podle jména) pole, jaké tlak vrátil (``dtype`` a tvar
  včetně rozšiřitelných, např. (proměnné, 1, sloty) u ``appeal``);
- ``reads``: co tlaky čtou ze světa kromě dávky, jako pole (viz níže).

**Co tlaky čtou ze stavu světa** (kromě dávky; ``reads`` obsahuje ty vstupy, které jsou čisté
hodnoty, ostatní zůstávají stavem světa v daném ticku):

- ``Conformity``: nic (jen ``freqs``);
- ``Appeal``, ``Motivation``, ``Entrenchment``, ``Actuation``, ``LexicalActuation``: sloupce
  tabulky variant ve slotech (``slot_appeal``, ``slot_change``, ``slot_morpheme``, ``slot_origin``,
  ``origin_names``), frekvence pojmů (``concept_frequency``), semínko světa a ``Parameters``;
- ``Articulation``, ``Clarity``, ``FunctionalLoad``, ``Dispersion``, ``Phonotactics``: proces
  proměnné (``process_slot`` = slot varianty „změna“, ``process_values`` = úspora artikulace,
  zřetelnost, příznak redukce bez přízvuku, příznak apokopy), hodnocení procesu v dosažených
  buňkách (``cell_row``, ``cell_column``, ``cell_assessment`` = nové homofony, krátká slova,
  změna rozptylu, změna příznakovosti), příznak silného přízvuku skupiny a podíl slov
  s koncovou souhláskou (``group_*``);
- ``Uniformity``, ``Conservation``, ``Teachability``, ``Distinctiveness``: analogická změna
  (``form_slot``, ``form_flags`` = vyrovnání, změna celého lexému), hodnocení tvaru v dosažených
  buňkách (``form_cell_*``) a podíl L2 mluvčích skupiny;
- ``Norm``: škola a spisovný jazyk skupiny (``group_schooling``), dominantní varianta spisovného
  jazyka a uzavřené proměnné kódu: **stav světa**;
- ``Taboo``: tabuizované pojmy skupin (``taboo``), stáří původu slova: **stav světa**;
- ``LexicalClarity``: index homofonů a eroze slov skupiny (``LexicalClarityIndex``): **stav světa**;
- ``Expressivity``, ``Economy``, ``Fusion``, ``Learnability``, ``Ambiguity``: konstrukce
  variant a převažující konstrukce skupiny, síla a slabost vyjádření funkce (``syntax.py``):
  **stav světa**.

**Stav světa se neukládá.** Snímek světa (pickle checkpointu) má 1 až 3 MB a nevejde se do
limitu 1 MB na soubor, proto ho vyrobí běh scénáře (``tests/v2/golden_worlds.py``, bitově
shodný s otisky ``scripts/v2_digests.py``) až do ticku záznamu; test ``test_v2_golden_pressures.py``
ho zopakuje, dávku sestaví ze záznamu (pole) nad tímto světem a porovná ``scores`` a ``reads``.
S ``--snapshots ADRESÁŘ`` skript navíc uloží pickle světa v tickách záznamů (pro ladění Rustu;
do repozitáře nepatří).

Záznam je výřez: z dávky se vezme několik řádků (proměnných), kde se něco děje, a několik
skupin; tlaky jsou po řádcích i po skupinách nezávislé (na tom stojí paralelní běh), a výstup
výřezu se proto spočítá tlakem znovu a skript ověří, že se rovná výřezu celého výstupu.
Záznam vzniká pokaždé stejný (bez náhody, bajt po bajtu).

Použití:  python scripts/v2_golden_pressures.py [--output-dir tests/v2/data] [--snapshots DIR]
"""

from __future__ import annotations

import argparse
import copy
import os
import pickle
import sys
from pathlib import Path
from typing import Any

os.environ["CEE_NATIVE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from cee.v2.changes import DEFAULT_CHANGES, pressures_by_kind  # noqa: E402
from tests.v2 import golden_worlds as worlds  # noqa: E402

#: Kolik ticků vzorku má každý scénář a kolik dávek jednoho druhu se v ticku zaznamená.
SAMPLE_TICKS = {"grid-5x5": 6, "shift": 6, "valley-50": 3, "trade-elite": 4, "church-school": 5,
                "rare-grammar": 3, "rare-sounds": 3}
PER_KIND = 3


def record(name: str, covered: set[str], snapshots: Path | None) -> list[dict[str, Any]]:
    simulation, ticks = worlds.new_simulation(name)
    chosen = set(worlds.sample_ticks(name, ticks, SAMPLE_TICKS[name], "pressures"))
    records: list[dict[str, Any]] = []
    taken: dict[tuple[int, str], int] = {}
    saved: set[int] = set()

    def handle(tick: int, first: int, batches: list[Any]) -> None:
        world = simulation.world
        for offset, (batch, outputs) in enumerate(batches):
            kind = world.variables[batch.variable_ids[0]].kind
            shape = batch.freqs.shape
            fresh = [(pressure, scores) for pressure, scores in outputs
                     if pressure.name not in covered and np.any(scores != 0)]
            sampled = tick in chosen and taken.get((tick, kind), 0) < PER_KIND
            if not sampled and not fresh:
                continue
            taken[(tick, kind)] = taken.get((tick, kind), 0) + 1
            focus = outputs if sampled else fresh
            rows, columns = worlds.choose(worlds.informative_cells(focus, shape))
            sub = worlds.narrowed(batch, rows, columns)
            scores: dict[str, np.ndarray] = {}
            for pressure, full in outputs:
                found = np.array(pressure.scores(sub))
                # Výřez celého výstupu musí být totéž, co výstup výřezu (jinak by tlak nebyl nezávislý).
                cut = worlds.full_scores(full, shape)[rows][:, columns]
                assert worlds.same(worlds.full_scores(found, sub.freqs.shape), cut), (name, tick, pressure.name)
                scores[pressure.name] = found
                if np.any(found != 0):
                    covered.add(pressure.name)
            records.append({
                "tick": tick, "call": first + offset, "kind": kind, "batch": worlds.batch_record(sub),
                "scores": scores, "reads": worlds.reads_of(sub),
            })
            if snapshots is not None and tick not in saved:
                saved.add(tick)
                (snapshots / f"{name}-{tick:03d}.pickle").write_bytes(pickle.dumps(copy.deepcopy(world), protocol=5))

    with worlds.probing_pressures(lambda tick: True, handle):
        simulation.run(simulation.world.start_year + ticks * worlds.DT)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="tests/v2/data")
    parser.add_argument("--snapshots", default=None, help="adresář pro pickle světa v tickách záznamů (nepovinné)")
    parser.add_argument("--scenarios", nargs="*", default=list(worlds.SCENARIOS), help="jen tyto scénáře (zkouška)")
    args = parser.parse_args()
    snapshots = None if args.snapshots is None else Path(args.snapshots)
    if snapshots is not None:
        snapshots.mkdir(parents=True, exist_ok=True)
    covered: set[str] = set()
    scenarios: dict[str, Any] = {}
    for name in args.scenarios:
        records = record(name, covered, snapshots)
        scenarios[name] = {"records": [worlds.encode(item) for item in records]}
        print(f"{name}: {len(records)} dávek, pokryto {len(covered)} tlaků", flush=True)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "golden_pressures.json.gz"
    worlds.write_gzip(path, {"scenarios": scenarios})
    print(f"{path}: {path.stat().st_size / 1024:.0f} kB")
    names = sorted({pressure.name for weighted in pressures_by_kind(DEFAULT_CHANGES).values()
                    for pressure, _ in weighted})
    print("bez nenulového výstupu:", ", ".join(name for name in names if name not in covered) or "žádný")


if __name__ == "__main__":
    main()
