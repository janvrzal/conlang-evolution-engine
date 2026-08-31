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

    def advance(self, state: State, year: int) -> list[dict[str, Any]]:
        self._ensure_center_communities(state)
        if not self.enabled(state):
            return []
        self._assign_groups(state)
        events: list[dict[str, Any]] = []
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
            community_rate = rate * (1.15 - 0.3 * community.mobility)
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
        return events
