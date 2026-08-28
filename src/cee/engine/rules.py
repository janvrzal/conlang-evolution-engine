from dataclasses import dataclass, field
from typing import Dict, Optional
from cee.core.models import Word

@dataclass
class Rule:
    """
    Reprezentuje jediné historické fonologické pravidlo.
    Tato třída je zcela nezávislá na tom, z jakého textového formátu 
    byla načtena (YAML, JSON, Lexurgy).
    """
    name: str
    target: Dict[str, str]
    action: Dict[str, str]
    env_before: Optional[Dict[str, str]] = None
    env_after: Optional[Dict[str, str]] = None

    def apply_to_word(self, word: Word) -> bool:
        """
        Aplikuje pravidlo na slovo in-place. Vrací True, pokud došlo ke změně.
        Provedeno ve dvou fázích (identifikace -> mutace) pro zamezení self-feeding artefaktů.
        """
        # Fáze 1: Identifikace terčů
        targets_to_modify = []
        for i, segment in enumerate(word.segments):
            # 1. Odpovídá segment terči pravidla?
            if not segment.matches(self.target):
                continue
                
            # 2. Odpovídá předchozí segment prostředí 'env_before'?
            if self.env_before:
                if self.env_before.get("_boundary") == "+":
                    if i != 0:
                        continue
                else:
                    if i == 0 or not word.segments[i-1].matches(self.env_before):
                        continue
                    
            # 3. Odpovídá následující segment prostředí 'env_after'?
            if self.env_after:
                if self.env_after.get("_boundary") == "+":
                    if i != len(word.segments) - 1:
                        continue
                else:
                    if i == len(word.segments) - 1 or not word.segments[i+1].matches(self.env_after):
                        continue
                        
            targets_to_modify.append(i)
            
        # Fáze 2: Simultánní mutace
        if not targets_to_modify:
            return False
            
        for i in targets_to_modify:
            segment = word.segments[i]
            if self.action.get("delete") == "+":
                segment.features["delete"] = "+"
            else:
                for feature, new_value in self.action.items():
                    segment.features[feature] = new_value
                    
        # Odstraníme segmenty označené ke smazání
        if self.action.get("delete") == "+":
            word.segments = [s for s in word.segments if s.features.get("delete") != "+"]
            
        return True
