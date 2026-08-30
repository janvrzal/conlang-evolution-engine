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
    year: int
    branch_id: str
    rule: Rule


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
