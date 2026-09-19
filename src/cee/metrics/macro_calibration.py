"""Výběr makro-parametrů proti nesměrovanému profilu kognátů."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from cee.metrics.correspondence import correspondence_hellinger


@dataclass(frozen=True)
class MacroCalibrationResult:
    parameters: dict[str, float]
    profile: dict[str, float]
    distance: float


def calibrate_macro_grid(
    candidates: Iterable[Mapping[str, float]],
    target: Mapping[str, float],
    measure: Callable[[Mapping[str, float]], Mapping[str, float]],
) -> list[MacroCalibrationResult]:
    """Změří všechny kandidáty a vrátí je od nejbližšího ke globálním datům."""
    results = [
        MacroCalibrationResult(
            parameters=dict(candidate),
            profile=dict(observed := measure(candidate)),
            distance=correspondence_hellinger(observed, target),
        )
        for candidate in candidates
    ]
    return sorted(results, key=lambda result: result.distance)


def deletion_diagnostics(events: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Součet skutečně smazaných segmentů podle schématu, ne podle názvu."""
    deleted: Counter[str] = Counter()
    for event in events:
        if event.get("kind") != "sound_change":
            continue
        amount = int(event.get("deleted_segments", 0) or 0)
        if amount:
            deleted[str(event.get("schema_id", "manual"))] += amount
    return dict(sorted(deleted.items(), key=lambda item: item[1], reverse=True))
