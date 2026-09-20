"""Vícesedové, vícerozměrné vyhodnocení historických scénářů.

Modul neřídí simulaci k cíli. Pouze agreguje hotové běhy a transparentně
skóruje jejich odchylku od předem zadaných pozorování a kontaktových limitů.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean, median, pstdev
from typing import Any, Callable, Mapping, Sequence

from cee.core.models import State, Word
from cee.metrics.language_distance import compare_languages


def _read_path(value: Mapping[str, Any], path: str) -> float | None:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return float(current) if isinstance(current, (int, float)) else None


@dataclass(frozen=True)
class MetricTarget:
    path: str
    target: float
    tolerance: float
    weight: float = 1.0


@dataclass(frozen=True)
class MetricSummary:
    runs: int
    mean: float
    median: float
    stddev: float


@dataclass(frozen=True)
class CalibrationResult:
    score: float
    components: dict[str, float]
    summaries: dict[str, MetricSummary]

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReplicateReport:
    seeds: tuple[int, ...]
    vectors: dict[str, tuple[dict[str, Any], ...]]

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CalibratedCandidate:
    parameters: dict[str, float]
    result: CalibrationResult


def rank_candidates(
    candidates: Sequence[Mapping[str, float]],
    evaluate: Callable[[Mapping[str, float]], Sequence[Mapping[str, Any]]],
    targets: Sequence[MetricTarget],
) -> list[CalibratedCandidate]:
    """Deterministicky seřadí parametry podle víceseedového vektoru, ne seedů."""
    ranked = [CalibratedCandidate(dict(candidate), calibrate_replicates(evaluate(candidate), targets)) for candidate in candidates]
    return sorted(ranked, key=lambda item: item.result.score)


def run_replicates(
    seeds: Sequence[int],
    simulate: Callable[[int], Mapping[str, State]],
    pairs: Sequence[tuple[str, str]],
    render: Callable[[Word], str],
) -> ReplicateReport:
    """Spustí tutéž topologii přes více seedů bez sdíleného mutovatelného stavu."""
    if not seeds:
        raise ValueError("Je potřeba alespoň jeden seed.")
    grouped: dict[str, list[dict[str, Any]]] = {f"{left}-{right}": [] for left, right in pairs}
    for seed in seeds:
        states = simulate(seed)
        for left, right in pairs:
            if left not in states or right not in states:
                raise ValueError(f"Běh seed {seed} nevrátil dvojici {left}-{right}.")
            grouped[f"{left}-{right}"].append(compare_languages(states[left], states[right], render).as_dict())
    return ReplicateReport(tuple(seeds), {pair: tuple(values) for pair, values in grouped.items()})


def calibrate_replicates(
    vectors: Sequence[Mapping[str, Any]], targets: Sequence[MetricTarget]
) -> CalibrationResult:
    """Skóruje medián více seedů; rozptyl zůstává viditelný v reportu.

    Každá metrika je samostatný komponent. Kontaktní doménové limity lze
    vyjádřit stejným mechanismem, například ``contact_left.loan_ratio``.
    """
    if not vectors:
        raise ValueError("Kalibrace potřebuje alespoň jeden výsledek běhu.")
    summaries: dict[str, MetricSummary] = {}
    components: dict[str, float] = {}
    weighted: list[tuple[float, float]] = []
    for target in targets:
        values = [item for vector in vectors if (item := _read_path(vector, target.path)) is not None]
        if not values:
            continue
        summary = MetricSummary(len(values), mean(values), median(values), pstdev(values) if len(values) > 1 else 0.0)
        summaries[target.path] = summary
        deviation = abs(summary.median - target.target) / max(target.tolerance, 1e-9)
        components[target.path] = deviation
        weighted.append((deviation, max(0.0, target.weight)))
    score = sum(value * weight for value, weight in weighted) / sum(weight for _, weight in weighted) if weighted and sum(weight for _, weight in weighted) else float("inf")
    return CalibrationResult(score, components, summaries)
