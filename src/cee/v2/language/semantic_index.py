"""Průběžná závislost sémantických míst na dominantních kořenech."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

if TYPE_CHECKING:
    from cee.v2.changes.base import InnovationContext
    from cee.v2.changes.lexicon import SemanticChange

Options = list[tuple[float, dict[str, object]]]


class SemanticDependencies:
    """Sdílená data kódu; žádné odkazy na svět či jeho funkce."""

    def __init__(self) -> None:
        self.version = -1
        self.config: object = None
        self.config_generation = 0
        self.dominant: dict[str, str] = {}
        self.relations: dict[str, set[str]] = {}
        self.compounds: dict[str, set[str]] = {}
        self.sites: dict[str, str] = {}
        self.changes: list[tuple[str, str | None, str | None]] = []
        self.dominant_cursor = self.usage_cursor = self.vocabulary_cursor = 0

    @staticmethod
    def _config(context: InnovationContext) -> object:
        world = context.world
        graph = world.semantics
        return (
            None if graph is None else (graph.relations, tuple(sorted(graph.compounds.items()))),
            tuple(sorted(world.concept_classes.items())), context.group.taboo,
            world.derivational_suffix, tuple(context.code.repertoire.variable_ids_of("lexical")),
        )

    def sync(self, context: InnovationContext) -> None:
        state = context.code.phonology
        if self.version == state.lexicon_version:
            return
        config = self._config(context)
        logs_valid = (self.dominant_cursor <= len(state.dominant_log)
                      and self.usage_cursor <= len(state.usage_log)
                      and self.vocabulary_cursor <= len(state.vocabulary_log))
        if self.version < 0 or config != self.config or not logs_valid:
            self.config_generation += 1
            self.relations.clear()
            self.compounds.clear()
            self.sites = {site.split(":", 1)[1]: site
                          for site in context.code.repertoire.variable_ids_of("lexical")}
            graph = context.world.semantics
            if graph is not None:
                for relation in graph.relations:
                    self.relations.setdefault(relation.source, set()).add(relation.target)
                for target, recipes in graph.compounds.items():
                    for left, right in recipes:
                        self.compounds.setdefault(left, set()).add(target)
                        self.compounds.setdefault(right, set()).add(target)
        # Jediné porovnání pro všechny rodiny zachytí veřejné zápisy mimo deník.
        for concept in sorted(self.dominant.keys() | state.dominant.keys()):
            old, new = self.dominant.get(concept), state.dominant.get(concept)
            if old != new:
                self.changes.append((concept, old, new))
        self.dominant = dict(state.dominant)
        self.version = state.lexicon_version
        self.config = config
        self.dominant_cursor = len(state.dominant_log)
        self.usage_cursor = len(state.usage_log)
        self.vocabulary_cursor = len(state.vocabulary_log)


class SemanticSitesIndex:
    """Místa jedné rodiny, jejich míry a součet pro rychlý dotaz."""

    def __init__(self) -> None:
        self.version = -1
        self.config_generation = -1
        self.cursor = 0
        self.found: dict[str, Options] = {}
        self.site_rates: dict[str, float] = {}
        self.sorted_sites: list[str] = []
        self.rates_array: npt.NDArray[np.float64] = np.array([], dtype=np.float64)
        self._total: float = 0.0
        self._weights: npt.NDArray[np.float64] | None = None
        self._dirty: bool = False

    def sync(self, context: InnovationContext, change: SemanticChange) -> dict[str, Options]:
        state = context.code.phonology
        if self.version == state.lexicon_version:
            return self.found
        key = "semantic-dependencies"
        cached = state.cache.get(key)
        dependencies = SemanticDependencies() if cached is None else cached[1]
        assert isinstance(dependencies, SemanticDependencies)
        dependencies.sync(context)
        state.cache[key] = (state.lexicon_version, dependencies)
        reset = (
            self.version < 0
            or self.config_generation != dependencies.config_generation
            or self.cursor > len(dependencies.changes)
        )
        if reset:
            had_items = bool(self.found)
            self.found.clear()
            self.site_rates.clear()
            dirty = set(dependencies.sites.values())
        else:
            had_items = False
            dirty_concepts: set[str] = set()
            for concept, old, new in dependencies.changes[self.cursor:]:
                if change.kind in ("semantic_shift", "taboo_replacement", "contamination", "back_formation"):
                    dirty_concepts.add(concept)
                if change.kind in ("semantic_shift", "conversion", "derivation",
                                   "taboo_replacement", "contamination"):
                    dirty_concepts.update(dependencies.relations.get(concept, ()))
                if change.kind == "compounding":
                    dirty_concepts.update(dependencies.compounds.get(concept, ()))
                if change.kind == "back_formation":
                    for root in (old, new):
                        if root is not None and root in context.world.morphemes:
                            morpheme = context.world.morphemes[root]
                            if morpheme.etymology == "derivation" and len(morpheme.sources) == 1:
                                dirty_concepts.add(morpheme.sources[0])
            dirty = {dependencies.sites[concept] for concept in dirty_concepts
                     if concept in dependencies.sites}

        changed = had_items
        for site in sorted(dirty):
            options = change.options(context, site.split(":", 1)[1])
            if options:
                new_rate = change.base_rate * sum(weight for weight, _ in options)
                old_rate = self.site_rates.get(site)
                self.found[site] = options
                self.site_rates[site] = new_rate
                if old_rate is None or old_rate != new_rate:
                    changed = True
            else:
                if site in self.found:
                    del self.found[site]
                    del self.site_rates[site]
                    changed = True

        if changed:
            self._dirty = True
            self._weights = None

        self.version = state.lexicon_version
        self.cursor = len(dependencies.changes)
        self.config_generation = dependencies.config_generation
        return self.found

    def ensure_ready(self) -> None:
        """Přepočítá seřazená místa, pole měr a jejich součet jen po skutečné změně indexu."""
        if not self._dirty:
            return
        self.sorted_sites = sorted(self.found)
        self.rates_array = np.fromiter(
            (self.site_rates[s] for s in self.sorted_sites),
            dtype=np.float64,
            count=len(self.sorted_sites),
        )
        self._total = float(np.sum(self.rates_array)) if len(self.rates_array) else 0.0
        self._weights = None
        self._dirty = False
