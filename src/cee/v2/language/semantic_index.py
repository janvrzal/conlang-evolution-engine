"""Sémantické závislosti a místa sémantických změn na číslech (krok B5b, Python reference).

Dřív držela ``SemanticDependencies`` dominantní kořeny, vztahy, složeniny a místa jako
řetězce a ``SemanticSitesIndex`` pro každou rodinu změn slovníky možností po místech.
Tady je totéž jako čísla; Rust (``cee_core.SiteIndex``, ``rust/cee_core/src/semantic_index.rs``)
je přepisuje 1:1 a tyto třídy jsou jeho fallback (``CEE_NATIVE=0``) a reference testu.

Místem sémantické změny je pojem, který má kód mezi lexikálními proměnnými, a míra místa je
``base_rate × součet vah cest k pojmu``. Cesty plynou z grafu pojmů (vztahy vedoucí do pojmu,
recepty složenin), z dominantních kořenů kódu (číslo kořene podle čísla pojmu, −1 = žádný),
z tabu skupiny a z vlastností kořenů (odvozenina, základ). Váhy vztahů, které by potřebovaly
``log1p`` (posun, konverze, odvození), a shodnost slovních druhů jsou v grafu předem spočítané,
takže součty vah jsou prosté součty v pořadí vztahů jako dřív (``sum`` od nuly).

**Přírůstkově.** Změna dominantního kořene pojmu dotkne jen pojmů, které na něm závisejí (sám
pojem, cíle jeho vztahů a složenin, pojem, ze kterého je odvozen starý či nový kořen); ty se
přepočítají pro všechny druhy změn. Změna grafu, tabu, přípony či množiny míst přepočítá vše.
Výsledek je čistá funkce stavu, takže se vždy shoduje s úplným přepočtem. Místa jsou seřazená
podle jmen pojmů, míry se sčítají párově (``np.sum``) jen přes místa.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from cee.v2 import phases

#: Pořadí druhů sémantických změn: posun, konverze, odvození, složenina, opis za tabu,
#: kontaminace, zpětné tvoření (jako ``LEXICAL_CHANGES``).
KINDS = ("semantic_shift", "conversion", "derivation", "compounding", "taboo_replacement",
         "contamination", "back_formation")
SHIFT, CONVERSION, DERIVATION, COMPOUNDING, TABOO, CONTAMINATION, BACK_FORMATION = range(7)

#: Příznaky vztahu.
COMPATIBLE, POLYSEMOUS, COLEXIFIED = 1, 2, 4
#: Vlastnost kořene dosud neznámá (doplní volající).
UNKNOWN = -2


class Graph:
    """Graf pojmů v řídkých řádcích podle cíle (vztahy každého cíle seřazené podle jména zdroje)."""

    def __init__(
        self, concepts: int, into_start: Any, source: Any, shift: Any, conversion: Any, derivation: Any,
        flags: Any, compound_start: Any, left: Any, right: Any,
    ) -> None:
        self.concepts = concepts
        self.into_start = [int(x) for x in into_start]
        self.source = [int(x) for x in source]
        self.shift = [float(x) for x in shift]
        self.conversion = [float(x) for x in conversion]
        self.derivation = [float(x) for x in derivation]
        self.flags = [int(x) for x in flags]
        self.compound_start = [int(x) for x in compound_start]
        self.left = [int(x) for x in left]
        self.right = [int(x) for x in right]
        affected: list[set[int]] = [set() for _ in range(concepts)]
        for target in range(concepts):
            for relation in range(self.into_start[target], self.into_start[target + 1]):
                if 0 <= self.source[relation] < concepts:
                    affected[self.source[relation]].add(target)
            for item in range(self.compound_start[target], self.compound_start[target + 1]):
                for part in (self.left[item], self.right[item]):
                    if 0 <= part < concepts:
                        affected[part].add(target)
        self.affected = [sorted(items) for items in affected]

    def relations(self, target: int) -> range:
        if target >= self.concepts:
            return range(0)
        return range(self.into_start[target], self.into_start[target + 1])

    def compounds(self, target: int) -> range:
        if target >= self.concepts:
            return range(0)
        return range(self.compound_start[target], self.compound_start[target + 1])


class _Slot:
    def __init__(self) -> None:
        self.synced = False
        self.graph_version = -1
        self.suffix = False
        self.dominant: list[int] = []
        self.site: list[bool] = []
        self.taboo: list[bool] = []
        #: Součet vah cest podle pojmu pro každý druh změny (0 = pojem není místem).
        self.sums: list[list[float]] = [[] for _ in KINDS]
        #: Pojem → pojmy, jejichž dominantní kořen je odvozenina z něj.
        self.derived: dict[int, list[int]] = {}
        self.compact: list[list[float]] = [[] for _ in KINDS]
        self.total = [0.0] * len(KINDS)
        self.base = [0.0] * len(KINDS)
        self.ready = [False] * len(KINDS)


class SemanticDependencies:
    """Graf pojmů, vlastnosti kořenů a závislosti míst každého kódu na dominantních kořenech."""

    def __init__(self) -> None:
        self.concepts: list[str] = []
        self.graph = Graph(0, [0], [], [], [], [], [], [0], [], [])
        self.graph_version = 0
        self._by_name: list[int] = []
        self._sorted_for = -1
        #: Kořen → pojem, ze kterého je odvozen (−1 = není odvozenina z jediného pojmu), a základ.
        self.root_source: dict[int, int] = {}
        self.root_base: dict[int, int] = {}
        self.slots: dict[int, _Slot] = {}

    def set_names(self, concepts: list[str]) -> None:
        self.concepts.extend(concepts)

    def set_graph(self, graph: Graph) -> None:
        self.graph = graph
        self.graph_version += 1

    def set_roots(self, numbers: list[int], sources: list[int], bases: list[int]) -> None:
        for number, source, base in zip(numbers, sources, bases):
            self.root_source[number], self.root_base[number] = int(source), int(base)

    def _known(self, root: int) -> bool:
        return root < 0 or root in self.root_source

    def _source_of(self, root: int) -> int:
        return -1 if root < 0 else max(self.root_source.get(root, -1), -1)

    def _base_of(self, root: int) -> int:
        return -1 if root < 0 else self.root_base.get(root, -1)

    @property
    def by_name(self) -> list[int]:
        """Pojmy seřazené podle jména."""
        if self._sorted_for != len(self.concepts):
            self._by_name = sorted(range(len(self.concepts)), key=self.concepts.__getitem__)
            self._sorted_for = len(self.concepts)
        return self._by_name

    def sync(
        self, tokens: list[int], dominants: list[Any], sites: list[Any], taboos: list[Any], suffixes: list[bool],
    ) -> list[int]:
        """Dorovná kódy; vrací čísla kořenů, jejichž vlastnosti je třeba doplnit (pak znovu)."""
        needs: set[int] = set()
        for token, dominant, site, taboo, suffix in zip(tokens, dominants, sites, taboos, suffixes):
            needs.update(self._sync_code(token, dominant, site, taboo, suffix))
        return sorted(needs)

    def _sync_code(self, token: int, dominant_in: Any, sites_in: Any, taboo_in: Any, suffix: bool) -> list[int]:
        concepts = max(self.graph.concepts, len(self.concepts))
        dominant = [int(x) for x in dominant_in] + [-1] * (concepts - len(dominant_in))
        site = [False] * concepts
        for concept in sites_in:
            if 0 <= concept < concepts:
                site[concept] = True
        taboo = [False] * concepts
        for concept in taboo_in:
            if 0 <= concept < concepts:
                taboo[concept] = True
        slot = self.slots.setdefault(token, _Slot())
        reset = (not slot.synced or slot.graph_version != self.graph_version or slot.suffix != suffix
                 or len(slot.dominant) != concepts or slot.taboo != taboo or slot.site != site)
        changed: list[int] = []
        needs: set[int] = set()
        for concept in range(concepts):
            old = -1 if reset else slot.dominant[concept]
            if reset or old != dominant[concept]:
                changed.append(concept)
                for root in (old, dominant[concept]):
                    if not self._known(root):
                        needs.add(root)
        if needs:
            return sorted(needs)
        if reset:
            dirty = list(range(concepts))
        else:
            marked: set[int] = set()
            for concept in changed:
                marked.add(concept)
                marked.update(self.graph.affected[concept] if concept < self.graph.concepts else ())
                for root in (slot.dominant[concept], dominant[concept]):
                    source = self._source_of(root)
                    if source >= 0:
                        marked.add(source)
            dirty = sorted(marked)
        derived: dict[int, list[int]] = {}
        for concept, root in enumerate(dominant):
            source = self._source_of(root)
            if 0 <= source < concepts:
                derived.setdefault(source, []).append(concept)
        sums = [[0.0] * concepts if reset or len(slot.sums[kind]) != concepts else slot.sums[kind]
                for kind in range(len(KINDS))]
        for concept in dirty:
            for kind in range(len(KINDS)):
                sums[kind][concept] = self._sum(kind, concept, dominant, taboo, suffix, derived)
        slot.sums, slot.derived = sums, derived
        slot.dominant, slot.site, slot.taboo, slot.suffix = dominant, site, taboo, suffix
        slot.graph_version = self.graph_version
        slot.ready = [False] * len(KINDS)
        slot.synced = True
        return []

    def _sum(
        self, kind: int, target: int, dominant: list[int], taboo: list[bool], suffix: bool,
        derived: dict[int, list[int]],
    ) -> float:
        """Součet vah cest ke pojmu ``target`` (po vztazích v pořadí, od nuly); 0 bez cest."""
        graph = self.graph

        def root(concept: int) -> int:
            return dominant[concept] if 0 <= concept < len(dominant) else -1

        current = dominant[target] if target < len(dominant) else -1
        total = 0.0
        if kind == COMPOUNDING:
            for item in graph.compounds(target):
                if root(graph.left[item]) >= 0 and root(graph.right[item]) >= 0:
                    total += 1.0
            return total
        if kind == BACK_FORMATION:
            for other in derived.get(target, ()):
                if other != target and current != self._base_of(dominant[other]):
                    total += 1.0
            return total
        if kind == DERIVATION and not suffix:
            return 0.0
        if kind == CONTAMINATION and current < 0:
            return 0.0
        if kind == TABOO and not (target < len(taboo) and taboo[target]):
            return 0.0
        found = False
        for relation in graph.relations(target):
            source = root(graph.source[relation])
            flags = graph.flags[relation]
            if kind == SHIFT:
                if source < 0 or source == current or not flags & COMPATIBLE or graph.shift[relation] <= 0.0:
                    continue
                weight = graph.shift[relation]
            elif kind == CONVERSION:
                if source < 0 or flags & COMPATIBLE or not flags & POLYSEMOUS:
                    continue
                weight = graph.conversion[relation]
            elif kind == DERIVATION:
                if source < 0 or graph.derivation[relation] <= 0.0:
                    continue
                weight = graph.derivation[relation]
            elif kind == TABOO:
                if source < 0 or source == current:
                    continue
                weight = 1.0
            else:
                if source < 0 or source == current or not flags & COLEXIFIED:
                    continue
                weight = 1.0
            found = True
            total += weight
        if kind == TABOO and not found:
            total += 1.0  # bez příbuzného slova se hledá nový opis: jediná cesta
        return total


class SemanticSitesIndex:
    """Místa, míry a součty míst sémantických změn (čtení nad ``SemanticDependencies``)."""

    def __init__(self, dependencies: SemanticDependencies) -> None:
        self._dependencies = dependencies

    def _prepare(self, token: int, kind: int, base: float) -> _Slot | None:
        slot = self._dependencies.slots.get(token)
        if slot is None:
            return None
        if slot.ready[kind] and slot.base[kind] == base:
            return slot
        compact = [
            base * slot.sums[kind][concept] for concept in self._dependencies.by_name
            if concept < len(slot.site) and slot.site[concept] and slot.sums[kind][concept] > 0.0
        ]
        slot.compact[kind] = compact
        slot.total[kind] = phases.rate_total(compact) if compact else 0.0
        slot.base[kind], slot.ready[kind] = base, True
        return slot

    def count_total(self, token: int, kind: int, base: float) -> tuple[int, float]:
        slot = self._prepare(token, kind, base)
        return (0, 0.0) if slot is None else (len(slot.compact[kind]), slot.total[kind])

    def rates(self, token: int, kind: int, base: float) -> np.ndarray:
        slot = self._prepare(token, kind, base)
        return np.array([] if slot is None else slot.compact[kind], dtype=np.float64)

    def sites(self, token: int, kind: int) -> list[int]:
        """Čísla pojmů míst v pořadí jmen pojmů."""
        slot = self._dependencies.slots.get(token)
        if slot is None:
            return []
        return [
            concept for concept in self._dependencies.by_name
            if concept < len(slot.site) and slot.site[concept] and slot.sums[kind][concept] > 0.0
        ]

    def dominant(self, token: int) -> list[int]:
        slot = self._dependencies.slots.get(token)
        return [] if slot is None else list(slot.dominant)
