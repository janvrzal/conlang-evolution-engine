import random
from dataclasses import dataclass
from typing import Mapping, Optional

from cee.core.models import Lexicon
from cee.engine.decisions import SemanticContextModel
from cee.semantics.concepts import ConcepticonIndex
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
    mechanism: Optional[str] = None
    mechanism_pressure: float = 1.0
    mechanism_reason: str = "untyped relation"
    context_pressure: float = 1.0
    context_reason: str = "no configured communicative pressure"

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
        mechanism_overrides: Optional[Mapping[str, str]] = None,
        relation_overrides: Optional[Mapping[str, Mapping[str, str]]] = None,
        concept_index: Optional[ConcepticonIndex] = None,
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
        self.mechanism_overrides = {
            str(key).strip().lower(): str(value).strip().lower()
            for key, value in (mechanism_overrides or {}).items()
        }
        self.relation_overrides = {
            str(key).strip().lower(): {
                str(field).strip().lower(): str(value).strip().lower()
                for field, value in values.items()
            }
            for key, values in (relation_overrides or {}).items()
            if isinstance(values, Mapping)
        }
        self.concept_index = concept_index

    _MECHANISMS = {"metaphor", "metonymy", "generalization", "specialization"}
    _PRESSURE_DOMAINS = {
        "economy": {"commerce", "money", "possession", "quantity", "exchange"},
        "technology": {"technology", "tools", "material culture", "work"},
        "institutions": {"law", "politics", "society", "government", "administration"},
        "religion": {"religion", "ritual", "belief", "spiritual"},
    }
    _BIOME_DOMAINS = {
        "forest": {"plants", "animals", "physical world"},
        "rainforest": {"plants", "animals", "physical world"},
        "les": {"plants", "animals", "physical world"},
        "prales": {"plants", "animals", "physical world"},
        "mountains": {"physical world", "weather", "motion"},
        "mountain": {"physical world", "weather", "motion"},
        "hory": {"physical world", "weather", "motion"},
        "desert": {"weather", "physical world", "water"},
        "poušť": {"weather", "physical world", "water"},
        "coast": {"water", "animals", "motion"},
        "pobřeží": {"water", "animals", "motion"},
        "island": {"water", "animals", "motion"},
        "ostrov": {"water", "animals", "motion"},
    }

    def _relations_for(self, concept_id: str):
        if hasattr(self.graph, "get_possible_relations"):
            relations = self.graph.get_possible_relations(concept_id)
        else:
            relations = [
                (*relation, None) for relation in self.graph.get_possible_shifts(concept_id)
            ]
        return [tuple(list(relation) + [None] * (7 - len(relation)))[:7] for relation in relations]

    def _mechanism_for(self, source: str, target: str, declared: Optional[str]) -> Optional[str]:
        override = self.mechanism_overrides.get(f"{source.lower()}->{target.lower()}")
        mechanism = override or (str(declared).strip().lower() if declared else None)
        return mechanism if mechanism in self._MECHANISMS else None

    def _relation_details(
        self, source: str, target: str, bridge: Optional[str], scope: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        override = self.relation_overrides.get(f"{source.lower()}->{target.lower()}", {})
        return override.get("bridge", bridge), override.get("scope", scope)

    def _domains_for(self, concept_id: str, word) -> set[str]:
        metadata = self.concept_index.lookup(concept_id) if self.concept_index else None
        raw = (
            metadata.semantic_field
            if metadata
            else word.grammatical_features.get("semantic.domains", "")
        )
        return {value.strip().lower() for value in raw.split(",") if value.strip()}

    def _mechanism_pressure(
        self,
        mechanism: Optional[str],
        source: str,
        target: str,
        word,
        bridge: Optional[str],
        scope: Optional[str],
    ) -> tuple[float, str]:
        """Vrátí tlak specifický pro mechanismus, nebo nulu bez evidence."""
        if mechanism is None:
            return 1.0, "untyped relation"
        source_domains = self._domains_for(source, word)
        target_domains = self._domains_for(target, word)
        bridge = (bridge or "").strip().lower()
        scope = (scope or "").strip().lower()
        if mechanism == "metaphor":
            if source_domains and target_domains and source_domains.isdisjoint(target_domains):
                return 1.0, "cross-domain bridge"
            return 0.0, "metaphor needs distinct annotated domains"
        if mechanism == "metonymy":
            valid_bridges = {
                "part_whole",
                "container_content",
                "instrument_action",
                "place_people",
                "producer_product",
            }
            if source_domains & target_domains and bridge in valid_bridges:
                return 1.0, f"same-domain {bridge} bridge"
            return 0.0, "metonymy needs same domain and structural bridge"
        if mechanism == "generalization":
            return (
                (1.0, "declared broader scope")
                if scope == "broader"
                else (0.0, "generalization needs broader scope")
            )
        if mechanism == "specialization":
            return (
                (1.0, "declared narrower scope")
                if scope == "narrower"
                else (0.0, "specialization needs narrower scope")
            )
        return 0.0, "unsupported mechanism"

    @staticmethod
    def _bounded(value: object, default: float = 0.0) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return default

    def _context_pressure(
        self, target: str, word, context: Optional[Mapping[str, object]]
    ) -> tuple[float, str]:
        """Vrátí jen zesílení *doložené* změny, nikdy novou hranu.

        Biome, hospodářství a instituce zde neurčují, co se slovo může stát.
        To dál omezuje CLICS/DatSemShift. Určují pouze, které z již
        doložených možností má v daném jazyce větší komunikační potřebu.
        """
        if not context:
            return 1.0, "no configured communicative pressure"
        semantic = context.get("semantic", {})
        semantic = semantic if isinstance(semantic, Mapping) else {}
        configured = semantic.get("pressures", {})
        configured = configured if isinstance(configured, Mapping) else {}
        target_domains = self._domains_for(target, word)
        matched: list[tuple[float, str]] = []
        for pressure_name, domains in self._PRESSURE_DOMAINS.items():
            strength = self._bounded(configured.get(pressure_name))
            if strength and target_domains & domains:
                matched.append((strength, pressure_name))

        map_config = context.get("map", {})
        map_config = map_config if isinstance(map_config, Mapping) else {}
        biome = str(map_config.get("biome", "")).strip().lower()
        biome_strength = self._bounded(configured.get("biome", 0.35 if biome else 0.0))
        if biome_strength and target_domains & self._BIOME_DOMAINS.get(biome, set()):
            matched.append((biome_strength, f"biome:{biome}"))

        # Autor může přesně přebít mapování širokého pole, aniž by měnil kód.
        for key, raw_strength in configured.items():
            if not str(key).startswith("domain:"):
                continue
            domain = str(key).split(":", 1)[1].strip().lower()
            strength = self._bounded(raw_strength)
            if strength and domain in target_domains:
                matched.append((strength, f"domain:{domain}"))
        if not matched:
            return 1.0, "no matching communicative pressure"
        strength, reason = max(matched)
        return round(1.0 + 0.6 * strength, 6), reason

    def evolve_registers(
        self, lexicon: Lexicon, context: Optional[Mapping[str, object]] = None
    ) -> list[dict[str, object]]:
        """Posune užití lexému mezi několika malými, explicitními registry.

        Nezavádí to umělý nový tvar: opis vzniká až v lexikálním motoru jako
        legitimní náhrada tabu. Tady se eviduje, proč staré slovo přestalo
        patřit do neutrálního užití.
        """
        context = context or {}
        semantic = context.get("semantic", {})
        semantic = semantic if isinstance(semantic, Mapping) else {}
        pressures = semantic.get("pressures", {})
        pressures = pressures if isinstance(pressures, Mapping) else {}
        registers = semantic.get("registers", {})
        registers = registers if isinstance(registers, Mapping) else {}
        social = context.get("social", {})
        social = social if isinstance(social, Mapping) else {}
        formalization = max(
            self._bounded(registers.get("formalization")),
            self._bounded(pressures.get("institutions"))
            * max(0.5, self._bounded(social.get("standardization"))),
        )
        secularization = self._bounded(registers.get("secularization"))
        lexical = context.get("lexical", {})
        lexical = lexical if isinstance(lexical, Mapping) else {}
        taboo_concepts = {str(value).lower() for value in lexical.get("taboo_concepts", [])}
        transitions: list[dict[str, object]] = []
        institutional_domains = self._PRESSURE_DOMAINS["institutions"]

        for word in lexicon.words:
            if not word.active:
                continue
            current = word.grammatical_features.get("lexical.register", "neutral").lower()
            domains = self._domains_for(word.concept_id, word)
            target: Optional[str] = None
            reason = ""
            pressure = 0.0
            if word.concept_id.lower() in taboo_concepts and current != "taboo":
                target, reason, pressure = "taboo", "configured taboo concept", 1.0
            elif current in {"neutral", "ordinary"} and formalization >= 0.5 and domains & institutional_domains:
                target, reason, pressure = "formal", "institutional standardization", formalization
            elif current == "ritual" and secularization >= 0.5:
                target, reason, pressure = "ordinary", "configured ritual diffusion", secularization
            if target is None or target == current:
                continue
            word.grammatical_features["lexical.register"] = target
            transitions.append(
                {
                    "word_lineage_id": word.lineage_id or word.id,
                    "from_register": current,
                    "to_register": target,
                    "pressure": round(pressure, 6),
                    "reason": reason,
                }
            )
        return transitions

    def extension_candidates(
        self, lexicon: Lexicon, context: Optional[Mapping[str, object]] = None
    ) -> list[SemanticProposal]:
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
                relations = self._relations_for(source)
                positive_weights = [max(0.0, float(item[2])) for item in relations]
                local_max = max(positive_weights, default=0.0)
                if local_max <= 0:
                    continue
                for (
                    target,
                    _name,
                    raw_weight,
                    edge_type,
                    declared_mechanism,
                    bridge,
                    scope,
                ) in relations:
                    target_id = str(target).lower()
                    if target_id in existing:
                        continue
                    evidence_weight = max(0.0, float(raw_weight))
                    evidence_strength = evidence_weight / local_max
                    exposure = 0.55 + 0.45 * max(0.0, min(1.0, word.frequency))
                    # Už existující samostatný lexém trochu snižuje potřebu
                    # rozšíření, ale neblokuje běžnou kolexifikaci.
                    lexical_need = 0.85 if target_id in covered else 1.0
                    mechanism = self._mechanism_for(str(source), target_id, declared_mechanism)
                    bridge, scope = self._relation_details(str(source), target_id, bridge, scope)
                    mechanism_pressure, mechanism_reason = self._mechanism_pressure(
                        mechanism, str(source), target_id, word, bridge, scope
                    )
                    if mechanism_pressure <= 0:
                        continue
                    context_pressure, context_reason = self._context_pressure(
                        target_id, word, context
                    )
                    pressure = min(
                        1.0,
                        evidence_strength
                        * exposure
                        * lexical_need
                        * mechanism_pressure
                        * context_pressure,
                    )
                    # Metafora, metonymie a generalizace nejprve rozšíří
                    # význam. Specializace nahrazuje hlavní, širší užití až
                    # po období polysémie. Neoznačený datový posun zůstává
                    # obecný "shift", žádný mechanismus si nevymýšlíme.
                    kind = (
                        "shift"
                        if mechanism == "specialization"
                        or (mechanism is None and edge_type == "shift")
                        else "extension"
                    )
                    candidates.append(
                        SemanticProposal(
                            word_lineage_id=lineage_id,
                            source_concept=str(source).lower(),
                            target_concept=target_id,
                            kind=kind,
                            pressure=round(pressure, 6),
                            evidence_weight=round(evidence_weight, 6),
                            evidence_type=str(edge_type),
                            mechanism=mechanism,
                            mechanism_pressure=round(mechanism_pressure, 6),
                            mechanism_reason=mechanism_reason,
                            context_pressure=context_pressure,
                            context_reason=context_reason,
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
        context: Optional[Mapping[str, object]] = None,
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
            (self.extension_candidates(lexicon, context=context), self.shift_prob),
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
