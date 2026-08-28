from typing import Optional
from cee.core.models import Lexicon, Word, State
import copy

class MorphologyEvaluator:
    """
    Vykonává morfologické operace, např. skládání slov (compounding)
    a případně analogii (zarovnávání nepravidelností).
    """
    
    def compound(self, state: State, word1_id: str, word2_id: str, new_concept_id: str) -> Optional[Word]:
        """
        Vytvoří nové slovo spojením dvou existujících slov z lexikonu státu.
        Respektuje typologický parametr 'compound_head' (initial vs final).
        word1: hlava (head)
        word2: modifikátor (modifier)
        
        Např: head='město', modifier='zlatý'. 
        Pokud head='final', výsledek bude [zlatý][město].
        Pokud head='initial', výsledek bude [město][zlatý].
        """
        w1 = state.lexicon.get_word(word1_id)
        w2 = state.lexicon.get_word(word2_id)
        
        if not w1 or not w2:
            return None
            
        head_order = state.compound_head
        
        if head_order == "initial":
            new_segments = copy.deepcopy(w1.segments) + copy.deepcopy(w2.segments)
        else: # final
            new_segments = copy.deepcopy(w2.segments) + copy.deepcopy(w1.segments)
            
        new_word = Word(
            concept_id=new_concept_id,
            segments=new_segments,
            origin_year=state.year
        )
        
        # Přidáme do lexikonu
        state.lexicon.words.append(new_word)
        return new_word
