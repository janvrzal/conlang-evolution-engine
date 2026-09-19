"""Životní cyklus postupných sémantických inovací.

Modul drží stav rozběhnutých změn mimo hlavní simulátor. Orchestrátor pouze
předává události na společné časové ose; zde se řeší jejich návrh, dědění,
fázování a dopad na lexikon.
"""

import copy
import inspect
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
        context=None,
        approval_mode: str = "auto",
        approved_changes: Optional[set[str]] = None,
        innovation_group: Optional[str] = None,
        graph_builder=None,
    ) -> None:
        parameters = inspect.signature(evaluator.propose_changes).parameters
        kwargs = {"random_gen": random_gen}
        if "context" in parameters:
            kwargs["context"] = context
        proposals = evaluator.propose_changes(state.lexicon, **kwargs)
        approved_changes = approved_changes or set()
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
            proposal_key = f"{proposal.source_concept}->{proposal.target_concept or '∅'}"
            if approval_mode == "review" and proposal_key not in approved_changes:
                if graph_builder:
                    graph_builder.add_event(
                        "semantic_proposal",
                        year,
                        state.node_id,
                        proposal_key=proposal_key,
                        source_concept=proposal.source_concept,
                        target_concept=proposal.target_concept,
                        change_kind=proposal.kind,
                        pressure=proposal.pressure,
                        mechanism=proposal.mechanism,
                        reason=proposal.context_reason,
                        status="pending",
                    )
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
                    competitor_lineage_id=proposal.competitor_lineage_id,
                    mechanism=proposal.mechanism,
                    mechanism_pressure=proposal.mechanism_pressure,
                    mechanism_reason=proposal.mechanism_reason,
                    context_pressure=proposal.context_pressure,
                    context_reason=proposal.context_reason,
                    innovation_group=innovation_group,
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
                competitor_lineage_id=change.competitor_lineage_id,
                mechanism=change.mechanism,
                mechanism_pressure=change.mechanism_pressure,
                mechanism_reason=change.mechanism_reason,
                context_pressure=change.context_pressure,
                context_reason=change.context_reason,
                innovation_group=change.innovation_group,
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

    def transfer_contact(
        self,
        source: State,
        target: State,
        year: int,
        strength: float,
        push,
        priority: int,
        graph_builder=None,
    ) -> int:
        """Přenese živou významovou variantu přes doložený kontakt.

        Cílový jazyk dostane vlastní časovanou variantu nad svým lexémem pro
        tentýž výchozí koncept. Kontakt ji jen založí a zváží; komunity cíle
        rozhodnou o jejím přijetí.
        """
        transferred = 0
        for change in list(self.changes.values()):
            if change.branch_id != source.node_id or not change.introduced:
                continue
            if not (change.year <= year < change.year + change.duration):
                continue
            target_word = next(
                (
                    word for word in target.lexicon.words
                    if word.active
                    and change.source_concept
                    in {word.concept_id.lower(), *(value.lower() for value in word.polysemy)}
                ),
                None,
            )
            if target_word is None:
                continue
            change_id = f"contact:{source.node_id}:{target.node_id}:{year}:{change.change_id}"
            if change_id in self.changes:
                continue
            imported = copy.copy(change)
            imported.change_id = change_id
            imported.branch_id = target.node_id
            imported.word_lineage_id = target_word.lineage_id or target_word.id
            imported.year = year
            imported.duration = max(80, change.year + change.duration - year)
            imported.pressure = round(max(0.05, min(1.0, change.pressure * strength)), 6)
            imported.evidence_type = "contact-calque"
            imported.mechanism = "contact_calque"
            imported.mechanism_reason = f"semantic variant from {source.node_id}"
            imported.introduced = False
            push(year, priority, imported)
            transferred += 1
            if graph_builder:
                graph_builder.add_event(
                    "semantic_contact_variant",
                    year,
                    target.node_id,
                    source_language=source.node_id,
                    source_change_id=change.change_id,
                    target_change_id=change_id,
                    source_concept=change.source_concept,
                    target_concept=change.target_concept,
                    strength=round(strength, 4),
                )
        return transferred

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
        effective_progress, community_adoption = self._community_progress(state, change, progress)
        phase = "diffusing"
        if change.kind == "loss" and not change.introduced:
            if effective_progress >= change.adoption_threshold:
                change.introduced = True
                phase = "receding"
        elif not change.introduced and effective_progress >= change.adoption_threshold:
            assert change.target_concept is not None
            word.polysemy.add(change.target_concept)
            change.introduced = True
            phase = "coexisting"

        if change.kind == "loss" and effective_progress >= 1.0:
            competitor = next(
                (
                    item
                    for item in state.lexicon.words
                    if item.active
                    and item.lineage_id == change.competitor_lineage_id
                    and change.source_concept
                    in {item.concept_id.lower(), *(value.lower() for value in item.polysemy)}
                ),
                None,
            )
            if competitor is None:
                phase = "cancelled"
            else:
                if change.source_concept in {item.lower() for item in word.polysemy}:
                    word.polysemy = {
                        item for item in word.polysemy if item.lower() != change.source_concept
                    }
                elif word.concept_id.lower() == change.source_concept:
                    if word.polysemy:
                        replacement = min(word.polysemy)
                        word.polysemy.remove(replacement)
                        word.concept_id = replacement
                    else:
                        word.active = False
                phase = "completed"
        elif change.kind == "shift" and effective_progress >= 1.0 and change.introduced:
            assert change.target_concept is not None
            if word.concept_id.lower() == change.source_concept:
                word.concept_id = change.target_concept
                word.polysemy.discard(change.target_concept)
                word.polysemy.discard(change.source_concept)
            phase = "completed"
        elif effective_progress >= 1.0:
            phase = "completed"

        hit_count = record_changes(
            state,
            before,
            year,
            "semantic_shift",
            (
                f"loss of {change.source_concept}"
                if change.kind == "loss"
                else f"{change.source_concept} > {change.target_concept} ({change.kind})"
            ),
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
                competitor_lineage_id=change.competitor_lineage_id,
                mechanism=change.mechanism,
                mechanism_pressure=change.mechanism_pressure,
                mechanism_reason=change.mechanism_reason,
                context_pressure=change.context_pressure,
                context_reason=change.context_reason,
                progress=round(progress, 4),
                effective_progress=round(effective_progress, 4),
                community_adoption=community_adoption,
                phase=phase,
                hit_count=hit_count,
            )
        if progress >= 1.0:
            self.changes.pop(change.change_id, None)

    @staticmethod
    def _community_progress(
        state: State, change: SemanticChangeEvent, progress: float
    ) -> tuple[float, dict[str, float]]:
        """Rozšíří významovou variantu v lehké síti komunit.

        Společný lexikon se změní teprve po úplném přijetí ve všech významných
        komunitách. Lokální inovace proto zůstane doloženou varietní variantou
        místo falešně plošné změny celého jazyka.
        """
        if not state.communities:
            return progress, {}
        origin_id = change.innovation_group
        if origin_id not in state.communities:
            origin_id = max(
                state.communities,
                key=lambda key: state.communities[key].share * (0.5 + state.communities[key].prestige),
            )
        adoption = state.semantic_adoptions.setdefault(change.change_id, {})
        origin = state.communities[origin_id]
        adoption[origin_id] = max(adoption.get(origin_id, 0.0), progress)
        for community_id, community in state.communities.items():
            if community_id == origin_id:
                continue
            exposure = max(
                float(origin.links.get(community_id, 0.0)),
                float(community.links.get(origin_id, 0.0)),
                float(origin.bilingualism.get(community_id, 0.0)),
                float(community.bilingualism.get(origin_id, 0.0)),
            )
            receptivity = 0.35 + 0.35 * community.mobility + 0.3 * community.urbanity
            # Silně propojené centrum může inovaci do konce období plně
            # přijmout; slabší síť ji zpomalí místo svévolného zákazu.
            spread_factor = exposure ** (2.0 - receptivity) if exposure else 0.0
            adoption[community_id] = max(
                adoption.get(community_id, 0.0), min(progress, progress * spread_factor)
            )
        weighted = sum(
            community.share * adoption.get(community_id, 0.0)
            for community_id, community in state.communities.items()
        )
        if all(value >= 0.999 for value in adoption.values()):
            weighted = 1.0
        return min(1.0, weighted), {key: round(value, 4) for key, value in adoption.items()}
