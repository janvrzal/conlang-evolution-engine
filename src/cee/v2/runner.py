"""Běh simulace na pozadí pro UI: průběh, průběžné snímky, zrušení.

:func:`start` postaví svět z popisu (:mod:`cee.v2.spec`) a spustí běh ve
vlákně. :class:`Run` průběžně ukládá lehké snímky (:func:`export.frame`)
po každém pozorování, takže UI kreslí mapu, zatímco běh pokračuje, a na
konci drží úplný export (:func:`export.export`). Zrušení se projeví po
dokončení rozpracovaného kroku.

Běh je deterministický: stejný popis dá stejný výsledek bez ohledu na to,
kolikrát a kdy se na průběh UI zeptá.
"""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Literal

from cee.v2 import export
from cee.v2.simulation import Simulation
from cee.v2.spec import WorldSpec, build

Status = Literal["running", "done", "failed", "cancelled"]


@dataclass
class Run:
    """Jeden běh: stav, průběh a výsledky (čtení je bezpečné z jiného vlákna)."""

    id: str
    spec: WorldSpec
    status: Status = "running"
    year: float = 0.0
    frames: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    started: float = field(default_factory=time.monotonic)
    seconds: float = 0.0
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def progress(self) -> float:
        span = self.spec.end_year - self.spec.start_year
        return min(1.0, max(0.0, (self.year - self.spec.start_year) / span))

    def cancel(self) -> None:
        self._cancel.set()

    def status_view(self, since: int = 0) -> dict[str, Any]:
        """Stav pro UI; ``since`` = kolik snímků už klient má."""
        with self._lock:
            return {
                "id": self.id, "status": self.status, "year": self.year, "progress": self.progress,
                "start_year": self.spec.start_year, "end_year": self.spec.end_year,
                "seconds": round(self.seconds, 2), "error": self.error,
                "frame_count": len(self.frames), "frames": self.frames[since:],
            }

    def execute(self, simulation: Simulation) -> None:
        """Provede běh v tomto vlákně (``start`` ho volá ve vlákně na pozadí)."""
        try:
            observed = 0
            for step in simulation.iterate(self.spec.end_year):
                if self._cancel.is_set():
                    with self._lock:
                        self.status = "cancelled"
                    return
                snapshots = len(step.history.snapshots)
                with self._lock:
                    self.year = step.year
                    self.seconds = time.monotonic() - self.started
                    if snapshots != observed:
                        observed = snapshots
                        self.frames.append(export.frame(step))
            result = export.export(simulation)
            with self._lock:
                self.result = result
                self.year = simulation.year
                self.seconds = time.monotonic() - self.started
                self.status = "done"
        except Exception as error:  # noqa: BLE001 - chyba běhu jde do UI, ne do logu serveru
            with self._lock:
                self.error = f"{type(error).__name__}: {error}"
                self.status = "failed"
            traceback.print_exc()


def prepare(run_id: str, data: dict[str, Any] | WorldSpec) -> tuple[Run, Simulation]:
    """Běh a simulace z popisu světa; neplatný popis vyhodí ``SpecError``."""
    world, events, spec = build(data)
    return Run(run_id, spec, year=spec.start_year), Simulation(world, events=events)


def start(run_id: str, data: dict[str, Any] | WorldSpec) -> Run:
    """Spustí běh na pozadí a hned vrátí jeho stav."""
    run, simulation = prepare(run_id, data)
    threading.Thread(target=run.execute, args=(simulation,), name=f"cee-v2-{run_id}", daemon=True).start()
    return run
