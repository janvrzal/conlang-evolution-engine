from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Any

@dataclass
class Segment:
    """
    Represents a single phonological segment.
    Uses a feature matrix rather than just a character string.
    """
    features: Dict[str, str] = field(default_factory=dict)
    
    def matches(self, target_features: Dict[str, str]) -> bool:
        """
        Check if this segment matches a given feature bundle.
        Example: target_features = {'son': '-', 'voice': '+', 'cont': '-'}
        """
        for feature, value in target_features.items():
            if self.features.get(feature) != value:
                return False
        return True

import uuid

@dataclass
class Word:
    """
    A single lexical item, which is a sequence of Segments.
    """
    concept_id: str
    segments: List[Segment]
    polysemy: Set[str] = field(default_factory=set) # Dodatečné významy (sémantické posuny)
    origin_year: int = 0
    source_id: Optional[str] = None # ID zdrojového uzlu v případě výpůjčky
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_word_id: Optional[str] = None
    origin_type: str = "inherited" # inherited, mutated, borrowed
    origin_rule: Optional[str] = None # if mutated, rule name
    is_grammatical: bool = False


@dataclass
class Lexicon:
    """
    A collection of words for a specific state.
    """
    words: List[Word] = field(default_factory=list)
    
    def get_word(self, concept_id: str) -> Optional[Word]:
        """Vrátí první nalezené slovo pokrývající tento koncept (primární nebo sdílený)."""
        for word in self.words:
            if word.concept_id == concept_id or concept_id in word.polysemy:
                return word
        return None
        
    def get_words(self, concept_id: str) -> List[Word]:
        """Vrátí všechna slova, která pokrývají daný koncept (synonyma)."""
        return [w for w in self.words if w.concept_id == concept_id or concept_id in w.polysemy]

@dataclass
class Inventory:
    """
    The set of phonemes available in a given state.
    Serves as the phonotactic filter and state tracking for rules.
    """
    segments: Set[str] = field(default_factory=set)

@dataclass
class State:
    """Stav jazyka v určitém čase/uzlu."""
    node_id: str
    inventory: Inventory
    lexicon: Lexicon
    year: int = 0
    parent_id: Optional[str] = None
    hash: Optional[str] = None
    map: Dict[str, Any] = field(default_factory=dict)
    
    # Morfologické / Typologické parametry
    affixation_strategy: str = "suffix" # "prefix" nebo "suffix"
    compound_head: str = "final"        # "initial" nebo "final"
    def __post_init__(self):
        if self.map is None:
            self.map = {}
        if "compound_head" in self.map:
            self.compound_head = self.map["compound_head"]
        if "affixation_strategy" in self.map:
            self.affixation_strategy = self.map["affixation_strategy"]
