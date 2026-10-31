"""Paralelní běh: víc procesů, každý s celým světem, drahé dotazy po částech.

Engine roste s počtem skupin lineárně; drahá je konstanta na buňku
(skupina × živá proměnná). Zhruba dvě třetiny času jsou dva druhy čistých
dotazů na stav na začátku kroku, které se počítají pro každou skupinu
zvlášť:

- **tlaky** na varianty při přenosu (:func:`cee.v2.transmission.fitness_of`),
- **tempo inovací** každé změny ve skupině (``Change.total_rate``).

Každý proces (*shard*) drží úplnou kopii světa a provádí celý krok sám
(míšení, inovace, demografie, události, pozorování), takže stav všech kopií
zůstává stejný. Dotazy ale počítá jen pro své skupiny a výsledky si procesy
vymění přes koordinátora v hlavním procesu. Skupina patří vždy témuž procesu
(stabilní hash ID), takže její keše, včetně hodnocení zvukových změn, které
zastarává po krocích, vznikají ve stejných krocích jako v jednom procesu.
Výsledek je proto bitově stejný jako běh v jednom procesu (testy
``tests/v2/test_v2_parallel.py``).

**Stav: pokus, nezrychluje.** Rozdělené dotazy jsou jen asi třetina až
polovina času; zbytek (uplatnění inovací, vstup slov do slovníku,
fonologizace, míšení, demografie, pozorování) musí kvůli shodě stavu dělat
každý proces celý, a čeká se na nejpomalejší proces. Naměřeno 0,99× se
dvěma a 0,89× se čtyřmi procesy (docs/engine-v2/16-rozhrani-ui.md). Skutečné
zrychlení chce, aby i tyto kroky dělal jen vlastník skupiny. Runner ani API
paralelní běh nepoužívají.

Diagnostika: ``CEE_PARALLEL_TIMING=1`` vypíše čas výměny a výpočtu tlaků
každého procesu, ``CEE_PARALLEL_PROFILE=adresář`` uloží profil každého procesu.

Rozdělení podle skupin, ne podle regionů: každý proces má celý svět, takže
na sousedství nezáleží a hash rozloží práci rovnoměrně i tehdy, když stát
přidá do některých regionů dvojjazyčné skupiny.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
import time
import traceback
from multiprocessing.connection import Connection
from typing import Any, Callable, Sequence

import numpy as np

from cee.v2.rng import stable_int

#: Pevný hash seed pro všechny procesy, aby se kopie světa chovaly stejně
#: i tam, kde by na pořadí množin přece jen záleželo.
HASH_SEED = "0"


def owner(group_id: str, shards: int) -> int:
    """Proces, kterému skupina patří (stabilní v čase i mezi stroji)."""
    return int(stable_int("shard", group_id) % shards)


class Shards:
    """Napojení simulace v jednom procesu na ostatní (``Simulation.shards``)."""

    def __init__(self, index: int, count: int, connection: Connection) -> None:
        self.index, self.count, self.connection = index, count, connection
        self._owners: dict[str, bool] = {}
        #: Čas strávený výměnou (odeslání a čekání na ostatní) podle druhu dotazu.
        self.timing: dict[str, float] = {}

    def owns(self, group_id: str) -> bool:
        found = self._owners.get(group_id)
        if found is None:
            found = self._owners[group_id] = owner(group_id, self.count) == self.index
        return found

    def gather(self, tag: str, payload: Any) -> list[Any]:
        """Pošle svou část a vrátí části všech procesů (v pořadí procesů)."""
        started = time.perf_counter()
        self.connection.send((tag, payload))
        reply = self.connection.recv()
        self.timing[tag] = self.timing.get(tag, 0.0) + time.perf_counter() - started
        if isinstance(reply, BaseException):
            raise reply
        return reply

    def fitness(self, world: Any, block: Any, inputs: Any, pressures: Any, heard: np.ndarray) -> np.ndarray:
        """Tlaky bloku: vlastní sloupce spočítá, ostatní dostane (``fitness_hook``)."""
        from cee.v2.transmission import fitness_of

        columns = [column for column, group_id in enumerate(inputs.group_ids) if self.owns(group_id)]
        started = time.perf_counter()
        part = fitness_of(world, block, inputs, pressures, heard, columns)
        self.timing["fitness-compute"] = self.timing.get("fitness-compute", 0.0) + time.perf_counter() - started
        full = np.zeros_like(block.freqs)
        for owned, values in self.gather("fitness", (columns, part)):
            if owned:
                full[:, owned] = values
        return full


def _worker(index: int, count: int, connection: Connection, frames: Any, data: dict[str, Any],
            until: float | None) -> None:
    """Jeden proces: postaví svět z popisu a běží v kroku s ostatními."""
    from cee.v2 import export
    from cee.v2.simulation import Simulation
    from cee.v2.spec import build

    profile_dir = os.environ.get("CEE_PARALLEL_PROFILE")
    profiler = None
    if profile_dir:
        import cProfile

        profiler = cProfile.Profile()
        profiler.enable()
    try:
        world, events, spec = build(data)
        simulation = Simulation(world, events=events)
        simulation.shards = Shards(index, count, connection)
        end = spec.end_year if until is None else until
        observed = 0
        for step in simulation.iterate(end):
            if index == 0 and frames is not None and len(step.history.snapshots) != observed:
                observed = len(step.history.snapshots)
                frames.put(("frame", step.year, export.frame(step)))
            if index == 0 and frames is not None:
                frames.put(("year", step.year, None))
        if os.environ.get("CEE_PARALLEL_TIMING"):
            print(f"shard {index}: {{{', '.join(f'{k}: {v:.2f}' for k, v in sorted(simulation.shards.timing.items()))}}}",
                  file=sys.stderr, flush=True)
        result = export.export(simulation) if index == 0 else None
        if profiler is not None:
            profiler.disable()
            profiler.dump_stats(os.path.join(str(profile_dir), f"shard-{index}.prof"))
        connection.send(("done", (simulation.history.digest(), result)))
    except BaseException as error:  # noqa: BLE001 - chyba se předá koordinátorovi
        traceback.print_exc()
        connection.send(("error", f"{type(error).__name__}: {error}"))


def _coordinate(connections: Sequence[Connection], cancelled: Callable[[], bool]) -> list[Any]:
    """Předává části dotazů mezi procesy, dokud všechny nedoběhnou."""
    while True:
        messages = [connection.recv() for connection in connections]
        tags = {tag for tag, _ in messages}
        if "error" in tags:
            errors = [payload for tag, payload in messages if tag == "error"]
            raise RuntimeError("; ".join(errors))
        if tags == {"done"}:
            return [payload for _, payload in messages]
        if len(tags) != 1:
            raise RuntimeError(f"Procesy se rozešly: {sorted(tags)}")
        if cancelled():
            for connection in connections:
                connection.send(RuntimeError("Běh zrušen."))
            raise RuntimeError("Běh zrušen.")
        reply = [payload for _, payload in messages]
        for connection in connections:
            connection.send(reply)


def run(
    data: dict[str, Any], workers: int, *, until: float | None = None, frames: Any = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[str, dict[str, Any]]:
    """Spustí popis světa v ``workers`` procesech; vrátí otisk historie a export.

    ``frames`` (``multiprocessing`` fronta) dostává průběžné snímky z prvního
    procesu: ``("frame", rok, snímek)`` a ``("year", rok, None)``.
    """
    if workers < 2:
        raise ValueError("Paralelní běh potřebuje aspoň dva procesy.")
    context = multiprocessing.get_context("spawn")
    previous = os.environ.get("PYTHONHASHSEED")
    os.environ["PYTHONHASHSEED"] = HASH_SEED
    processes, connections = [], []
    try:
        for index in range(workers):
            parent, child = context.Pipe()
            process = context.Process(
                target=_worker, args=(index, workers, child, frames, data, until),
                name=f"cee-v2-shard-{index}", daemon=True,
            )
            process.start()
            child.close()
            processes.append(process)
            connections.append(parent)
    finally:
        if previous is None:
            os.environ.pop("PYTHONHASHSEED", None)
        else:
            os.environ["PYTHONHASHSEED"] = previous
    try:
        results = _coordinate(connections, cancelled)
    finally:
        for process in processes:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
    digests = {digest for digest, _ in results}
    if len(digests) != 1:
        raise RuntimeError("Kopie světa v procesech se rozešly (různé otisky historie).")
    return results[0][0], results[0][1]
