import random
from dataclasses import dataclass
from typing import Optional

from cee.core.models import Lexicon
from cee.engine.decisions import SemanticContextModel
from cee.semantics.graph import SemanticGraph


@dataclass(frozen=True)
class SemanticProposal:
    """Auditovatelný návrh jedné sémantické inovace."""

    word_lineage_id: str
    source_concept: str
    target_concept: Optional[str]
    kind: str
    pressure: float
    evidence_weight: float
    evidence_type: str
    competitor_lineage_id: Optional[str] = None

    def duration(self, base_years: int = 240) -> int:
        """Silnější tlak urychlí přijetí, ale nezmění význam okamžitě."""
        if base_years <= 0:
            return 0
        return max(80, round(base_years * (1.3 - 0.7 * self.pressure)))

    def adoption_threshold(self, frequency: float) -> float:
        """Okamžik, kdy se nové užití stane součástí živého lexikonu."""
        bounded_frequency = max(0.0, min(1.0, frequency))
        if self.kind == "loss":
            return min(
                0.9,
                max(0.4, 0.5 + 0.25 * bounded_frequency + 0.1 * (1 - self.pressure)),
            )
        return min(0.85, max(0.3, 0.65 - 0.25 * bounded_frequency + 0.1 * (1 - self.pressure)))


class SemanticEvaluator:
    """
    Vykonává sémantické posuny nad lexikonem na základě sémantického grafu.
    Simuluje to, jak slova v čase získávají nové významy (polysemie) a ztrácejí staré.
    """

    def __init__(
        self,
        graph: SemanticGraph,
        shift_prob: float = 0.05,
        forget_prob: float = 0.01,
        seed: int = 42,
    ):
        """
        :param graph: Načtená síť Concepticon/DatSemShift/CLICS
        :param shift_prob: Šance (0.0 - 1.0), že jedno slovo získá nový význam během jednoho průchodu (např. jednoho století)  # noqa: E501
        :param forget_prob: Šance (0.0 - 1.0), že slovo s více významy zapomene jeden ze svých starších významů.  # noqa: E501
        :param seed: Seed pro deterministické hody kostkou (nutné pro hashování stromu historie)
        """
        self.graph = graph
        self.shift_prob = shift_prob
        self.forget_prob = forget_prob
        self.random = random.Random(seed)
        self.context_model = SemanticContextModel()

    def extension_candidates(self, lexicon: Lexicon) -> list[SemanticProposal]:
        """Sestaví doložená rozšíření a posuny bez náhodného losování."""
        covered = {
            meaning.lower()
            for word in lexicon.words
            if word.active
            for meaning in (word.concept_id, *word.polysemy)
        }
        candidates: list[SemanticProposal] = []

        for word in lexicon.words:
            if not word.active:
                continue
            lineage_id = word.lineage_id or word.id
            existing = {word.concept_id.lower(), *(meaning.lower() for meaning in word.polysemy)}
            for source in (word.concept_id, *sorted(word.polysemy)):
                shifts = self.graph.get_possible_shifts(source)
                positive_weights = [max(0.0, float(item[2])) for item in shifts]
                local_max = max(positive_weights, default=0.0)
                if local_max <= 0:
                    continue
                for target, _name, raw_weight, edge_type in shifts:
                    target_id = str(target).lower()
                    if target_id in existing:
                        continue
                    evidence_weight = max(0.0, float(raw_weight))
                    evidence_strength = evidence_weight / local_max
                    exposure = 0.55 + 0.45 * max(0.0, min(1.0, word.frequency))
                    # Už existující samostatný lexém trochu snižuje potřebu
                    # rozšíření, ale neblokuje běžnou kolexifikaci.
                    lexical_need = 0.85 if target_id in covered else 1.0
                    pressure = min(1.0, evidence_strength * exposure * lexical_need)
                    kind = "shift" if edge_type == "shift" else "extension"
                    candidates.append(
                        SemanticProposal(
                            word_lineage_id=lineage_id,
                            source_concept=str(source).lower(),
                            target_concept=target_id,
                            kind=kind,
                            pressure=round(pressure, 6),
                            evidence_weight=round(evidence_weight, 6),
                            evidence_type=str(edge_type),
                        )
                    )
        return candidates

    @staticmethod
    def _stability(word) -> float:
        raw = word.grammatical_features.get(
            "semantic.stability", word.grammatical_features.get("lexical.stability", "0.5")
        )
        try:
            return max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            return 0.5

    def loss_candidates(self, lexicon: Lexicon) -> list[SemanticProposal]:
        """Najde redundantní významy vytlačované silnějším synonymem.

        Nízká frekvence sama nestačí. Význam lze ztratit jen tehdy, pokud jej
        pokrývá jiný aktivní lexém ve srovnatelném komunikačním kontextu.
        """
        meanings: dict[str, list] = {}
        for word in lexicon.words:
            if not word.active:
                continue
            for meaning in {word.concept_id.lower(), *(item.lower() for item in word.polysemy)}:
                meanings.setdefault(meaning, []).append(word)

        candidates: list[SemanticProposal] = []
        for meaning, words in meanings.items():
            if len(words) < 2:
                continue
            strength = {
                word.id: max(0.0, min(1.0, word.frequency)) * (0.5 + 0.5 * self._stability(word))
                for word in words
            }
            # Při shodné síle zachováme pořadí lexikonu. UUID objektu Word
            # nesmí rozhodovat o historickém výsledku mimo simulátor.
            winner = max(words, key=lambda word: strength[word.id])
            winner_strength = strength[winner.id]
            if winner_strength <= 0:
                continue
            for loser in words:
                if loser is winner:
                    continue
                advantage = max(0.0, (winner_strength - strength[loser.id]) / winner_strength)
                if advantage <= 0:
                    continue
                context_overlap, evidence_level = self.context_model.overlap(loser, winner)
                if context_overlap <= 0:
                    continue
                # Ztráta jednoho z více významů je méně riskantní než zánik
                # posledního užití celého lexému.
                survival = 1.0 if loser.polysemy else 0.65
                pressure = min(1.0, (advantage * context_overlap) ** 0.5 * survival)
                candidates.append(
                    SemanticProposal(
                        word_lineage_id=loser.lineage_id or loser.id,
                        source_concept=meaning,
                        target_concept=None,
                        kind="loss",
                        pressure=round(pressure, 6),
                        evidence_weight=round(advantage, 6),
                        evidence_type=f"synonym-competition:{evidence_level}",
                        competitor_lineage_id=winner.lineage_id or winner.id,
                    )
                )
        return candidates

    def propose_changes(
        self,
        lexicon: Lexicon,
        random_gen: Optional[random.Random] = None,
    ) -> list[SemanticProposal]:
        """Navrhne nanejvýš jednu změnu podle datové a lexikální opory.

        Hrana v CLICS/DatSemShift určuje, *který* posun je legitimní. Konkurence
        živých synonym určuje, *který* význam může zaniknout bez ztráty
        sémantického pokrytí. ``shift_prob`` a ``forget_prob`` jsou pouze míry
        historických příležitostí za století, ne losování cílového významu.
        """
        rng = random_gen or self.random
        opportunities: list[SemanticProposal] = []
        groups = (
            (self.extension_candidates(lexicon), self.shift_prob),
            (self.loss_candidates(lexicon), self.forget_prob),
        )
        for candidates, rate in groups:
            if not candidates or rate <= 0:
                continue
            candidates.sort(
                key=lambda item: (
                    -item.pressure,
                    -item.evidence_weight,
                )
            )
            strongest = candidates[0]
            if rng.random() < rate * strongest.pressure:
                opportunities.append(strongest)

        if not opportunities:
            return []
        opportunities.sort(
            key=lambda item: (
                -(item.pressure * (self.forget_prob if item.kind == "loss" else self.shift_prob)),
                -item.evidence_weight,
            )
        )
        return [opportunities[0]]

    def evaluate(
        self,
        lexicon: Lexicon,
        random_gen: Optional[random.Random] = None,
    ) -> Lexicon:
        """
        Projde lexikon a aplikuje pravděpodobnostní sémantické změny.
        Modifikuje in-place, ale vrací pro pohodlí řetězení.
        """
        rng = random_gen or self.random
        for word in lexicon.words:
            if not word.active:
                continue
            # 1. Získání nového významu přes Kolexifikaci (Rozšíření CLICS)
            if rng.random() < self.shift_prob:
                # Rozhodneme se, z jakého aktuálního významu se slovo odrazí.
                available_origins = [word.concept_id] + sorted(word.polysemy)
                origin = rng.choice(available_origins)

                # Zkusíme najít kolexifikaci
                new_concept = self.graph.random_shift(
                    origin, random_gen=rng, edge_type="colexification"
                )
                if (
                    new_concept
                    and new_concept != word.concept_id
                    and new_concept not in word.polysemy
                ):
                    # Slovo získalo nový význam! (Polysémie)
                    word.polysemy.add(new_concept)

            # 2. Úplný sémantický posun (DatSemShift)
            # Děje se s menší pravděpodobností
            if rng.random() < (self.shift_prob * 0.5):
                # Slovo ztratí starý kořenový význam a přesune se
                new_concept = self.graph.random_shift(
                    word.concept_id, random_gen=rng, edge_type="shift"
                )
                if new_concept and new_concept != word.concept_id:
                    # Přesuneme starý concept_id do polysémie, kdyby ho jazyk ještě chvíli používal,
                    # a posuneme hlavní kořen na new_concept
                    word.polysemy.add(word.concept_id)
                    word.concept_id = new_concept
                    if new_concept in word.polysemy:
                        word.polysemy.remove(new_concept)

            # 3. Ztráta starého významu (Zúžení)
            # Pokud má slovo více významů, může jeden ztratit.
            if len(word.polysemy) > 0 and rng.random() < self.forget_prob:
                all_meanings = [word.concept_id] + sorted(word.polysemy)
                to_forget = rng.choice(all_meanings)

                if to_forget == word.concept_id:
                    # Pokud zapomene svůj hlavní význam (kořen), musíme ho nahradit nějakým z polysemie.  # noqa: E501
                    new_root = rng.choice(sorted(word.polysemy))
                    word.polysemy.remove(new_root)
                    word.concept_id = new_root
                else:
                    word.polysemy.remove(to_forget)

        return lexicon
