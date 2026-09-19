"""Diachronní lexikální obměna: frekvence, konkurence a náhrada kořene."""

from __future__ import annotations

import copy
import random
import uuid
from dataclasses import replace
from typing import Callable, Iterable, Optional, Sequence

from cee.core.models import State, Word
from cee.engine.decisions import ChangeDecisionEngine
from cee.engine.morphology import MorphologyEvaluator

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
        homophony_policy: str = "off",
        homophony_strategies: Optional[dict] = None,
        innovation_rate: float = 0.0,
        innovation_sources: Optional[dict[str, float]] = None,
    ):
        self.replacement_rate = max(0.0, replacement_rate)
        self.loss_rate = max(0.0, loss_rate)
        self.homophony_resolution_rate = min(1.0, max(0.0, homophony_resolution_rate))
        self.homophony_policy = homophony_policy if homophony_policy in {"off", "audit", "resolve"} else "off"
        self.homophony_strategies = dict(homophony_strategies or {})
        self.innovation_rate = min(1.0, max(0.0, innovation_rate))
        self.innovation_sources = {
            str(source): max(0.0, float(weight))
            for source, weight in (innovation_sources or {}).items()
            if str(source)
        }
        self.decision_engine = ChangeDecisionEngine()
        self.last_homophony_decisions = []
        self.last_competitions: list[dict[str, object]] = []

    def evaluate(
        self,
        state: State,
        year: int,
        rng: random.Random,
        *,
        taboo_concepts: Sequence[str] = (),
        render: Optional[Callable[[Word], str]] = None,
    ) -> list[Word]:
        active = [word for word in state.lexicon.words if word.active]
        if not active:
            return []

        mobility = state.social.get("mobility", 0.5)
        standard = state.social.get("standardization", 0.0)
        replacements: list[Word] = []

        for word in active:
            # Frekvenci rozběhnuté synonymní soutěže spravuje samostatný
            # model níže; obecná stabilita by jinak každý krok mazala i
            # právě se šířící inovaci.
            if len(state.lexicon.get_words(word.concept_id)) > 1:
                continue
            stability = 0.65 if _is_basic(word) else 0.25
            word.frequency = min(1.0, max(0.01, word.frequency + (stability - 0.5) * 0.08))

            # Standardizace chrání existující tvar; mobilita naopak podporuje
            # soutěž synonym a náhrad.
            rate = self.replacement_rate * (1.0 + mobility) * (1.0 - standard)
            if _is_basic(word) or rng.random() >= rate:
                continue

            if rng.random() < self.innovation_rate:
                replacement = self._motivated_root(state, active, word, year, rng, render)
            else:
                donor = self._donor(active, word, rng)
                replacement = self._replacement_from(donor, word, year, "lexical_replacement") if donor else None
            if replacement is None:
                continue
            replacement.grammatical_features["lexical.variant_for"] = word.lineage_id or word.id
            replacement.grammatical_features["lexical.stage"] = "introduced"
            replacements.append(replacement)

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
            replacement.grammatical_features["lexical.register"] = "circumlocution"
            replacement.grammatical_features["lexical.euphemism_for"] = word.concept_id
            replacements.append(replacement)
            word.active = False

        if self.homophony_policy != "off" and render:
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
                for decision in self.decision_engine.assess_homophones(forms):
                    if self.homophony_policy != "resolve" or decision.action != "needs_legitimate_innovation":
                        self.last_homophony_decisions.append(decision)
                        continue
                    if rng.random() > self.homophony_resolution_rate:
                        self.last_homophony_decisions.append(decision)
                        continue
                    words_by_id = {word.id: word for word in [*state.lexicon.words, *replacements]}
                    winner, loser = words_by_id[decision.winner_id], words_by_id[decision.loser_id]
                    strategy = self.homophony_strategies.get(loser.concept_id) or self._automatic_homophony_strategy(
                        state, loser
                    )
                    resolved = self._resolve_homophony(state, winner, loser, year, strategy)
                    self.last_homophony_decisions.append(
                        replace(
                            decision,
                            action=resolved or "needs_legitimate_innovation",
                            reason=(
                                f"Kolize vyřešena historickou událostí: {resolved}."
                                if resolved
                                else decision.reason
                            ),
                        )
                    )

        state.lexicon.words.extend(replacements)
        self._advance_competitions(state, mobility=mobility, standard=standard)
        return replacements

    def _advance_competitions(self, state: State, *, mobility: float, standard: float) -> None:
        """Posune rozběhnuté synonymní soutěže o jednu historickou epochu."""
        self.last_competitions = []
        by_concept: dict[str, list[Word]] = {}
        for word in state.lexicon.words:
            if word.active:
                by_concept.setdefault(word.concept_id, []).append(word)
        for concept, variants in by_concept.items():
            innovators = [word for word in variants if word.grammatical_features.get("lexical.variant_for")]
            incumbents = [word for word in variants if word not in innovators]
            if not innovators or not incumbents:
                continue
            innovator = max(innovators, key=lambda word: word.frequency)
            incumbent = max(incumbents, key=lambda word: word.frequency)
            # Standardizace není jen globální brzda: při dostatečné síle
            # instituce vybere konkrétní nejrozšířenější variantu a označí ji
            # jako normu. Zbývající varianty mohou dál přežívat, ale soutěží
            # proti skutečnému standardnímu tvaru.
            if standard >= 0.6:
                standard_variant = max(variants, key=lambda word: word.frequency)
                standard_variant.grammatical_features["lexical.standard_variant"] = "true"
                standard_variant.frequency = min(1.0, standard_variant.frequency + 0.03 * standard)
            source_group = innovator.grammatical_features.get("social.group", "").strip()
            target_group = incumbent.grammatical_features.get("social.group", "").strip()
            network = 1.0
            if source_group and target_group and source_group != target_group:
                source = state.communities.get(source_group)
                target = state.communities.get(target_group)
                if source is not None and target is not None:
                    connection = max(
                        float(source.links.get(target_group, 0.0)),
                        float(target.links.get(source_group, 0.0)),
                        float(source.bilingualism.get(target_group, 0.0)),
                        float(target.bilingualism.get(source_group, 0.0)),
                    )
                    network = 0.25 + 0.75 * connection
            gain = 0.12 * (0.4 + mobility) * (1.0 - standard) * network
            shift = min(incumbent.frequency, gain * max(0.15, 1.0 - innovator.frequency))
            innovator.frequency = min(1.0, innovator.frequency + shift)
            incumbent.frequency = max(0.01, incumbent.frequency - shift)
            stage = "dominant" if innovator.frequency >= incumbent.frequency else "spreading"
            innovator.grammatical_features["lexical.stage"] = stage
            resolved = False
            if innovator.frequency >= incumbent.frequency * 2 and incumbent.frequency <= self.loss_rate * 8:
                incumbent.active = False
                innovator.grammatical_features["lexical.stage"] = "established"
                resolved = True
            self.last_competitions.append(
                {
                    "concept_id": concept,
                    "incumbent_id": incumbent.id,
                    "innovator_id": innovator.id,
                    "stage": innovator.grammatical_features["lexical.stage"],
                    "resolved": resolved,
                    "network_spread": round(network, 6),
                }
            )

    @staticmethod
    def _resolve_homophony(
        state: State, winner: Word, loser: Word, year: int, strategy: object
    ) -> Optional[str]:
        """Provede pouze explicitně doložený typ lexikální inovace.

        Specifikace je součástí historie projektu. Bez ní vysoký tlak jen
        zůstane auditním záznamem — algoritmus nevymýšlí afix ani kořen.
        """
        if not isinstance(strategy, dict):
            return None
        kind = str(strategy.get("kind", ""))
        if kind == "colexification":
            winner.polysemy.add(loser.concept_id)
            winner.grammatical_features["lexical.homophony_resolution"] = "colexification"
            loser.active = False
            return kind

        morphology = MorphologyEvaluator()
        loser.active = False
        try:
            if kind == "semantic_shift":
                source = state.lexicon.get_word(str(strategy.get("source", "")))
                if source is None:
                    loser.active = True
                    return None
                source.polysemy.add(loser.concept_id)
                source.grammatical_features["lexical.homophony_resolution"] = "semantic_shift"
                source.grammatical_features["lexical.semantic_shift_year"] = str(year)
                return kind
            if kind == "derivation":
                derived = morphology.derive(
                    state,
                    str(strategy.get("root", "")),
                    str(strategy.get("affix", "")),
                    loser.concept_id,
                    prefix=strategy.get("prefix"),
                )
                if derived is not None:
                    derived.origin_type = "homophony_derivation"
                    derived.origin_rule = "homophony:derivation"
                    return kind
            if kind == "productive_derivation":
                affix = state.lexicon.get_word(str(strategy.get("affix", "")))
                # Kořen je právě poražený lexém. Přípona/předpona je však
                # samostatně doložený produktivní morfém, ne nouzový segment.
                if affix is None or not affix.is_grammatical:
                    return None
                productivity = float(affix.grammatical_features.get("morphology.productivity", "0"))
                if productivity <= 0:
                    return None
                use_prefix = state.affixation_strategy == "prefix"
                left, right = (affix, loser) if use_prefix else (loser, affix)
                derived = copy.deepcopy(loser)
                derived.id = str(uuid.uuid4())
                derived.parent_word_id = loser.id
                derived.active = True
                derived.segments = copy.deepcopy(left.segments) + copy.deepcopy(right.segments)
                derived.morpheme_boundaries = {len(left.segments)}
                derived.origin_year = year
                derived.origin_type = "homophony_productive_derivation"
                derived.origin_rule = "homophony:productive_derivation"
                derived.grammatical_features = {
                    **derived.grammatical_features,
                    "morphology.affix_id": affix.id,
                    "lexical.homophony_resolution": "productive_derivation",
                }
                derived.ensure_stress()
                state.lexicon.words.append(derived)
                return kind
            if kind == "compound":
                compound = morphology.compound(
                    state,
                    str(strategy.get("head", "")),
                    str(strategy.get("modifier", "")),
                    loser.concept_id,
                )
                if compound is not None:
                    compound.origin_type = "homophony_compound"
                    compound.origin_rule = "homophony:compound"
                    return kind
        finally:
            if not state.lexicon.get_words(loser.concept_id):
                loser.active = True
        return None

    @staticmethod
    def _automatic_homophony_strategy(state: State, loser: Word) -> Optional[dict[str, str]]:
        """Najde pouze takovou reakci, která už má doložený recept a kořeny.

        Automatika zde nesmí maskovat nevysvětlitelný zásah. Použije jen
        kurátorovanou sémantickou složeninu se dvěma živými kořeny nebo už
        produktivní gramatický afix. Vše ostatní zůstává ve frontě pro autora
        nebo explicitní historickou strategii.
        """
        from cee.semantics.swadesh import available_suggestions

        suggestions = available_suggestions(state, loser.concept_id)
        if suggestions:
            choice = suggestions[0]
            return {"kind": "compound", "head": choice.head, "modifier": choice.modifier}

        productive_affixes = [
            word for word in state.lexicon.words
            if word.active
            and word.is_grammatical
            and word.id != loser.id
            and float(word.grammatical_features.get("morphology.productivity", "0")) > 0
        ]
        if productive_affixes:
            affix = max(
                productive_affixes,
                key=lambda word: (
                    float(word.grammatical_features.get("morphology.productivity", "0")),
                    word.frequency,
                ),
            )
            return {"kind": "productive_derivation", "affix": affix.concept_id}
        return None

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

    def _motivated_root(
        self,
        state: State,
        active: Sequence[Word],
        target: Word,
        year: int,
        rng: random.Random,
        render: Optional[Callable[[Word], str]],
    ) -> Optional[Word]:
        """Vytvoří nový kořen z fonémů daného jazyka a doloží jeho motivaci.

        Nejde o náhodný prefix ani o kopii cizího slova. Nový lexém skládá
        vlastní segmenty jazyka v rozsahu běžných kořenů a vstupuje do stejné
        synonymní soutěže jako výpůjčka či opis. Zdroj motivace je explicitně
        auditovatelný a lze ho vážit konfigurací.
        """
        segments = [segment for word in active for segment in word.segments]
        if len(segments) < 2:
            return None
        sources = self.innovation_sources or {
            "expressive": 0.35 + (1.0 - float(state.social.get("standardization", 0.0))) * 0.25,
            "child_speech": 0.2,
            "trade_slang": 0.1 + float(state.social.get("mobility", 0.5)) * 0.3,
            "local_substrate": 0.15 + float(state.map.get("contact_intensity", 0.0)) * 0.2,
        }
        names = [name for name, weight in sources.items() if weight > 0]
        if not names:
            return None
        source = rng.choices(names, weights=[sources[name] for name in names], k=1)[0]
        # Dvouslabičný až krátký tříslabičný kořen: délka se opírá o současný
        # lexikon, ale nikdy neprodukuje jednosegmentový artefakt.
        lengths = [max(2, min(6, len(word.segments))) for word in active if word.segments]
        length = rng.choice(lengths) if lengths else 2
        existing_forms = {render(word) for word in active} if render else set()
        for _ in range(12):
            candidate = Word(
                concept_id=target.concept_id,
                segments=[copy.deepcopy(rng.choice(segments)) for _ in range(length)],
                origin_year=year,
                frequency=max(0.12, target.frequency * 0.65),
                parent_word_id=target.id,
                origin_type=f"lexical_innovation_{source}",
                origin_rule=f"motivated_root:{source}",
                grammatical_features={
                    "lexical.motivation": source,
                    "lexical.innovation_year": str(year),
                },
            )
            if render is None or render(candidate) not in existing_forms:
                return candidate
        return None

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
