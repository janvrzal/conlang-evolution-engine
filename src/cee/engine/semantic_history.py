"""Životní cyklus postupných sémantických inovací.

Modul drží stav rozběhnutých změn mimo hlavní simulátor. Orchestrátor pouze
předává události na společné časové ose; zde se řeší jejich návrh, dědění,
fázování a dopad na lexikon.
"""

import copy
import math
from typing import Callable, Optional

from cee.core.models import State
from cee.engine.events import SemanticChangeEvent, SemanticChangeSpreadEvent

SEMANTIC_SPREAD_PHASE_YEARS = 40


class SemanticChangeRuntime:
    """Spravuje aktivní významové změny během jednoho běhu simulace."""

    def __init__(self) -> None:
        self.changes: dict[str, SemanticChangeEvent] = {}
        self.sequence = 0

    def schedule_proposals(
        self,
        state: State,
        year: int,
        evaluator,
        random_gen,
        push,
        priority: int,
        horizon: int,
    ) -> None:
        proposals = evaluator.propose_changes(state.lexicon, random_gen=random_gen)
        active_lineages = {
            change.word_lineage_id
            for change in self.changes.values()
            if change.branch_id == state.node_id
        }
        for proposal in proposals:
            if proposal.word_lineage_id in active_lineages:
                continue
            word = next(
                (
                    item
                    for item in state.lexicon.words
                    if item.active and item.lineage_id == proposal.word_lineage_id
                ),
                None,
            )
            if word is None:
                continue
            self.sequence += 1
            change_id = f"{state.node_id}:{year}:semantic:{self.sequence}"
            push(
                year,
                priority,
                SemanticChangeEvent(
                    year=year,
                    branch_id=state.node_id,
                    change_id=change_id,
                    word_lineage_id=proposal.word_lineage_id,
                    source_concept=proposal.source_concept,
                    target_concept=proposal.target_concept,
                    kind=proposal.kind,
                    duration=min(proposal.duration(), max(0, horizon - year)),
                    pressure=proposal.pressure,
                    evidence_weight=proposal.evidence_weight,
                    evidence_type=proposal.evidence_type,
                    adoption_threshold=proposal.adoption_threshold(word.frequency),
                ),
            )
            active_lineages.add(proposal.word_lineage_id)

    def start(
        self,
        state: State,
        change: SemanticChangeEvent,
        push,
        priority: int,
        record_changes: Callable,
        word_versions: Callable,
        graph_builder=None,
    ) -> None:
        self.changes[change.change_id] = change
        if graph_builder:
            graph_builder.add_event(
                "semantic_change_started",
                change.year,
                change.branch_id,
                change_id=change.change_id,
                source_concept=change.source_concept,
                target_concept=change.target_concept,
                change_kind=change.kind,
                duration=change.duration,
                pressure=change.pressure,
                evidence_weight=change.evidence_weight,
                evidence_type=change.evidence_type,
            )
        phases = max(1, math.ceil(change.duration / SEMANTIC_SPREAD_PHASE_YEARS))
        self._propagate(
            state,
            change,
            1 / phases,
            change.year,
            record_changes,
            word_versions,
            graph_builder,
        )
        self._schedule_spread(change, push, priority)

    def spread(
        self,
        state: State,
        event: SemanticChangeSpreadEvent,
        record_changes: Callable,
        word_versions: Callable,
        graph_builder=None,
    ) -> None:
        change = self.changes.get(event.change_id)
        if change is not None:
            self._propagate(
                state,
                change,
                event.progress,
                event.year,
                record_changes,
                word_versions,
                graph_builder,
            )

    def inherit(self, parent_id: str, child_id: str, year: int, push, priority: int) -> None:
        """Potomek pokračuje v rozběhnutých inovacích rodiče."""
        inherited = [
            change
            for change in self.changes.values()
            if change.branch_id == parent_id and change.year < year < change.year + change.duration
        ]
        for change in inherited:
            child_change = copy.copy(change)
            child_change.branch_id = child_id
            child_change.change_id = f"{change.change_id}:fork:{child_id}"
            self.changes[child_change.change_id] = child_change
            self._schedule_spread(child_change, push, priority, after_year=year)

    @staticmethod
    def _schedule_spread(
        change: SemanticChangeEvent,
        push,
        priority: int,
        *,
        after_year: Optional[int] = None,
    ) -> None:
        if change.duration <= 0:
            return
        phases = max(1, math.ceil(change.duration / SEMANTIC_SPREAD_PHASE_YEARS))
        for phase in range(2, phases + 1):
            progress = phase / phases
            year = change.year + int(round(change.duration * progress))
            if after_year is not None and year <= after_year:
                continue
            push(
                year,
                priority,
                SemanticChangeSpreadEvent(year, change.branch_id, change.change_id, progress),
            )

    def _propagate(
        self,
        state: State,
        change: SemanticChangeEvent,
        progress: float,
        year: int,
        record_changes: Callable,
        word_versions: Callable,
        graph_builder=None,
    ) -> None:
        state.year = year
        word = next(
            (
                item
                for item in state.lexicon.words
                if item.active and item.lineage_id == change.word_lineage_id
            ),
            None,
        )
        if word is None:
            if progress >= 1.0:
                self.changes.pop(change.change_id, None)
            return

        before = word_versions(state)
        phase = "diffusing"
        if not change.introduced and progress >= change.adoption_threshold:
            word.polysemy.add(change.target_concept)
            change.introduced = True
            phase = "coexisting"

        if change.kind == "shift" and progress >= 1.0 and change.introduced:
            if word.concept_id.lower() == change.source_concept:
                word.concept_id = change.target_concept
                word.polysemy.discard(change.target_concept)
                word.polysemy.discard(change.source_concept)
            phase = "completed"
        elif progress >= 1.0:
            phase = "completed"

        hit_count = record_changes(
            state,
            before,
            year,
            "semantic_shift",
            f"{change.source_concept} > {change.target_concept} ({change.kind})",
        )
        if graph_builder:
            graph_builder.add_event(
                "semantic_change_progress",
                year,
                state.node_id,
                change_id=change.change_id,
                source_concept=change.source_concept,
                target_concept=change.target_concept,
                change_kind=change.kind,
                progress=round(progress, 4),
                phase=phase,
                hit_count=hit_count,
            )
        if progress >= 1.0:
            self.changes.pop(change.change_id, None)
