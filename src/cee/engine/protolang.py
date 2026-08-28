import json
import random
from pathlib import Path
from typing import List, Dict, Any

class ProtolangGenerator:
    """
    Generátor počátečního lexikonu (Proto-jazyka) ze zadaných hláskových inventářů.
    """
    def __init__(self, concepts_file: str = "src/cee/data/concepts.json", seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)
        
        path = Path(concepts_file)
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                self.concepts = json.load(f)
        else:
            self.concepts = [{"id": "sun"}, {"id": "moon"}, {"id": "water"}]

    def generate_word(self, consonants: List[str], vowels: List[str], syllable_structure: str, min_syl: int = 1, max_syl: int = 2) -> str:
        """
        Vygeneruje jedno slovo podle zadaných pravidel.
        syllable_structure: např. "CV", "CVC", "(C)V"
        Zatím podporujeme zjednodušený parser:
        C = náhodná souhláska
        V = náhodná samohláska
        """
        syl_count = self.rng.randint(min_syl, max_syl)
        word = ""
        
        for _ in range(syl_count):
            i = 0
            while i < len(syllable_structure):
                char = syllable_structure[i]
                optional = False
                
                if char == '(':
                    optional = True
                    i += 1
                    char = syllable_structure[i]
                    i += 1 # přeskočíme znak
                    if i < len(syllable_structure) and syllable_structure[i] == ')':
                        pass # přeskočíme zavírací závorku
                
                # U volitelných prvků hodíme mincí (50% šance)
                if optional and self.rng.random() < 0.5:
                    i += 1
                    continue
                    
                if char == 'C':
                    word += self.rng.choice(consonants)
                elif char == 'V':
                    word += self.rng.choice(vowels)
                    
                i += 1
        return word

    def generate_lexicon(self, consonants: str, vowels: str, syllable_structure: str) -> List[Dict[str, Any]]:
        """
        Vygeneruje slovník pro všechny koncepty.
        Očekává stringy oddělené mezerou, např. "p t k s m n", "a i u"
        """
        cons_list = consonants.split()
        vow_list = vowels.split()
        
        words = []
        for concept in self.concepts:
            ipa = self.generate_word(cons_list, vow_list, syllable_structure)
            words.append({
                "id": concept["id"],
                "ipa": ipa,
                "polysemy": []
            })
            
        return words
