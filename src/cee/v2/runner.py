"""Běh simulace na pozadí pro UI: ověření popisu, průběh, průběžné snímky, zrušení.

:func:`check` ověří popis světa: schéma a přepisy parametrů v Pythonu (:mod:`cee.v2.spec`),
zbytek v Rustu (``check_spec``: slovník, slova, stavba světa, zkušební provedení událostí).
:func:`start` postaví svět v Rustu (vazba :mod:`cee_engine_py`, crate
``rust/cee_py``) a spustí běh ve vlákně. Každý krok běží v Rustu bez GIL, takže server mezitím odpovídá UI.
:class:`Run` průběžně ukládá lehké snímky (``Run.frame`` vazby) po každém
pozorování, takže UI kreslí mapu, zatímco běh pokračuje, a na konci drží úplný
export ``cee-v2/1``. Zrušení se projeví po dokončení rozpracovaného kroku.

Běh je deterministický: stejný popis dá stejný výsledek bez ohledu na to,
kolikrát a kdy se na průběh UI zeptá. Celý engine v2 je v Rustu; Python ho jen volá.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from cee.v2.spec import Issue, SpecError, WorldSpec, check_parameters, errors, parse

#: Kam `maturin` + `pip install --target` ukládá vazbu v repozitáři (viz ``rust/README.md``).
_TARGET = Path(__file__).resolve().parents[3] / "rust" / "cee_py" / "target" / "py"


def native() -> Any:
    """Modul vazby ``cee_engine_py``; když není v ``sys.path``, zkusí ``rust/cee_py/target/py``."""
    try:
        import cee_engine_py
    except ImportError:
        if not _TARGET.is_dir():
            raise ImportError(
                "Chybí vazba enginu v Rustu (cee_engine_py); sestavení je popsané v rust/README.md."
            ) from None
        sys.path.append(str(_TARGET))
        import cee_engine_py
    return cee_engine_py


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
    native: Any = field(default=None, repr=False)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def progress(self) -> float:
        span = self.spec.end_year - self.spec.start_year
        return min(1.0, max(0.0, (self.year - self.spec.start_year) / span))

    def cancel(self) -> None:
        self._cancel.set()
        if self.native is not None:
            self.native.cancel()

    def status_view(self, since: int = 0) -> dict[str, Any]:
        """Stav pro UI; ``since`` = kolik snímků už klient má."""
        with self._lock:
            return {
                "id": self.id, "status": self.status, "year": self.year, "progress": self.progress,
                "start_year": self.spec.start_year, "end_year": self.spec.end_year,
                "seconds": round(self.seconds, 2), "error": self.error,
                "frame_count": len(self.frames), "frames": self.frames[since:],
            }

    def execute(self) -> None:
        """Provede běh v tomto vlákně (``start`` ho volá ve vlákně na pozadí)."""
        try:
            observed = 0
            more = True
            while more:
                if self._cancel.is_set():
                    break
                more = self.native.advance(1)  # jeden krok bez GIL
                snapshots = self.native.snapshots
                year = self.native.year
                frame = json.loads(self.native.frame()) if snapshots != observed else None
                with self._lock:
                    self.year = year
                    self.seconds = time.monotonic() - self.started
                    if frame is not None:
                        observed = snapshots
                        self.frames.append(frame)
            if self._cancel.is_set() or self.native.cancelled:
                with self._lock:
                    self.status = "cancelled"
                return
            result = json.loads(self.native.export())
            with self._lock:
                self.result = result
                self.year = self.native.year
                self.seconds = time.monotonic() - self.started
                self.status = "done"
        except Exception as error:  # noqa: BLE001 - chyba běhu jde do UI, ne do logu serveru
            with self._lock:
                self.error = f"{type(error).__name__}: {error}"
                self.status = "failed"
            traceback.print_exc()


def check(data: dict[str, Any] | WorldSpec) -> list[Issue]:
    """Chyby a varování popisu světa s cestou k poli; bez chyb (:func:`errors`) jde svět postavit a spustit.

    Chyby jdou před varováními. Varování svět nezastaví: například jiný slovník než výchozí
    dá jiné výsledky než výchozí svět.
    """
    spec, issues = parse(data)
    if spec is None:
        return issues
    issues = check_parameters(spec)
    if issues:
        return issues
    found = native().check_spec(json.dumps(spec.model_dump(mode="json", by_alias=True)))
    return [Issue(item["path"], item["message"], item["severity"]) for item in found]


def prepare(run_id: str, data: dict[str, Any] | WorldSpec) -> Run:
    """Běh z popisu světa; neplatný popis vyhodí ``SpecError``.

    Schéma ověří pydantic, zbytek (neznámé regiony, slova, parametry) ohlásí stavba světa v Rustu.
    Úplné ověření s cestami k polím a varováními dává :func:`check` (``/api/v2/validate``).
    """
    spec, issues = parse(data)
    if spec is None:
        raise SpecError(issues)
    try:
        handle = native().Run(json.dumps(spec.model_dump(mode="json", by_alias=True)))
    except ValueError as error:
        raise SpecError(errors([Issue("(svět)", str(error))])) from error
    return Run(run_id, spec, year=spec.start_year, native=handle)


def start(run_id: str, data: dict[str, Any] | WorldSpec) -> Run:
    """Spustí běh na pozadí a hned vrátí jeho stav."""
    run = prepare(run_id, data)
    threading.Thread(target=run.execute, name=f"cee-v2-{run_id}", daemon=True).start()
    return run
