"""Rozhodovací jádro pro tlaky, které vedou k jazykové změně.

Tato vrstva záměrně nevybírá náhodný zásah do slova.  Ze stavu jazyka nejdřív
odvodí pozorovatelné podmínky a teprve nad nimi mohou evaluátory rozhodovat o
historické události.  První uživatel je homofonie; stejné rozhraní má později
sloužit i zvukovým inovacím a jejich časování.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from cee.core.models import State, Word
from cee.engine.rules import Rule


@dataclass(frozen=True)
class HomophonyDecision:
    """Auditovatelný výsledek pro jednu dvojici shodných forem."""

    winner_id: str
    loser_id: str
    pressure: float
    context_overlap: float
    evidence_level: str
    action: str
    reason: str


@dataclass(frozen=True)
class SoundChangeDecision:
    """Měřitelný tlak a plán šíření jedné fonologické inovace."""

    applicable_words: int
    word_coverage: float
    frequency_coverage: float
    pressure: float
    reason: str

    def duration(self, base_years: int) -> int:
        """Silně podpořená inovace se šíří rychleji, ale nikdy okamžitě."""
        if base_years <= 0:
            return 0
        return max(40, round(base_years * (1.3 - 0.6 * self.pressure)))


class SemanticContextModel:
    """Strojově sestavené komunikační kontexty bez univerzálních POS.

    Role jsou malé, jazykově agnostické typy účasti ve výpovědi (reference,
    událost, vlastnost, vztah, deixis).  Import z Concepticonu je může doplnit
    přes ``semantic.roles``/``semantic.domains``; do té doby se model opírá o
    existující metadata slovníku a konzervativní funkční-vs.-obsahové dělení.
    To je *heuristický* režim a proto nikdy sám nemění formu lexému.
    """

    _ROLE_BY_LEGACY_POS = {
        "noun": "reference",
        "pronoun": "deixis",
        "verb": "event",
        "adj": "property",
        "adjective": "property",
        "adposition": "relation",
        "preposition": "relation",
        "postposition": "relation",
        "particle": "operator",
        "conjunction": "operator",
    }

    @staticmethod
    def _values(word: Word, key: str) -> set[str]:
        return {
            value.strip().lower()
            for value in word.grammatical_features.get(key, "").split(",")
            if value.strip()
        }

    def contexts_for(self, word: Word) -> set[str]:
        explicit_roles = self._values(word, "semantic.roles")
        legacy_roles = self._values(word, "lexical.pos") | self._values(word, "pos")
        roles = explicit_roles or {
            self._ROLE_BY_LEGACY_POS[pos]
            for pos in legacy_roles
            if pos in self._ROLE_BY_LEGACY_POS
        }
        if not roles:
            lexical_class = word.grammatical_features.get("lexical.class", "content")
            roles = {"operator" if lexical_class == "function" else "reference"}

        domains = self._values(word, "semantic.domains") or self._values(word, "lexical.domains")
        contexts = {f"role:{role}" for role in roles}
        contexts.update(f"domain:{domain}" for domain in domains)
        register = word.grammatical_features.get("lexical.register", "").strip().lower()
        if register:
            contexts.add(f"register:{register}")
        return contexts

    def overlap(self, first: Word, second: Word) -> tuple[float, str]:
        """Jaccardův překryv možných konstrukčních kontextů.

        Zdroje s rolí či doménou importovanou z Concepticonu jsou silnější
        evidence než fallback.  Nejde o odhad člověka ani AI: pro daný stav je
        výpočet deterministický a auditovatelný.
        """
        first_contexts, second_contexts = self.contexts_for(first), self.contexts_for(second)
        union = first_contexts | second_contexts
        overlap = len(first_contexts & second_contexts) / len(union) if union else 0.0
        annotated = all(
            self._values(word, "semantic.roles") or self._values(word, "semantic.domains")
            for word in (first, second)
        )
        return overlap, "semantic-metadata" if annotated else "heuristic"


class ChangeDecisionEngine:
    """Z pozorovatelných tlaků vyvozuje, zda je změna vůbec kandidát.

    V této verzi homofonii pouze klasifikuje.  Historickou opravu povolí až
    konkrétní legitimní proces (sémantický posun, doložená derivace, složenina
    nebo kontakt); neexistuje zde žádný nouzový prefix ani náhodný foném.
    """

    def __init__(self, context_model: SemanticContextModel | None = None):
        self.context_model = context_model or SemanticContextModel()

    def assess_homophones(self, words: Iterable[Word]) -> list[HomophonyDecision]:
        active = [word for word in words if word.active]
        decisions: list[HomophonyDecision] = []
        for index, first in enumerate(active):
            for second in active[index + 1 :]:
                overlap, evidence = self.context_model.overlap(first, second)
                frequency = max(0.0, min(1.0, (first.frequency * second.frequency) ** 0.5))
                pressure = min(1.0, frequency * overlap)
                winner, loser = (first, second) if first.frequency >= second.frequency else (second, first)
                action = "monitor" if pressure < 0.35 else "needs_legitimate_innovation"
                decisions.append(
                    HomophonyDecision(
                        winner_id=winner.id,
                        loser_id=loser.id,
                        pressure=round(pressure, 6),
                        context_overlap=round(overlap, 6),
                        evidence_level=evidence,
                        action=action,
                        reason=(
                            "Kontext odlišuje významy dostatečně."
                            if action == "monitor"
                            else "Kolize má funkční zátěž, ale není dostupná legitimní lexikální inovace."
                        ),
                    )
                )
        return decisions

    @staticmethod
    def assess_sound_change(state: State, rule: Rule) -> SoundChangeDecision:
        """Změří, zda má kandidát reálnou oporu v aktuálním lexikonu.

        Inventář sám říká jen to, že hláska existuje. Tato metoda navíc ověří
        skutečné slovní prostředí pravidla a frekvenční rozsah inovace. To je
        minimální kauzální tlak, který lze spočítat bez předstírání znalosti
        konkrétní historické komunity.
        """
        words = [word for word in state.lexicon.words if word.active]
        applicable = [word for word in words if rule.can_apply_to_word(word)]
        total_frequency = sum(max(0.01, word.frequency) for word in words)
        affected_frequency = sum(max(0.01, word.frequency) for word in applicable)
        word_coverage = len(applicable) / len(words) if words else 0.0
        frequency_coverage = affected_frequency / total_frequency if total_frequency else 0.0
        # Typová i frekvenční opora jsou stejně důležité: pravidlo, které
        # zasahuje jen mnoho řídkých slov, a pravidlo s jedním častým zásahem
        # nejsou totožné historické situace.
        pressure = (word_coverage * frequency_coverage) ** 0.5
        return SoundChangeDecision(
            applicable_words=len(applicable),
            word_coverage=round(word_coverage, 6),
            frequency_coverage=round(frequency_coverage, 6),
            pressure=round(pressure, 6),
            reason=(
                "Pravidlo má oporu v reálných slovních prostředích."
                if applicable
                else "Pravidlo nemá v aktuálním lexikonu žádný zásah."
            ),
        )

    @staticmethod
    def sound_change_adoption_threshold(word: Word, rule: Rule, sample: float) -> float:
        """Relativní okamžik, kdy lexém přijme aktivní inovaci (0 až 1).

        Častější slova jsou v tomto prvním modelu dostupnější pro šíření;
        zásah přímo na morfémové hranici je konzervativnější, protože její
        transparentnost může změnu brzdit. Náhodná složka je seedovaná ve
        simulátoru, proto je běh stále reprodukovatelný.
        """
        matching = rule.matching_indices(word)
        boundary_hit = any(index in word.morpheme_boundaries or index + 1 in word.morpheme_boundaries for index in matching)
        frequency_bias = (0.5 - max(0.0, min(1.0, word.frequency))) * 0.3
        boundary_delay = 0.15 if boundary_hit else 0.0
        return min(1.0, max(0.0, sample + frequency_bias + boundary_delay))
