"""Auditní historie běhu: log událostí, snímky a volitelné trajektorie."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Čísla v logu se zaokrouhlují, aby otisk běhu nezávisel na posledních bitech
# maticového násobení, které se mohou lišit mezi knihovnami BLAS.
_DECIMALS = 6


def _rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, _DECIMALS)
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_rounded(item) for item in value]
    return value


@dataclass
class History:
    events: list[dict[str, Any]] = field(default_factory=list)
    snapshots: list[Any] = field(default_factory=list)
    #: (varianta, skupina) → [(tick, frekvence)]; plní se jen na vyžádání.
    trajectories: dict[tuple[str, str], list[tuple[int, float]]] = field(default_factory=dict)

    def record(self, kind: str, tick: int, year: float, **payload: Any) -> None:
        event: dict[str, Any] = {"kind": kind, "tick": tick, "year": round(year, _DECIMALS)}
        for key, value in payload.items():
            event[key] = value if isinstance(value, (str, int)) and not isinstance(value, bool) else _rounded(value)
        self.events.append(event)

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [event for event in self.events if event["kind"] == kind]

    def lines(self) -> list[str]:
        return [json.dumps(event, sort_keys=True, ensure_ascii=False) for event in self.events]

    def digest(self) -> str:
        """Otisk celého logu; dva běhy se stejným seedem ho musí mít shodný."""
        sha = hashlib.sha256()
        for line in self.lines():
            sha.update(line.encode("utf-8"))
            sha.update(b"\n")
        return sha.hexdigest()

    def write_jsonl(self, path: str | Path) -> None:
        Path(path).write_text("".join(f"{line}\n" for line in self.lines()), encoding="utf-8")
