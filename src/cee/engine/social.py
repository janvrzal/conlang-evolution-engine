"""Lehký sociální model: demografie, komunity a dialektní varianty.

Nejde o agentovou simulaci jednotlivých mluvčích. Drží jen parametry, které
mají přímý a auditovatelný dopad na šíření jazykových inovací.
"""

from __future__ import annotations

import hashlib
from typing import Any

from cee.core.models import State, VarietyState


class SocialDynamicsEngine:
    """Aktualizuje dialektní tlak bez kopírování celého lexikonu."""

    @staticmethod
    def enabled(state: State) -> bool:
        return bool(state.communities or state.population.centers > 1)

    @staticmethod
    def _ensure_center_communities(state: State) -> None:
        if state.communities or state.population.centers <= 1:
            return
        count = state.population.centers
        for index in range(count):
            identifier = f"center-{index + 1}"
            # Import zde zabraňuje cyklické závislosti při načtení modelů.
            from cee.core.models import SpeechCommunity

            state.communities[identifier] = SpeechCommunity(
                identifier,
                share=1 / count,
                kind="regional",
                variety_id=f"variety:{identifier}",
            )

    @staticmethod
    def _assign_groups(state: State) -> None:
        """Přiřadí původ inovace deterministicky, bez ovlivnění formy slova."""
        if len(state.communities) < 2:
            return
        communities = sorted(state.communities.values(), key=lambda item: item.id)
        thresholds: list[tuple[float, str]] = []
        cumulative = 0.0
        for community in communities:
            cumulative += community.share
            thresholds.append((cumulative, community.id))
        for word in state.lexicon.words:
            if "social.group" in word.grammatical_features:
                continue
            token = word.lineage_id or word.id or word.concept_id
            fraction = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:12], 16) / 0xFFFFFFFFFFFF
            group = next((item for threshold, item in thresholds if fraction <= threshold), communities[-1].id)
            word.grammatical_features["social.group"] = group

    @staticmethod
    def _cohort_receptivity(community) -> float:
        """Pravděpodobnost přijetí inovace bez předstírání sítě osob."""
        generation = community.generation
        cohort = {"young": 0.18, "adult": 0.08, "mixed": 0.0, "elder": -0.12}.get(generation, 0.0)
        urban = (community.urbanity - 0.5) * 0.22
        return max(-0.25, min(0.35, cohort + urban + (community.mobility - 0.5) * 0.12))

    @staticmethod
    def _advance_cohorts(state: State, year: int) -> list[dict[str, Any]]:
        """Posune agregované kohorty; obnova je auditovatelná po 200 letech."""
        events: list[dict[str, Any]] = []
        sequence = {"young": "adult", "adult": "elder", "elder": "young", "mixed": "young"}
        for community in state.communities.values():
            before = community.generation
            # Mobilní město obměňuje kohorty rychleji než izolovaný venkov.
            community.cohort_age += 0.38 + 0.18 * community.urbanity + 0.08 * community.mobility
            if community.cohort_age < 1.0:
                continue
            community.cohort_age %= 1.0
            community.generation = sequence.get(before, "young")
            events.append({
                "kind": "cohort_turnover", "year": year, "community_id": community.id,
                "from_generation": before, "to_generation": community.generation,
            })
        return events

    def advance(self, state: State, year: int) -> list[dict[str, Any]]:
        self._ensure_center_communities(state)
        if not self.enabled(state):
            return []
        self._assign_groups(state)
        events: list[dict[str, Any]] = []
        events.extend(self._advance_cohorts(state, year))
        isolation = max(0.0, min(1.0, float(state.map.get("isolation", 0.5))))
        mobility = state.social.get("mobility", 0.5)
        standardization = state.social.get("standardization", 0.0)
        # Rozptýlená, izolovaná populace s více centry diverguje rychleji;
        # standard a mobilita ji naopak drží pohromadě.
        density = state.population.size / max(1.0, state.population.area or 1.0)
        sparse_bonus = 0.05 if density < 25 else 0.0
        rate = max(
            0.0,
            0.03 * isolation * (1.0 - mobility * 0.6) * (1.0 - standardization * 0.7)
            + sparse_bonus,
        )
        for community in state.communities.values():
            if not community.variety_id:
                continue
            variety = state.varieties.setdefault(
                community.variety_id, VarietyState(community.variety_id, community.id)
            )
            before = variety.divergence
            settlement = 1.0 + (0.18 if community.kind in {"rural", "regional"} else -0.08 if community.kind == "urban" else 0.0)
            community_rate = rate * (1.15 - 0.3 * community.mobility) * settlement
            variety.divergence = min(1.0, round(variety.divergence + community_rate, 6))
            if before != variety.divergence:
                events.append(
                    {
                        "kind": "variety_divergence",
                        "year": year,
                        "variety_id": variety.id,
                        "community_id": community.id,
                        "divergence": variety.divergence,
                        "rate": round(community_rate, 6),
                    }
                )
            if not variety.split_candidate and variety.divergence >= 0.45:
                variety.split_candidate = True
                events.append(
                    {
                        "kind": "language_split_candidate",
                        "year": year,
                        "variety_id": variety.id,
                        "community_id": community.id,
                        "divergence": variety.divergence,
                        "reason": "persistent regional divergence",
                    }
                )
        # Inovace se mezi propojenými komunitami šíří jako částečné sbližování
        # jejich divergence. Zůstává to lehký model: žádné kopie lexikonu,
        # jen explicitní síť a audit síly difuze.
        for community in state.communities.values():
            if not community.variety_id or not community.links:
                continue
            variety = state.varieties.get(community.variety_id)
            if variety is None:
                continue
            neighbors = [
                (
                    state.communities.get(identifier),
                    max(weight, float(community.bilingualism.get(identifier, 0.0))),
                )
                for identifier, weight in {
                    **community.bilingualism,
                    **community.links,
                }.items()
                if weight > 0
            ]
            neighbors = [(item, weight) for item, weight in neighbors if item and item.variety_id in state.varieties]
            if not neighbors:
                continue
            total = sum(weight for _, weight in neighbors)
            mean = sum(state.varieties[item.variety_id].divergence * weight for item, weight in neighbors) / total
            receptivity = self._cohort_receptivity(community)
            spread = min(0.24, total / max(1, len(neighbors)) * (0.04 + 0.06 * community.mobility + receptivity * 0.08))
            before = variety.divergence
            variety.divergence = round(before + (mean - before) * spread, 6)
            if variety.divergence != before:
                events.append({"kind": "variety_diffusion", "year": year, "variety_id": variety.id, "community_id": community.id, "divergence": variety.divergence, "spread": round(spread, 6), "cohort_receptivity": round(receptivity, 6), "urbanity": community.urbanity})
        return events
