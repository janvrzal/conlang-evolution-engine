import hashlib
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

from cee.core.models import State
from cee.engine.rules import Rule

@dataclass
class VerticalEdge:
    """
    Hrana dědičnosti mezi mateřským a dceřiným jazykem.
    Obsahuje pravidla uspořádaná chronologicky.
    """
    parent_id: str
    child_id: str
    rules: List[Rule] = field(default_factory=list)

@dataclass
class ContactEdge:
    """
    Horizontální hrana (výpůjčka, kontakt) mezi dvěma jazyky v daném roce.
    """
    year: int
    source_id: str
    target_id: str
    volume: int = 10  # Kolik slov se průměrně přejímá (může být řízeno pravděpodobností)

@dataclass
class EvolutionGraph:
    """
    Kompletní definice stromu/grafu rodiny.
    """
    node_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    nodes: Dict[str, State] = field(default_factory=dict)
    vertical_edges: List[VerticalEdge] = field(default_factory=list)
    contact_edges: List[ContactEdge] = field(default_factory=list)
    
    def get_children(self, node_id: str) -> List[str]:
        return [e.child_id for e in self.vertical_edges if e.parent_id == node_id]
        
    def get_rules_for_edge(self, parent_id: str, child_id: str) -> List[Rule]:
        for e in self.vertical_edges:
            if e.parent_id == parent_id and e.child_id == child_id:
                return e.rules
        return []

def compute_state_hash(parent_id: Optional[str], rules: List[Rule], seed: int = 42) -> str:
    """
    Git-like verzování stavu na základě jeho historie.
    """
    m = hashlib.sha256()
    if parent_id:
        m.update(parent_id.encode('utf-8'))
    for rule in rules:
        m.update(rule.name.encode('utf-8'))
        if rule.year:
            m.update(str(rule.year).encode('utf-8'))
    m.update(str(seed).encode('utf-8'))
    return m.hexdigest()[:12]
