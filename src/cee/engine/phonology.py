import panphon
from typing import List, Dict
from cee.core.models import Segment, Word

class FeatureMapper:
    """
    Zajišťuje obousměrný překlad mezi textovými IPA znaky a rysovými maticemi
    s využitím knihovny panphon.
    """
    def __init__(self):
        # Inicializace panphon FeatureTable (obsahuje definice tisíců IPA znaků)
        self.ft = panphon.FeatureTable()
        
        # Pre-cache pro rychlejší zpětné vyhledávání (Rysy -> IPA)
        # Uložíme si seznam všech známých plně specifikovaných matic
        self._known_segments = []
        
        def _to_str_dict(numeric_dict):
            mapping = {1: '+', -1: '-', 0: '0'}
            return {k: mapping.get(v, str(v)) for k, v in numeric_dict.items()}
            
        for ipa_str in self.ft.seg_dict.keys():
            # ft.word_fts vrací list panphon segmentů
            segs = self.ft.word_fts(ipa_str)
            if segs:
                fd = _to_str_dict(segs[0].data)
                self._known_segments.append((ipa_str, fd))
                
        # Seřadíme podle délky IPA řetězce, abychom při shodě preferovali nejjednodušší znak (např. 'o' před 'ö')
        self._known_segments.sort(key=lambda x: len(x[0]))

    def parse_word(self, concept_id: str, ipa_string: str) -> Word:
        """
        Převod IPA textu na objekt Word složený z rysových matic.
        """
        mapping = {1: '+', -1: '-', 0: '0'}
        panphon_segs = self.ft.word_fts(ipa_string)
        segments = [Segment(features={k: mapping.get(v, str(v)) for k, v in seg.data.items()}) for seg in panphon_segs]
        return Word(concept_id=concept_id, segments=segments)

    def segment_to_ipa(self, segment: Segment) -> str:
        """
        Najde nejlepší odpovídající IPA znak pro danou rysovou matici.
        """
        if not segment.features:
            return "?"

        # 1. Pokus o exaktní shodu (nejrychlejší)
        for ipa, fd in self._known_segments:
            if fd == segment.features:
                return ipa
                
        # 2. Hledání nejbližší shody (např. pokud pravidlo vytvořilo nevyváženou matici)
        # Počítáme shodu rysů. (V produkci by se zde hodila Hammingova vzdálenost)
        best_match = "?"
        best_score = -1
        
        for ipa, fd in self._known_segments:
            score = 0
            possible = True
            for feature, target_val in segment.features.items():
                actual_val = fd.get(feature, '0')
                if actual_val == target_val:
                    score += 1
                elif actual_val != '0' and target_val != '0':
                    # Konflikt v explicitním rysu (např. +voice vs -voice)
                    possible = False
                    break
            
            if possible and score > best_score:
                best_score = score
                best_match = ipa
                
        return best_match

    def render_word(self, word: Word) -> str:
        """
        Převede celý objekt Word zpět na IPA text.
        """
        return "".join(self.segment_to_ipa(seg) for seg in word.segments)
