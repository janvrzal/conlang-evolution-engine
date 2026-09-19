from dataclasses import dataclass, field
from typing import Any, Dict, List

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
    volume: int = 10  # Kolik slov se průměrně přejímá

    #: Sousedící jazyky se obvykle ovlivňují navzájem, ne jen jedním směrem.
    #: Jednosměrný kontakt odpovídá výrazně nesymetrické prestiži.
    mutual: bool = False
    #: Sociální typ kontaktu (obchod, válka, náboženství, sousedství).
    domain: str = "neighborhood"
    #: Poměr prestiže zdroje vůči cíli; 1.0 je vyrovnaný kontakt.
    prestige: float = 1.0
    #: Podíl významových kalků místo přímého převzetí tvaru.
    calque_rate: float = 0.0
    #: Starší scénáře zachovávají přesný tvar výpůjčky; nový editor může
    #: explicitně zapnout adaptaci do inventáře cílového jazyka.
    adapt: bool = False
    #: Sociální kanál přejímky; určuje registr přejatého lexému.
    layer: str = "folk"
    #: Zda smí kontakt přenášet i gramatické morfémy a jejich produktivitu.
    transfer_morphology: bool = False
    #: Zda smí kontakt nabídnout výpůjčku jako řešení funkčně zatížené homofonie.
    resolve_homophony: bool = False
    #: ID produktivních konstrukcí z konfigurace zdrojového jazyka.
    construction_ids: List[str] = field(default_factory=list)

    def directions(self):
        """Dvojice (zdroj, cíl) pro každý směr, kterým kontakt působí."""
        pairs = [(self.source_id, self.target_id)]
        if self.mutual:
            pairs.append((self.target_id, self.source_id))
        return pairs


@dataclass
class Polity:
    """Autorsky kreslená politická jednotka; neztotožňuje se s jazykem."""

    id: str
    name: str
    territory: List[Dict[str, float]] = field(default_factory=list)
    institutions: Dict[str, float] = field(default_factory=dict)
    language_ids: List[str] = field(default_factory=list)


@dataclass
class TradeRoute:
    """Mapový objekt, z něhož se odvozují časované kontakty."""

    id: str
    kind: str  # sea / land / river
    intensity: float
    language_ids: List[str]
    start_year: int = 0
    end_year: int | None = None
    # Světové souřadnice kreslené přímo na plátně. Jsou nepovinné, aby staré
    # projekty dál fungovaly jako ručně určený seznam zastávek.
    waypoints: List[Dict[str, float]] = field(default_factory=list)


@dataclass
class HistoricalEventSpec:
    id: str
    kind: str
    start_year: int
    duration: int = 0
    target_language_ids: List[str] = field(default_factory=list)
    target_polity_id: str | None = None
    effects: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvolutionGraph:
    """
    Kompletní definice stromu/grafu rodiny.
    """

    node_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    nodes: Dict[str, State] = field(default_factory=dict)
    vertical_edges: List[VerticalEdge] = field(default_factory=list)
    contact_edges: List[ContactEdge] = field(default_factory=list)
    polities: Dict[str, Polity] = field(default_factory=dict)
    trade_routes: List[TradeRoute] = field(default_factory=list)
    historical_events: List[HistoricalEventSpec] = field(default_factory=list)

    def get_children(self, node_id: str) -> List[str]:
        return [e.child_id for e in self.vertical_edges if e.parent_id == node_id]

    def get_rules_for_edge(self, parent_id: str, child_id: str) -> List[Rule]:
        for e in self.vertical_edges:
            if e.parent_id == parent_id and e.child_id == child_id:
                return e.rules
        return []
