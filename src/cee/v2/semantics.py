"""Graf pojmů pro lexikální změny (milník M3b).

Výřez CLICS⁴ a DatSemShift pro základní slovní zásobu je přibalený v
``cee/data/v2_core_semantics.json`` (CC BY 4.0, citace a SHA-256 vstupů
uvnitř; vzniká skriptem ``scripts/build_v2_core_semantics.py``). Simulace
proto nepotřebuje síť ani lokální cache.

Vztah je *doklad*, ne příkaz: říká, že slovo pro pojem A se v mnoha rodinách
jazyků stalo slovem pro pojem B (posun), že B se z A odvozuje (odvození),
nebo že jazyky A a B vyjadřují jedním slovem (kolexifikace). Váhy jsou
počty rodin, resp. jazyků.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "v2_core_semantics.json"


@dataclass(frozen=True)
class Relation:
    source: str
    target: str
    polysemy: int = 0
    derivation: int = 0
    colexification: int = 0

    @property
    def shift_weight(self) -> float:
        """Síla dokladu pro posun významu A → B (kolexifikace váží méně)."""
        return math.log1p(self.polysemy) + math.log1p(self.colexification) / 3.0

    @property
    def derivation_weight(self) -> float:
        return math.log1p(self.derivation)


@dataclass(frozen=True)
class ConceptGraph:
    relations: tuple[Relation, ...]
    #: Recepty složenin: pojem → (hlava, určení).
    compounds: dict[str, tuple[tuple[str, str], ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        incoming: dict[str, list[Relation]] = {}
        for relation in self.relations:
            incoming.setdefault(relation.target, []).append(relation)
        object.__setattr__(self, "_incoming", incoming)
        pairs = {frozenset((relation.source, relation.target)) for relation in self.relations}
        object.__setattr__(self, "_pairs", pairs)

    def into(self, target: str) -> list[Relation]:
        """Vztahy, které vedou do pojmu ``target``, seřazené podle zdroje."""
        found: list[Relation] = getattr(self, "_incoming").get(target, [])
        return sorted(found, key=lambda relation: relation.source)

    def related(self, first: str, second: str) -> bool:
        """Jsou pojmy doloženě příbuzné (v jakémkoli směru)?"""
        return frozenset((first, second)) in getattr(self, "_pairs")


@lru_cache(maxsize=1)
def core_graph() -> ConceptGraph:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    relations = tuple(
        Relation(
            item["source"], item["target"], int(item.get("polysemy", 0)),
            int(item.get("derivation", 0)), int(item.get("colexification", 0)),
        )
        for item in data["relations"]
    )
    return ConceptGraph(relations, _compound_recipes())


def _compound_recipes() -> dict[str, tuple[tuple[str, str], ...]]:
    """Kurátorované recepty složenin pro Swadesh 100 (převzato z legacy).

    Viz ``docs/SWADESH_COMPOUNDS.md``: jde o možnosti pro worldbuilding,
    ne o tvrzení o univerzální etymologii.
    """
    from cee.semantics.swadesh import _OPTIONS

    return {target: tuple((head, modifier) for head, modifier, _ in options)
            for target, options in _OPTIONS.items()}
