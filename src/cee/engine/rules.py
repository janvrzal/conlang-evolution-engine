from dataclasses import dataclass
from typing import Dict, List, Optional
from cee.core.models import Segment, Word

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
    year: Optional[int] = None

    #: "before" / "after" — vloží nový segment vedle terče. Bez toho uměl
    #: engine jen měnit rysy a mazat, takže slova mohla pouze krátnout.
    insert: Optional[str] = None
    #: Úplná rysová matice vkládaného segmentu (musí odpovídat reálné hlásce).
    insert_features: Optional[Dict[str, str]] = None
    #: IPA vkládané hlásky, jen pro čitelnost názvů a záznamu.
    insert_label: Optional[str] = None

    def apply_to_word(self, word: Word) -> bool:
        """
        Aplikuje pravidlo na slovo in-place. Vrací True, pokud došlo ke změně.
        Provedeno ve dvou fázích (identifikace -> mutace) pro zamezení self-feeding artefaktů.
        """
        # 0. Kontrola časové stopy (výpůjčky přejaté po pravidle jím neprojdou)
        if self.year is not None and self.year < word.origin_year:
            return False
            
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

        if self.insert and self.insert_features:
            word.segments = self._with_insertions(word, targets_to_modify)
            return True

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

    def _with_insertions(self, word: Word, targets: List[int]) -> List[Segment]:
        """
        Poskládá slovo znovu i s vloženými segmenty.

        Staví se nový seznam, protože vkládání do stávajícího by posunulo
        indexy, které fáze 1 našla nad původním tvarem.
        """
        pozice = set(targets)
        vysledek: List[Segment] = []

        for i, segment in enumerate(word.segments):
            if i in pozice and self.insert == "before":
                vysledek.append(Segment(features=dict(self.insert_features)))

            vysledek.append(segment)

            if i in pozice and self.insert == "after":
                vysledek.append(Segment(features=dict(self.insert_features)))

        return vysledek
