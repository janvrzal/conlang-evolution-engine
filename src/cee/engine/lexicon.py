"""Diachronní lexikální obměna: frekvence, konkurence a náhrada kořene."""
from __future__ import annotations

import copy
import random
import uuid
from typing import Callable, Iterable, Optional, Sequence

from cee.core.models import State, Word


def _is_basic(word: Word) -> bool:
    """První, staré a časté položky považujeme za konzervativnější jádro."""
    return word.frequency >= 0.7


class LexicalEvaluator:
    """Malý, deterministický model životního cyklu lexému.

    Neháže pryč koncepty náhodně: nejdřív vytvoří konkurující náhradu, až
    potom může starý, málo frekventní tvar ustoupit. Výpůjčky a složeniny tak
    zůstávají plnohodnotnými účastníky pozdějších zvukových změn.
    """

    def __init__(self, replacement_rate: float = 0.015, loss_rate: float = 0.01):
        self.replacement_rate = max(0.0, replacement_rate)
        self.loss_rate = max(0.0, loss_rate)

    def evaluate(
        self,
        state: State,
        year: int,
        rng: random.Random,
        *,
        taboo_concepts: Sequence[str] = (),
        resolve_homophones: bool = False,
        render: Optional[Callable[[Word], str]] = None,
    ) -> list[Word]:
        active = [word for word in state.lexicon.words if word.active]
        if not active:
            return []

        mobility = state.social.get("mobility", 0.5)
        standard = state.social.get("standardization", 0.0)
        replacements: list[Word] = []

        for word in active:
            stability = 0.65 if _is_basic(word) else 0.25
            word.frequency = min(1.0, max(0.01, word.frequency + (stability - 0.5) * 0.08))

            # Standardizace chrání existující tvar; mobilita naopak podporuje
            # soutěž synonym a náhrad.
            rate = self.replacement_rate * (1.0 + mobility) * (1.0 - standard)
            if _is_basic(word) or rng.random() >= rate:
                continue

            donor = self._donor(active, word, rng)
            if donor is None:
                continue
            replacement = copy.deepcopy(donor)
            replacement.id = str(uuid.uuid4())
            replacement.parent_word_id = donor.id
            replacement.concept_id = word.concept_id
            replacement.polysemy = set()
            replacement.origin_year = year
            replacement.origin_type = "lexical_replacement"
            replacement.origin_rule = "lexical replacement"
            replacement.source_id = None
            replacement.frequency = max(0.12, word.frequency * 0.75)
            replacement.morpheme_boundaries = set(donor.morpheme_boundaries)
            replacements.append(replacement)

            if word.frequency < 0.20 and rng.random() < self.loss_rate * (1.0 - standard):
                word.active = False

        # Tabu nenechá slot prázdný: starý tvar přestane být produktivní a
        # nový se utvoří z jiného živého kořene. Konfigurace je explicitní,
        # takže žádný koncept není bez souhlasu uživatele „zakázán“.
        for word in active:
            if word.concept_id not in taboo_concepts or not word.active:
                continue
            donor = self._donor(active, word, rng)
            if donor is None:
                continue
            replacement = self._replacement_from(donor, word, year, "taboo_replacement")
            replacement.frequency = max(0.2, word.frequency)
            replacements.append(replacement)
            word.active = False

        if resolve_homophones and render:
            groups: dict[str, list[Word]] = {}
            for word in [*active, *replacements]:
                if word.active:
                    groups.setdefault(render(word), []).append(word)
            for forms in groups.values():
                if len(forms) < 2:
                    continue
                winner = max(forms, key=lambda word: word.frequency)
                for loser in forms:
                    if loser is winner or not loser.segments:
                        continue
                    resolved = copy.deepcopy(loser)
                    resolved.id = str(uuid.uuid4())
                    resolved.parent_word_id = loser.id
                    resolved.origin_year = year
                    resolved.origin_type = "homophony_resolution"
                    resolved.origin_rule = "lexical disambiguation"
                    resolved.segments.insert(0, copy.deepcopy(loser.segments[0]))
                    resolved.frequency = max(0.1, loser.frequency * 0.7)
                    resolved.ensure_stress()
                    replacements.append(resolved)
                    loser.active = False

        state.lexicon.words.extend(replacements)
        return replacements

    @staticmethod
    def _replacement_from(donor: Word, target: Word, year: int, origin_type: str) -> Word:
        replacement = copy.deepcopy(donor)
        replacement.id = str(uuid.uuid4())
        replacement.parent_word_id = donor.id
        replacement.concept_id = target.concept_id
        replacement.polysemy = set()
        replacement.origin_year = year
        replacement.origin_type = origin_type
        replacement.origin_rule = origin_type.replace("_", " ")
        replacement.source_id = None
        replacement.frequency = max(0.12, target.frequency * 0.75)
        replacement.morpheme_boundaries = set(donor.morpheme_boundaries)
        return replacement

    @staticmethod
    def _donor(words: Iterable[Word], target: Word, rng: random.Random) -> Optional[Word]:
        candidates = [word for word in words if word is not target and word.active and word.concept_id != target.concept_id]
        if not candidates:
            return None
        # Vyšší frekvence zvyšuje šanci, ale neuzavírá cestu okrajovým slovům.
        weights = [max(0.05, word.frequency) for word in candidates]
        return rng.choices(candidates, weights=weights, k=1)[0]
