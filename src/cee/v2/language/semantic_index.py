"""Průběžná závislost sémantických míst na dominantních kořenech."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    """Místa jedné rodiny a kurzor sdílených změn."""

    def __init__(self) -> None:
        self.version = -1
        self.config_generation = -1
        self.cursor = 0
        self.found: dict[str, Options] = {}

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
        if self.config_generation != dependencies.config_generation or self.cursor > len(dependencies.changes):
            self.found = {}
            dirty = set(dependencies.sites.values())
        else:
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
        for site in sorted(dirty):
            options = change.options(context, site.split(":", 1)[1])
            if options:
                self.found[site] = options
            else:
                self.found.pop(site, None)
        self.version = state.lexicon_version
        self.cursor = len(dependencies.changes)
        self.config_generation = dependencies.config_generation
        return self.found
