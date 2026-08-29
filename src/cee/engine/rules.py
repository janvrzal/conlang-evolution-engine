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
    #: Volitelná prosodická podmínka: ``unstressed`` nebo ``stressed``.
    prosody: Optional[str] = None
    #: Pozice v explicitně vypočtené slabice: onset, nucleus nebo coda.
    syllable_part: Optional[str] = None

    def apply_to_word(self, word: Word) -> bool:
        """
        Aplikuje pravidlo na slovo in-place. Vrací True, pokud došlo ke změně.
        Provedeno ve dvou fázích (identifikace -> mutace) pro zamezení self-feeding artefaktů.
        """
        # 0. Kontrola časové stopy (výpůjčky přejaté po pravidle jím neprojdou)
        if self.year is not None and self.year < word.origin_year:
            return False
            
        word.ensure_stress()
        # Fáze 1: Identifikace terčů
        targets_to_modify = []
        for i, segment in enumerate(word.segments):
            # 1. Odpovídá segment terči pravidla?
            if not segment.matches(self.target):
                continue

            if self.prosody == "unstressed" and i == word.stress_index:
                continue
            if self.prosody == "stressed" and i != word.stress_index:
                continue

            if self.syllable_part:
                from cee.engine.prosody import syllable_position
                if syllable_position(word, i) != self.syllable_part:
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
                elif self.env_after.get("_lookahead_vowel") == "+":
                    environment = {
                        key: value for key, value in self.env_after.items()
                        if not key.startswith("_")
                    }
                    following_vowel = next(
                        (candidate for candidate in word.segments[i + 1:]
                         if candidate.features.get("syl") == "+"),
                        None,
                    )
                    if following_vowel is None or not following_vowel.matches(environment):
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
            word.ensure_stress()
            return True

        if self.action.get("delete") == "+":
            zbyvajici = [s for i, s in enumerate(word.segments) if i not in set(targets_to_modify)]

            # Prosodická minimalita ("information carrying capacity"): slovo
            # nesmí přijít o jediné jádro slabiky, jinak přestává být
            # vyslovitelné a splývá s libovolným jiným shlukem souhlásek.
            # Segment-count kontrola (< 2 hlásky) tohle nechytí — "spir" má
            # po synkopě 3 hlásky, ale žádnou samohlásku.
            if not self._passes_minimality(word, word.segments, zbyvajici):
                return False

            word.segments = zbyvajici
            word.ensure_stress()
            return True

        for i in targets_to_modify:
            segment = word.segments[i]
            for feature, new_value in self.action.items():
                segment.features[feature] = new_value

        word.ensure_stress()

        return True

    @staticmethod
    def _passes_minimality(word: Word, original: List[Segment], zbyvajici: List[Segment]) -> bool:
        """
        Kontrola prosodické minimality po mazacím pravidle.

        Blokuje dvě věci, ne jednu společnou hranici segmentů:
        - slovo by úplně zaniklo (`zbyvajici` prázdné),
        - slovo by přišlo o poslední slabičné jádro, i když by hlásek
          formálně zbylo dost (typicky souhláskový shluk bez samohlásky).

        Pokud protojazykové slovo samo o sobě žádnou samohlásku nemá, dál se
        to nekontroluje — není co chránit.
        """
        if not zbyvajici:
            return False

        if getattr(word, "is_grammatical", False):
            return True

        melo_jadro = any(s.features.get("syl") == "+" for s in original)
        ma_jadro = any(s.features.get("syl") == "+" for s in zbyvajici)

        # Forma bez jádra už v protojazyce žádné jádro chránit nemá. Její
        # další zkrácení proto smí projít (dokud nezmizí úplně); viz test
        # `minimalita_neresi_slovo_bez_samohlasky_od_pocatku`.
        return ma_jadro or not melo_jadro

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
