"""Srovnatelný souhrn více kalibračních scénářů."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from cee.metrics.scenario_calibration import MetricTarget, calibrate_replicates


@dataclass(frozen=True)
class ScenarioComparison:
    scenario_id: str
    score: float
    pairs: dict[str, dict[str, Any]]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_scenarios(
    reports: Mapping[str, Mapping[str, Sequence[Mapping[str, Any]]]],
    targets: Mapping[str, Mapping[str, Sequence[MetricTarget]]],
) -> list[ScenarioComparison]:
    """Vytváří jeden auditovatelný řádek na scénář; nesrovnává holé seedy."""
    result = []
    for scenario_id, pairs in reports.items():
        pair_results, scores, warnings = {}, [], []
        for pair, vectors in pairs.items():
            calibrated = calibrate_replicates(vectors, targets.get(scenario_id, {}).get(pair, ()))
            pair_results[pair] = calibrated.as_dict()
            if calibrated.score != float("inf"):
                scores.append(calibrated.score)
            if any(summary.stddev > 0.12 for summary in calibrated.summaries.values()):
                warnings.append(f"{pair}: vysoký rozptyl mezi seedy")
        result.append(ScenarioComparison(scenario_id, sum(scores) / len(scores) if scores else float("inf"), pair_results, tuple(warnings)))
    return sorted(result, key=lambda item: item.score)
