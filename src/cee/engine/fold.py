from typing import List, Set, Optional
from cee.core.models import Lexicon
from cee.engine.rules import Rule
from cee.engine.phonology import FeatureMapper

class DerivationFold:
    """
    Hlavní engine pro aplikaci sérií historických pravidel na celý jazyk.
    Zatím aplikuje pravidla in-place na slovník. V budoucnu zde bude
    logika pro ukládání verzovaných uzlů (State).
    """
    def __init__(self, rules: List[Rule]):
        self.rules = rules
        
    def apply_to_lexicon(self, lexicon: Lexicon, mapper: Optional[FeatureMapper] = None) -> Lexicon:
        """
        Aplikuje chronologický seznam pravidel na celý lexikon.
        Každé pravidlo se aplikuje na každé slovo.
        """
        for rule in self.rules:
            for word in lexicon.words:
                rule.apply_to_word(word)
                
            if mapper:
                self.update_inventory(lexicon, mapper)
                
        return lexicon
        
    def update_inventory(self, lexicon: Lexicon, mapper: FeatureMapper) -> Set[str]:
        """Projde lexikon a zjistí všechny aktuálně používané fonémy."""
        inventory = set()
        for word in lexicon.words:
            for segment in word.segments:
                try:
                    ipa = mapper.segment_to_ipa(segment)
                    if ipa:
                        inventory.add(ipa)
                except Exception:
                    pass
        return inventory
