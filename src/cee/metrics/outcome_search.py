"""Jednoduché simulované hledání parametrů proti outcome intervalům."""

from __future__ import annotations

import copy
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from cee.engine.parser import YamlParser
from cee.metrics.outcomes import measure_state_outcome
from cee.pipeline import SimulationConfig, get_feature_mapper, load_lexicon_from_csv, run_simulation


@dataclass(frozen=True)
class OutcomeCandidate:
    parameters: dict[str, float]
    metrics: dict[str, float]
    score: float
    inside_intervals: int
    compared_metrics: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def load_target_group(path: str | Path, kind: str, group_id: str) -> dict[str, Mapping[str, Any]]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    for group in document.get("groups", []):
        if group.get("kind") == kind and group.get("id") == group_id:
            return dict(group.get("metrics", {}))
    raise ValueError(f"Outcome profil nemá skupinu {kind}:{group_id}.")


def score_metrics(
    metrics: Mapping[str, float], target: Mapping[str, Mapping[str, Any]]
) -> tuple[float, int, int]:
    """Nulu dává kandidát uvnitř všech dostupných 95% intervalů.

    Mimo interval se vzdálenost normalizuje jeho poloviční šířkou. Není-li
    interval dostupný, používá se standardní odchylka pozorovaného vzorku.
    """
    distances = []
    inside = 0
    for metric, value in metrics.items():
        reference = target.get(metric)
        if not reference:
            continue
        interval = reference.get("interval_95")
        if interval:
            low, high = float(interval[0]), float(interval[1])
            if low <= value <= high:
                inside += 1
                distances.append(0.0)
                continue
            scale = max((high - low) / 2, 1e-9)
            distances.append(min(abs(value - (low if value < low else high)) / scale, 10.0))
        else:
            scale = max(float(reference.get("standard_deviation", 0.0)), 1e-9)
            distances.append(min(abs(value - float(reference["mean"])) / scale, 10.0))
    return (sum(distances) / len(distances) if distances else float("inf"), inside, len(distances))


def _leaf_states(states, graph):
    parents = {edge.parent_id for edge in graph.vertical_edges}
    return [state for node_id, state in states.items() if node_id not in parents]


def _candidate_preset(base: Mapping[str, Any], parameters: Mapping[str, float]) -> dict[str, Any]:
    preset = copy.deepcopy(base)
    preset.setdefault("macro", {}).update(parameters)
    return preset


def search_macro_parameters(
    target: Mapping[str, Mapping[str, Any]],
    topology_path: str | Path,
    proto_csv: str | Path,
    preset_path: str | Path,
    years: int,
    trials: int,
    replicates: int,
    seed: int,
) -> list[OutcomeCandidate]:
    """Vyhledá počáteční makro-parametry nad zadaným scénářem.

    Nejde o rekonstrukci historie: pro každý kandidát znovu simuluje celý
    scénář přes více seedů a porovnává průměr jeho listových jazyků s cílem.
    """
    if trials < 1 or replicates < 1:
        raise ValueError("trials i replicates musí být kladné.")
    rng = random.Random(seed)
    mapper = get_feature_mapper()
    base_preset = YamlParser.parse_preset(str(preset_path))
    candidates = []
    for trial in range(trials):
        parameters = {
            "change_rate": round(rng.uniform(0.4, 1.8), 4),
            "coda_erosion": round(rng.uniform(0.25, 2.5), 4),
            "deletion_rate": round(rng.uniform(0.1, 1.0), 4),
        }
        measured = []
        for replicate in range(replicates):
            graph = YamlParser.parse_topology(str(topology_path))
            lexicon = load_lexicon_from_csv(str(proto_csv), mapper)
            states = run_simulation(
                lexicon,
                graph,
                mapper,
                SimulationConfig(
                    preset=_candidate_preset(base_preset, parameters),
                    seed=seed + trial * replicates + replicate,
                    years=years,
                    enable_semantics=False,
                ),
            )
            measured.extend(measure_state_outcome(state, mapper) for state in _leaf_states(states, graph))
        common = set.intersection(*(set(metrics) for metrics in measured)) if measured else set()
        averages = {
            metric: sum(metrics[metric] for metrics in measured) / len(measured) for metric in common
        }
        score, inside, compared = score_metrics(averages, target)
        candidates.append(OutcomeCandidate(parameters, averages, score, inside, compared))
    return sorted(candidates, key=lambda candidate: (candidate.score, -candidate.inside_intervals))
