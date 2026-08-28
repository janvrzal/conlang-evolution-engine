import random
from cee.core.models import Lexicon
from cee.semantics.graph import SemanticGraph

class SemanticEvaluator:
    """
    Vykonává sémantické posuny nad lexikonem na základě sémantického grafu.
    Simuluje to, jak slova v čase získávají nové významy (polysemie) a ztrácejí staré.
    """
    def __init__(self, graph: SemanticGraph, shift_prob: float = 0.05, forget_prob: float = 0.01, seed: int = 42):
        """
        :param graph: Načtená síť Concepticon/DatSemShift/CLICS
        :param shift_prob: Šance (0.0 - 1.0), že jedno slovo získá nový význam během jednoho průchodu (např. jednoho století)
        :param forget_prob: Šance (0.0 - 1.0), že slovo s více významy zapomene jeden ze svých starších významů.
        :param seed: Seed pro deterministické hody kostkou (nutné pro hashování stromu historie)
        """
        self.graph = graph
        self.shift_prob = shift_prob
        self.forget_prob = forget_prob
        self.random = random.Random(seed)
        
    def evaluate(self, lexicon: Lexicon) -> Lexicon:
        """
        Projde lexikon a aplikuje pravděpodobnostní sémantické změny.
        Modifikuje in-place, ale vrací pro pohodlí řetězení.
        """
        for word in lexicon.words:
            # 1. Získání nového významu (Rozšíření)
            if self.random.random() < self.shift_prob:
                # Rozhodneme se, z jakého aktuálního významu se slovo odrazí.
                # Většinou z hlavního, ale může i z těch, které už získalo.
                available_origins = [word.concept_id] + list(word.polysemy)
                origin = self.random.choice(available_origins)
                
                # Zde musíme graph upravit nebo si udělat vlastní random choice, 
                # ale graph.random_shift používá globální random. 
                # V dalším kroku upravíme i graph.py, teď používáme aspoň lokální pravděpodobnost.
                # new_concept může být None, pokud uzel nemá žádné následníky
                new_concept = self.graph.random_shift(origin, random_gen=self.random)
                if new_concept and new_concept != word.concept_id and new_concept not in word.polysemy:
                    # Slovo získalo nový význam!
                    word.polysemy.add(new_concept)
                    
            # 2. Ztráta starého významu (Zúžení / Shift)
            # Pokud má slovo více významů, může jeden ztratit.
            if len(word.polysemy) > 0 and self.random.random() < self.forget_prob:
                all_meanings = [word.concept_id] + list(word.polysemy)
                to_forget = self.random.choice(all_meanings)
                
                if to_forget == word.concept_id:
                    # Pokud zapomene svůj hlavní význam (kořen), musíme ho nahradit nějakým z polysemie.
                    new_root = word.polysemy.pop()
                    word.concept_id = new_root
                else:
                    word.polysemy.remove(to_forget)
                    
        return lexicon
