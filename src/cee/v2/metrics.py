"""Metriky realističnosti (specifikace, oddíl Metriky realističnosti)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
import numpy.typing as npt

from cee.v2.history import History

FloatArray = npt.NDArray[np.float64]


def logistic_r2(points: Sequence[tuple[float, float]]) -> float | None:
    """Jak dobře průběh šíření sedí na logistickou křivku (metrika 7).

    Přímka se prokládá logitem frekvence v čase (Kroch 1989); R² se pak
    počítá na původní škále frekvencí. Vrací ``None``, pokud je na proložení
    málo bodů mezi 1 % a 99 %.
    """
    times = np.array([point[0] for point in points], dtype=np.float64)
    values = np.array([point[1] for point in points], dtype=np.float64)
    inner = (values > 0.01) & (values < 0.99)
    if inner.sum() < 4 or np.ptp(times[inner]) == 0:
        return None
    slope, intercept = np.polyfit(times[inner], np.log(values[inner] / (1 - values[inner])), 1)
    predicted = 1.0 / (1.0 + np.exp(-(slope * times + intercept)))
    total = float(((values - values.mean()) ** 2).sum())
    if total == 0:
        return None
    return 1.0 - float(((values - predicted) ** 2).sum()) / total


def establishment_fraction(history: History) -> float:
    """Podíl inovací, které se aspoň v jedné skupině ustálily (metrika 8)."""
    innovations = {event["variant"] for event in history.of_kind("innovation")}
    if not innovations:
        return 0.0
    established = {event["variant"] for event in history.of_kind("established")} & innovations
    return len(established) / len(innovations)


@dataclass(frozen=True)
class DistanceFit:
    """Souvislost jazykové a zeměpisné vzdálenosti (metrika 9, Séguyho zákon)."""

    correlation: float
    r2_linear: float
    r2_log: float

    @property
    def sublinear(self) -> bool:
        return self.r2_log >= self.r2_linear


def _r2(x: FloatArray, y: FloatArray) -> float:
    slope, intercept = np.polyfit(x, y, 1)
    total = float(((y - y.mean()) ** 2).sum())
    return 0.0 if total == 0 else 1.0 - float(((y - (slope * x + intercept)) ** 2).sum()) / total


def isolation_by_distance(
    distances: FloatArray, positions: Sequence[tuple[float, float]]
) -> DistanceFit:
    linguistic, geographic = [], []
    for first in range(len(positions)):
        for second in range(first + 1, len(positions)):
            linguistic.append(distances[first, second])
            geographic.append(math.dist(positions[first], positions[second]))
    y = np.array(linguistic, dtype=np.float64)
    x = np.array(geographic, dtype=np.float64)
    correlation = float(np.corrcoef(x, y)[0, 1]) if y.std() > 0 else 0.0
    return DistanceFit(correlation, _r2(x, y), _r2(np.log(x), y))
