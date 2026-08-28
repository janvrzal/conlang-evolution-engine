from typing import List, Optional, Set

from cee.core.models import Inventory, Lexicon, State
from cee.engine.phonology import FeatureMapper
from cee.engine.rules import Rule


class DerivationFold:
    """
    Hlavní engine pro aplikaci sérií historických pravidel na celý jazyk.

    Fold je stavový: po každém pravidle přepočítá fonologický inventář, takže
    stav uzlu odpovídá tomu, co v jazyce po dané změně skutečně existuje
    (viz CEE_master.md, 4.3).
    """

    def __init__(self, rules: List[Rule]):
        self.rules = rules
        self.inventory: Set[str] = set()

    def apply_to_lexicon(
        self,
        lexicon: Lexicon,
        mapper: Optional[FeatureMapper] = None,
        state: Optional[State] = None,
    ) -> Lexicon:
        """
        Aplikuje chronologický seznam pravidel na celý lexikon.
        Každé pravidlo se aplikuje na každé slovo.

        Je-li předán `mapper`, po každém pravidle se aktualizuje inventář —
        výsledek je dostupný přes `self.inventory` a zapíše se do `state.inventory`,
        pokud je `state` předán.
        """
        for rule in self.rules:
            for word in lexicon.words:
                rule.apply_to_word(word)

            if mapper:
                self.inventory = self.update_inventory(lexicon, mapper)
                if state is not None:
                    state.inventory = Inventory(segments=set(self.inventory))

        return lexicon

    def update_inventory(self, lexicon: Lexicon, mapper: FeatureMapper) -> Set[str]:
        """Projde lexikon a zjistí všechny aktuálně používané fonémy."""
        inventory = set()
        for word in lexicon.words:
            for segment in word.segments:
                ipa = mapper.segment_to_ipa(segment)
                if ipa and ipa != "?":
                    inventory.add(ipa)
        return inventory
