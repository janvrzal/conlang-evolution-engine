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

    def __init__(
        self,
        replacement_rate: float = 0.015,
        loss_rate: float = 0.01,
        homophony_resolution_rate: float = 1.0,
    ):
        self.replacement_rate = max(0.0, replacement_rate)
        self.loss_rate = max(0.0, loss_rate)
        self.homophony_resolution_rate = min(1.0, max(0.0, homophony_resolution_rate))

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
            # Označení nesmí vznikat prostým zdvojením prvního segmentu
            # kolidujícího kořene. To u krátkých slov rychle nafukovalo
            # délku lexikonu (pata -> ppata -> pppata) a zároveň to nebyla
            # samostatná morfologická inovace. Bereme proto jeden existující
            # foném jako nejmenší produktivní rozlišovací prefix; jeho výběr
            # je deterministický a nesmí vytvořit další obsazený tvar.
            markers = self._disambiguation_markers([*active, *replacements])
            occupied = set(groups)
            for forms in groups.values():
                if len(forms) < 2:
                    continue
                winner = max(forms, key=lambda word: word.frequency)
                for loser in forms:
                    if loser is winner or not loser.segments:
                        continue
                    # Plná hodnota zachovává předchozí explicitní chování
                    # ``resolve_homophones: true``. Menší hodnota je
                    # frekvenčně i kontextově vážená pravděpodobnost, že se
                    # mluvčí vůbec rozhodnou kolizi aktivně rozlišovat.
                    pressure = self._collision_pressure(winner, loser)
                    if (
                        self.homophony_resolution_rate < 1.0
                        and rng.random() >= self.homophony_resolution_rate * pressure
                    ):
                        continue
                    resolved = self._disambiguate(loser, markers, occupied, render)
                    if resolved is None:
                        # Když ani jeden foném inventáře tvar nerozliší,
                        # raději kolizi ponecháme pro další lexikální cyklus,
                        # než abychom vymysleli neomezeně dlouhý pseudotvar.
                        continue
                    resolved.id = str(uuid.uuid4())
                    resolved.parent_word_id = loser.id
                    resolved.origin_year = year
                    resolved.origin_type = "homophony_resolution"
                    resolved.origin_rule = "lexical disambiguation prefix"
                    resolved.frequency = max(0.1, loser.frequency * 0.7)
                    resolved.ensure_stress()
                    replacements.append(resolved)
                    occupied.add(render(resolved))
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
        slovním druhu, doméně a registru soutěží více než položky oddělené
        gramatikou či situací. Metadata jsou volitelně v ``grammatical_features``
        jako ``lexical.pos``, ``lexical.domains`` (CSV) a ``lexical.register``.
        Při jejich absenci zůstává neutrální tlak 1.0, aby staré projekty
        nezískaly skrytou klasifikaci z názvu konceptu.
        """
        def value(word: Word, key: str) -> str:
            return word.grammatical_features.get(key, "").strip().lower()

        pressure = 1.0
        winner_pos, loser_pos = value(winner, "lexical.pos"), value(loser, "lexical.pos")
        if winner_pos and loser_pos and winner_pos != loser_pos:
            pressure *= 0.35

        winner_domains = {item.strip() for item in value(winner, "lexical.domains").split(",") if item.strip()}
        loser_domains = {item.strip() for item in value(loser, "lexical.domains").split(",") if item.strip()}
        if winner_domains and loser_domains:
            pressure *= 1.0 if winner_domains & loser_domains else 0.4

        winner_register, loser_register = value(winner, "lexical.register"), value(loser, "lexical.register")
        if winner_register and loser_register and winner_register != loser_register:
            pressure *= 0.5

        # Dvě okrajová slova bývají méně naléhavá než kolize frekventního
        # jádra. Spodní mez zabraňuje tomu, aby položka vypadla z modelu úplně.
        frequency = max(0.15, (max(0.0, winner.frequency) * max(0.0, loser.frequency)) ** 0.5)
        return min(1.0, pressure * frequency)

    @staticmethod
    def _disambiguate(
        loser: Word,
        markers,
        occupied: set[str],
        render: Callable[[Word], str],
    ) -> Optional[Word]:
        for marker in markers:
            candidate = copy.deepcopy(loser)
            candidate.segments.insert(0, copy.deepcopy(marker))
            candidate.morpheme_boundaries = {boundary + 1 for boundary in loser.morpheme_boundaries}
            candidate.morpheme_boundaries.add(1)
            candidate.ensure_stress()
            if render(candidate) not in occupied:
                return candidate
        return None

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
