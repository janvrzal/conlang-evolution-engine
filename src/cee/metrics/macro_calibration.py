"""Výběr makro-parametrů proti nesměrovanému profilu kognátů."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

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
