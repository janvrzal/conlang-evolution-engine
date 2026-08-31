"""Typy událostí společné časové osy evoluční simulace.

Oddělení datových nosičů od `EvolutionSimulator` drží samotný orchestrátor
zaměřený na pořadí a účinky událostí. Události jsou záměrně malé a nemají
vlastní chování: historická pravidla zůstávají v `rules.py`.
"""

from dataclasses import dataclass
from typing import Dict

from cee.engine.rules import Rule


@dataclass
class ForkEvent:
    year: int
    parent_id: str
    child_id: str


@dataclass
class PhonologyEvent:
    """Ručně zapsané, okamžité pravidlo pro zpětnou kompatibilitu."""

    year: int
    branch_id: str
    rule: Rule


@dataclass
class SoundChangeEvent:
    """Začátek generované změny, která se šíří po části časové osy."""

    year: int
    branch_id: str
    rule: Rule
    change_id: str
    duration: int
    intensity: float = 1.0
    pressure: float = 0.0
    applicable_words: int = 0
    frequency_coverage: float = 0.0


@dataclass
class SoundChangeSpreadEvent:
    """Jedna kumulativní fáze šíření dříve vzniklé zvukové inovace."""

    year: int
    branch_id: str
    change_id: str
    progress: float


@dataclass
class PhonologySlotEvent:
    """Okamžik, kdy se pravidlo vybere z tehdejšího stavu jazyka."""

    year: int
    branch_id: str


@dataclass
class ContactEvent:
    year: int
    source_id: str
    target_id: str
    volume: int
    domain: str = "neighborhood"
    prestige: float = 1.0
    calque_rate: float = 0.0
    adapt: bool = False


@dataclass
class SemanticEvent:
    year: int
    branch_id: str


@dataclass
class SemanticChangeEvent:
    """Sémantická inovace, která po určitou dobu koexistuje se starým užitím."""

    year: int
    branch_id: str
    change_id: str
    word_lineage_id: str
    source_concept: str
    target_concept: str
    kind: str
    duration: int
    pressure: float
    evidence_weight: float
    evidence_type: str
    adoption_threshold: float
    introduced: bool = False


@dataclass
class SemanticChangeSpreadEvent:
    """Kumulativní fáze šíření jedné sémantické inovace."""

    year: int
    branch_id: str
    change_id: str
    progress: float


@dataclass
class MorphologyEvent:
    year: int
    branch_id: str


@dataclass
class LexicalEvent:
    year: int
    branch_id: str


@dataclass
class SocialEvent:
    year: int
    branch_id: str
    changes: Dict[str, float]
