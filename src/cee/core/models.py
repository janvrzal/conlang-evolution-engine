from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set

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
    """
    Represents a language node at an absolute year.
    """
    node_id: str
    year: int
    inventory: Inventory
    lexicon: Lexicon
    parent_id: Optional[str] = None
    hash: str = ""
