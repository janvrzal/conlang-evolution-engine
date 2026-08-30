from typing import Dict

import panphon

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
            mapping = {1: "+", -1: "-", 0: "0"}
            return {k: mapping.get(v, str(v)) for k, v in numeric_dict.items()}

        for ipa_str in self.ft.seg_dict.keys():
            # ft.word_fts vrací list panphon segmentů
            segs = self.ft.word_fts(ipa_str)
            if segs:
                fd = _to_str_dict(segs[0].data)
                self._known_segments.append((ipa_str, fd))

        # Seřadíme podle délky IPA řetězce, abychom při shodě preferovali nejjednodušší znak (např. 'o' před 'ö')  # noqa: E501
        self._known_segments.sort(key=lambda x: len(x[0]))

        # Memoizace zpětného překladu. Bez ní se pro každý segment lineárně
        # prochází celá panphon tabulka (tisíce položek), a to po každém pravidle
        # při aktualizaci inventáře.
        self._ipa_cache: Dict[tuple, str] = {}

    def parse_word(self, concept_id: str, ipa_string: str, is_grammatical: bool = False) -> Word:
        """
        Převod řetězce IPA znaků na instanci třídy Word.
        Neznámé znaky přeskočí s varováním.
        """
        mapping = {1: "+", -1: "-", 0: "0"}
        panphon_segs = self.ft.word_fts(ipa_string)
        segments = [
            Segment(features={k: mapping.get(v, str(v)) for k, v in seg.data.items()})
            for seg in panphon_segs
        ]
        word = Word(concept_id=concept_id, segments=segments, is_grammatical=is_grammatical)
        # Výchozí prozodie je součást vstupního stavu, ne první náhodné
        # zvukové změny. Jinak by se pouhé přiřazení přízvuku mylně
        # zapisovalo jako zásah historického pravidla.
        word.ensure_stress()
        return word

    def segment_to_ipa(self, segment: Segment) -> str:
        """
        Najde nejlepší odpovídající IPA znak pro danou rysovou matici.
        Výsledek je memoizovaný podle obsahu rysové matice.
        """
        if not segment.features:
            return "?"

        cache_key = tuple(sorted(segment.features.items()))
        cached = self._ipa_cache.get(cache_key)
        if cached is not None:
            return cached

        result = self._resolve_ipa(segment.features)
        self._ipa_cache[cache_key] = result
        return result

    def _resolve_ipa(self, features: Dict[str, str]) -> str:
        """Vlastní vyhledání nejlepšího IPA znaku (bez cache)."""
        # 1. Pokus o exaktní shodu (nejrychlejší)
        for ipa, fd in self._known_segments:
            if fd == features:
                return ipa

        # 2. Hledání nejbližší shody (např. pokud pravidlo vytvořilo nevyváženou matici)
        # Počítáme shodu rysů. (V produkci by se zde hodila Hammingova vzdálenost)
        best_match = "?"
        best_score = -1

        for ipa, fd in self._known_segments:
            score = 0
            possible = True
            for feature, target_val in features.items():
                actual_val = fd.get(feature, "0")
                if actual_val == target_val:
                    score += 1
                elif actual_val != "0" and target_val != "0":
                    # Konflikt v explicitním rysu (např. +voice vs -voice)
                    possible = False
                    break

            if possible and score > best_score:
                best_score = score
                best_match = ipa

        return best_match

    def is_exact_segment(self, segment: Segment) -> bool:
        """
        True, pokud rysová matice přesně odpovídá některé známé IPA hlásce.

        False znamená, že pravidlo vyrobilo kombinaci rysů, která v panphon
        tabulce neexistuje, a `segment_to_ipa` musel sáhnout po přibližné
        shodě — tichý zdroj zkomolených výstupů.
        """
        if not segment.features:
            return False
        return any(fd == segment.features for _ipa, fd in self._known_segments)

    def render_word(self, word: Word) -> str:
        """
        Převede celý objekt Word zpět na IPA text včetně kontrastivní délky.
        """
        return "".join(
            self.segment_to_ipa(segment) + ("ː" if index in word.long_nuclei else "")
            for index, segment in enumerate(word.segments)
        )

    def render_word_prosodic(self, word: Word) -> str:
        """IPA tvar s explicitní značkou uloženého hlavního přízvuku."""
        return "".join(
            ("ˈ" if index == word.stress_index else "")
            + self.segment_to_ipa(segment)
            + ("ː" if index in word.long_nuclei else "")
            for index, segment in enumerate(word.segments)
        )
