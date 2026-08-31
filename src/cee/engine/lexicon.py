"""Diachronní lexikální obměna: frekvence, konkurence a náhrada kořene."""

from __future__ import annotations

import copy
import random
import uuid
from typing import Callable, Iterable, Optional, Sequence

from cee.core.models import State, Word
from cee.engine.decisions import ChangeDecisionEngine

_FUNCTION_CONCEPTS = frozenset(
    {
        "and",
        "or",
        "not",
        "if",
        "of",
        "to",
        "from",
        "in",
        "on",
        "at",
        "with",
        "for",
        "by",
        "this",
        "that",
        "i",
        "you",
        "we",
        "he",
        "she",
        "it",
        "who",
        "what",
        "where",
        "when",
        "how",
    }
)
_FUNCTION_MARKERS = (
    "pronoun",
    "suffix",
    "prefix",
    "particle",
    "classifier",
    "determiner",
    "article",
    "conjunction",
    "preposition",
    "postposition",
    "demonstrative",
    "interrogative",
    "negative",
    "possessive",
    "reciprocal",
    "causative",
    "locative",
    "genitive",
)


def infer_lexical_class(concept_id: str, *, is_grammatical: bool = False) -> str:
    """Vrátí konzervativní základní třídu bez závislosti na ontologii.

    CEE zatím nepotřebuje automaticky hádat jemný sémantický význam každého
    konceptu. Pro frekvenční model a řešení homofonie stačí robustní minimum:
    rozlišit gramatická/funkční slova od obsahových. Rozhodnutí je záměrně
    malé, vysvětlitelné a v importéru vždy přepsatelné explicitní hodnotou.
    """
    if is_grammatical:
        return "function"
    normalized = concept_id.strip().lower()
    compact = "".join(char for char in normalized if char.isalnum())
    if normalized in _FUNCTION_CONCEPTS or any(marker in compact for marker in _FUNCTION_MARKERS):
        return "function"
    return "content"


def annotate_basic_lexical_class(word: Word) -> None:
    """Doplní výchozí třídu a frekvenční prior, pokud je uživatel neurčil."""
    explicit = word.grammatical_features.get("lexical.class", "").strip().lower()
    lexical_class = explicit if explicit in {"function", "content"} else infer_lexical_class(
        word.concept_id, is_grammatical=word.is_grammatical
    )
    word.grammatical_features["lexical.class"] = lexical_class
    word.grammatical_features.setdefault(
        "lexical.classification", "explicit" if explicit else "heuristic-basic-v1"
    )
    # Funkční prvky mají bez dodaného korpusu vyšší, ale nikoli absolutní
    # frekvenční prior. Explicitní frekvence se nepřepisuje: importer ji
    # nastaví až po této funkci, pokud ji zdroj skutečně obsahuje.
    if lexical_class == "function" and word.frequency == 0.5:
        word.frequency = 0.75


def _is_basic(word: Word) -> bool:
    """První, staré a časté položky považujeme za konzervativnější jádro."""
    return word.frequency >= 0.7


class LexicalEvaluator:
    """Malý, deterministický model životního cyklu lexému.

    Neháže pryč koncepty náhodně: nejdřív vytvoří konkurující náhradu, až
    potom může starý, málo frekventní tvar ustoupit. Výpůjčky a složeniny tak
    zůstávají plnohodnotnými účastníky pozdějších zvukových změn.
    """

    def __init__(
        self,
        replacement_rate: float = 0.015,
        loss_rate: float = 0.01,
        homophony_resolution_rate: float = 1.0,
    ):
        self.replacement_rate = max(0.0, replacement_rate)
        self.loss_rate = max(0.0, loss_rate)
        self.homophony_resolution_rate = min(1.0, max(0.0, homophony_resolution_rate))
        self.decision_engine = ChangeDecisionEngine()
        self.last_homophony_decisions = []

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
                # Homofonie je diagnostická situace, nikoli licence přilepit
                # k poraženému slovu náhodný segment.  Rozhodovací jádro ji
                # posoudí podle automaticky sestavených kontextů. Samotnou
                # náhradu smí provést až reálná událost (sémantika, morfologie
                # nebo kontakt), která dodá její historický původ.
                self.last_homophony_decisions.extend(self.decision_engine.assess_homophones(forms))

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
    def _disambiguation_markers(words: Iterable[Word]):
        """Jednosegmentové markery z aktuálního inventáře ve stabilním pořadí."""
        markers = {}
        for word in words:
            if not word.active:
                continue
            for segment in word.segments:
                key = tuple(sorted(segment.features.items()))
                markers.setdefault(key, segment)
        return [markers[key] for key in sorted(markers)]

    @staticmethod
    def _collision_pressure(winner: Word, loser: Word) -> float:
        """Odhad komunikačního tlaku na rozlišení jedné homofonie.

        Nejde o tvrzení, že bez ručně dodaného korpusu známe skutečnou
        funkční zátěž. Je to transparentní proxy: častá slova ve stejném
        základním lexikálním typu, slovním druhu, doméně a registru soutěží
        více než položky oddělené gramatikou či situací. ``lexical.class``
        (``function``/``content``) je automaticky doplněný už při importu;
        jemnější metadata ``lexical.pos``, ``lexical.domains`` (CSV) a
        ``lexical.register`` jsou volitelná.
        """
        decisions = ChangeDecisionEngine().assess_homophones([winner, loser])
        return decisions[0].pressure if decisions else 0.0

    @staticmethod
    def _donor(words: Iterable[Word], target: Word, rng: random.Random) -> Optional[Word]:
        candidates = [
            word
            for word in words
            if word is not target and word.active and word.concept_id != target.concept_id
        ]
        if not candidates:
            return None
        # Vyšší frekvence zvyšuje šanci, ale neuzavírá cestu okrajovým slovům.
        weights = [max(0.05, word.frequency) for word in candidates]
        return rng.choices(candidates, weights=weights, k=1)[0]
