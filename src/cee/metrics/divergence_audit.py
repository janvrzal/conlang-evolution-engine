"""Audit skutečně provedených inovací po jednotlivých větvích."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class BranchDivergenceAudit:
    branch_id: str
    sound_changes: int
    lexical_changes: int
    morphological_changes: int
    contact_events: int
    changed_words: int
    profile: dict[str, float]

    def as_dict(self) -> dict:
        return asdict(self)


def audit_branch_divergence(events: Iterable[Mapping]) -> dict[str, BranchDivergenceAudit]:
    """Agreguje stopu GraphBuilderu; neodhaduje změny z konečných forem."""
    counters: dict[str, Counter] = defaultdict(Counter)
    profiles: dict[str, dict[str, float]] = {}
    for event in events:
        branch = event.get("language_id")
        if not isinstance(branch, str):
            continue
        kind = event.get("kind")
        if kind == "branch_divergence_profile":
            profiles[branch] = {
                key: float(event[key])
                for key in ("phonological_rate", "lexical_rate", "morphological_rate", "contact_permeability")
                if key in event
            }
        elif kind == "sound_change":
            counters[branch]["sound_changes"] += 1
            counters[branch]["changed_words"] += int(event.get("hit_count", 0))
        elif kind == "lexicon":
            counters[branch]["lexical_changes"] += 1
            counters[branch]["changed_words"] += int(event.get("hit_count", 0))
        elif kind == "morphology":
            counters[branch]["morphological_changes"] += 1
            counters[branch]["changed_words"] += int(event.get("hit_count", 0))
        elif kind == "contact":
            counters[branch]["contact_events"] += 1
    branches = set(counters) | set(profiles)
    return {
        branch: BranchDivergenceAudit(
            branch, counters[branch]["sound_changes"], counters[branch]["lexical_changes"],
            counters[branch]["morphological_changes"], counters[branch]["contact_events"],
            counters[branch]["changed_words"], profiles.get(branch, {}),
        )
        for branch in sorted(branches)
    }
