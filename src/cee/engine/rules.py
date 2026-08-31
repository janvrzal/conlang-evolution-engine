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
    #: Strukturální operace, které nelze vyjádřit prostým přepsáním rysu.
    #: Podporované: swap_next, geminate, degeminate, lengthen, shorten,
    #: compensatory_lengthening, stress_initial, stress_penult a stress_final.
    operation: Optional[str] = None
    #: Stabilní identifikátor schématu, z něhož pravidlo vzniklo. Ručně
    #: zadaná pravidla ho mít nemusí; používá ho kalibrace generátoru.
    schema_id: Optional[str] = None
    #: Souběžná rotace kontrastů pro systémový řetězový posun.
    chain_steps: Optional[List[tuple[Dict[str, str], Dict[str, str]]]] = None

    def matching_indices(self, word: Word) -> List[int]:
        """Najde terče bez mutace tvaru; používá ho generátor i aplikátor."""
        if self.year is not None and self.year < word.origin_year:
            return []
        word.ensure_stress()
        targets: List[int] = []
        for i, segment in enumerate(word.segments):
            matches_target = (
                any(segment.matches(source) for source, _ in self.chain_steps or [])
                if self.operation == "chain_shift"
                else segment.matches(self.target)
            )
            if not matches_target:
                continue
            if self.prosody == "unstressed" and i == word.stress_index:
                continue
            if self.prosody == "stressed" and i != word.stress_index:
                continue
            if self.syllable_part:
                from cee.engine.prosody import syllable_position

                if syllable_position(word, i) != self.syllable_part:
                    continue
            if self.env_before:
                if self.env_before.get("_boundary") == "+":
                    if i != 0:
                        continue
                elif i == 0 or not word.segments[i - 1].matches(self.env_before):
                    continue
            if self.env_after:
                if self.env_after.get("_boundary") == "+":
                    if i != len(word.segments) - 1:
                        continue
                elif self.env_after.get("_lookahead_vowel") == "+":
                    environment = {
                        key: value
                        for key, value in self.env_after.items()
                        if not key.startswith("_")
                    }
                    if not any(
                        candidate.features.get("syl") == "+" and candidate.matches(environment)
                        for candidate in word.segments[i + 1 :]
                    ):
                        continue
                elif i == len(word.segments) - 1 or not word.segments[i + 1].matches(
                    self.env_after
                ):
                    continue
            targets.append(i)
        return targets

    def can_apply_to_word(self, word: Word) -> bool:
        """Levný predikát pro výběr kandidátního pravidla.

        Záměrně nevytváří deep-copy každého slova. U mazání kontroluje stejnou
        minimální prosodii jako aplikátor, aby se do historie nedostávalo
        pravidlo, které reálně nikam nezasáhne.
        """
        targets = self.matching_indices(word)
        if not targets:
            return False
        if self.operation == "swap_next":
            return any(i + 1 < len(word.segments) for i in targets)
        if self.operation == "chain_shift":
            return bool(targets)
        if self.operation == "tonogenesis":
            return any(i + 1 < len(word.segments) for i in targets)
        if self.operation == "tone_shift":
            return any(i in word.tones for i in targets)
        if self.operation == "geminate":
            return True
        if self.operation == "degeminate":
            return any(
                i + 1 < len(word.segments)
                and word.segments[i].features == word.segments[i + 1].features
                for i in targets
            )
        if self.operation == "lengthen":
            return any(
                word.segments[i].features.get("syl") == "+" and i not in word.long_nuclei
                for i in targets
            )
        if self.operation == "shorten":
            return any(i in word.long_nuclei for i in targets)
        if self.operation == "compensatory_lengthening":
            lost = {
                i + 1
                for i in targets
                if i + 1 < len(word.segments)
                and (
                    i + 1 == len(word.segments) - 1
                    or (
                        i + 2 < len(word.segments)
                        and word.segments[i + 2].features.get("cons") == "+"
                    )
                )
            }
            return bool(lost) and self._passes_minimality(
                word,
                word.segments,
                [segment for i, segment in enumerate(word.segments) if i not in lost],
            )
        if self.action.get("delete") == "+":
            return self._passes_minimality(
                word,
                word.segments,
                [segment for i, segment in enumerate(word.segments) if i not in set(targets)],
            )
        if self.operation in {"stress_initial", "stress_penult", "stress_final"}:
            nuclei = word.syllable_nuclei()
            if not nuclei:
                return False
            desired = {
                "stress_initial": nuclei[0],
                "stress_final": nuclei[-1],
                "stress_penult": nuclei[-2] if len(nuclei) > 1 else nuclei[0],
            }[self.operation]
            return word.stress_index != desired
        if self.insert and self.insert_features:
            return True

        # Pravidlo odpovídající terči ještě nemusí nic změnit: například
        # finální odznělení /p/ → /p/ nesmí blokovat pozdější kandidát pro
        # skutečně znělé /b/. Referenční zápisy ($before/$after) hodnotíme
        # stejně jako aplikátor.
        for i in targets:
            segment = word.segments[i]
            for feature, new_value in self.action.items():
                if isinstance(new_value, str) and new_value.startswith("$after:"):
                    if i + 1 < len(word.segments):
                        expected = word.segments[i + 1].features.get(
                            new_value.split(":", 1)[1], "0"
                        )
                    else:
                        continue
                elif isinstance(new_value, str) and new_value.startswith("$before:"):
                    if i > 0:
                        expected = word.segments[i - 1].features.get(
                            new_value.split(":", 1)[1], "0"
                        )
                    else:
                        continue
                else:
                    expected = new_value
                if segment.features.get(feature) != expected:
                    return True
        return False

    def apply_to_word(self, word: Word) -> bool:
        """
        Aplikuje pravidlo na slovo in-place. Vrací True, pokud došlo ke změně.
        Provedeno ve dvou fázích (identifikace -> mutace) pro zamezení self-feeding artefaktů.
        """
        targets_to_modify = self.matching_indices(word)
        # Fáze 2: Simultánní mutace
        if not targets_to_modify:
            return False

        if self.operation == "swap_next":
            changed = False
            for i in sorted(targets_to_modify, reverse=True):
                if i + 1 < len(word.segments):
                    word.segments[i], word.segments[i + 1] = word.segments[i + 1], word.segments[i]
                    changed = True
            word.ensure_stress()
            return changed

        if self.operation == "chain_shift":
            changed = False
            for i in targets_to_modify:
                for source, action in self.chain_steps or []:
                    if word.segments[i].matches(source):
                        word.segments[i].features.update(action)
                        changed = True
                        break
            word.ensure_stress()
            return changed

        if self.operation == "tonogenesis":
            changed = False
            removed: set[int] = set()
            for i in targets_to_modify:
                following = i + 1
                if following >= len(word.segments):
                    continue
                coda = word.segments[following]
                word.tones[i] = "L" if coda.features.get("voi") == "+" else "H"
                removed.add(following)
                changed = True
            if not changed:
                return False
            def remap(index: int) -> int:
                return index - sum(1 for removed_index in removed if removed_index < index)
            word.segments = [segment for index, segment in enumerate(word.segments) if index not in removed]
            word.long_nuclei = {remap(index) for index in word.long_nuclei if index not in removed}
            word.tones = {remap(index): tone for index, tone in word.tones.items() if index not in removed}
            word.ensure_stress()
            return True

        if self.operation == "tone_shift":
            changed = False
            rotation = {"H": "R", "R": "L", "L": "H"}
            for i in targets_to_modify:
                if i in word.tones:
                    word.tones[i] = rotation.get(word.tones[i], "H")
                    changed = True
            return changed

        if self.operation == "geminate":
            word.segments = [
                part
                for i, segment in enumerate(word.segments)
                for part in (
                    [segment, Segment(features=dict(segment.features))]
                    if i in targets_to_modify
                    else [segment]
                )
            ]
            word.ensure_stress()
            return True

        if self.operation == "degeminate":
            targets = set(targets_to_modify)
            remaining = [
                segment
                for i, segment in enumerate(word.segments)
                if not (
                    i in targets
                    and i + 1 < len(word.segments)
                    and segment.features == word.segments[i + 1].features
                )
            ]
            if len(remaining) == len(word.segments):
                return False
            word.segments = remaining
            word.ensure_stress()
            return True

        if self.operation in {"lengthen", "shorten"}:
            if self.operation == "lengthen":
                word.long_nuclei.update(
                    i for i in targets_to_modify if word.segments[i].features.get("syl") == "+"
                )
            else:
                word.long_nuclei.difference_update(targets_to_modify)
            word.ensure_stress()
            return True

        if self.operation == "compensatory_lengthening":
            # Jedna historická událost: ztráta obstruenty v kodě a délka
            # předcházejícího vokálu. Samotné prodloužení před onsetem by
            # nebylo kompenzační dloužení, proto ho sem nepouštíme.
            lost: set[int] = set()
            lengthened: set[int] = set()
            for i in targets_to_modify:
                following = i + 1
                if following >= len(word.segments):
                    continue
                coda = following == len(word.segments) - 1 or (
                    following + 1 < len(word.segments)
                    and word.segments[following + 1].features.get("cons") == "+"
                )
                if coda:
                    lost.add(following)
                    lengthened.add(i)
            if not lost:
                return False

            remaining = [segment for i, segment in enumerate(word.segments) if i not in lost]
            if not self._passes_minimality(word, word.segments, remaining):
                return False

            # Přepočet indexů zachová i délky, které ve slově byly předtím.
            def new_index(index: int) -> int:
                return index - sum(1 for removed in lost if removed < index)

            word.segments = remaining
            word.long_nuclei = {
                new_index(index) for index in word.long_nuclei | lengthened if index not in lost
            }
            word.ensure_stress()
            return True

        if self.operation in {"stress_initial", "stress_penult", "stress_final"}:
            nuclei = word.syllable_nuclei()
            if not nuclei:
                return False
            if self.operation == "stress_initial":
                word.stress_index = nuclei[0]
            elif self.operation == "stress_final":
                word.stress_index = nuclei[-1]
            else:
                word.stress_index = nuclei[-2] if len(nuclei) > 1 else nuclei[0]
            return True

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
                if isinstance(new_value, str) and new_value.startswith("$after:"):
                    if i + 1 < len(word.segments):
                        segment.features[feature] = word.segments[i + 1].features.get(
                            new_value.split(":", 1)[1], "0"
                        )
                elif isinstance(new_value, str) and new_value.startswith("$before:"):
                    if i > 0:
                        segment.features[feature] = word.segments[i - 1].features.get(
                            new_value.split(":", 1)[1], "0"
                        )
                else:
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
                vysledek.append(Segment(features=dict(self.insert_features or {})))

            vysledek.append(segment)

            if i in pozice and self.insert == "after":
                vysledek.append(Segment(features=dict(self.insert_features or {})))

        return vysledek
