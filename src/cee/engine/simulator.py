import copy
import heapq
import inspect
import math
import random
import uuid
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from cee.core.models import Inventory, Lexicon, SpeechCommunity, State, VarietyState
from cee.engine.decisions import ChangeDecisionEngine
from cee.engine.events import (
    ContactEvent,
    ForkEvent,
    LexicalEvent,
    MorphologyEvent,
    PhonologyEvent,
    PhonologySlotEvent,
    SemanticChangeEvent,
    SemanticChangeSpreadEvent,
    SemanticEvent,
    SocialDynamicsEvent,
    SocialEvent,
    SoundChangeEvent,
    SoundChangeSpreadEvent,
)
from cee.engine.generator import MacroParams, SoundChangeGenerator
from cee.engine.graph_builder import GraphBuilder
from cee.engine.historical import SOCIAL_PARAMETERS, curve_strength, normalize_effect
from cee.engine.inventory import InventoryView
from cee.engine.lexicon import LexicalEvaluator
from cee.engine.morphology import MorphologyEvaluator
from cee.engine.phonology import FeatureMapper
from cee.engine.phonotactics import PhonotacticProfile
from cee.engine.rng import derive_seed
from cee.engine.rules import Rule
from cee.engine.semantic_history import SemanticChangeRuntime
from cee.engine.social import SocialDynamicsEngine
from cee.engine.topology import EvolutionGraph

# Priorita událostí ve stejném roce: uzel musí nejdřív vzniknout, teprve pak
# na něj smí dopadnout zvuková změna, a až nakonec kontakt s jiným jazykem.
_PRIO_FORK = 0
_PRIO_PHONOLOGY = 1
_PRIO_SEMANTICS = 2
_PRIO_MORPHOLOGY = 3
_PRIO_LEXICON = 4
_PRIO_SOCIAL = 5
_PRIO_CONTACT = 6

# Jemnost záznamu šíření jedné inovace. Není to tempo jazykové změny:
# to nastavuje MacroParams.sound_changes_per_millennium.
SPREAD_PHASE_YEARS = 40


@dataclass(frozen=True)
class WordPressure:
    """Nezávislé tlaky nad jedním lexémem; záměrně bez souhrnného skóre."""

    segment_length: float
    syllable_length: float
    vowel_duration: float
    repetition: float
    phonotactics: float
    homophony: float
    neighborhood_similarity: float


class EvolutionSimulator:
    """
    Řídí globální lockstep simulaci evoluční sítě.

    Všechny události (větvení, zvukové změny, kontakty) se slijí do jedné
    fronty seřazené podle absolutního roku a zpracují chronologicky, takže
    všechny větve sdílejí tutéž časovou osu.
    """

    def __init__(
        self,
        graph_topo: EvolutionGraph,
        mapper: FeatureMapper,
        preset: Dict[str, Any] | None = None,
        seed: int = 42,
        semantic_evaluator=None,
        graph_builder: Optional[GraphBuilder] = None,
        end_year: Optional[int] = None,
        evolve_root: bool = False,
        inventory_validator=None,
        schema_multipliers=None,
        profile_macro=None,
        profile_lexical=None,
    ):
        self.graph = graph_topo
        self.mapper = mapper
        self.graph_builder = graph_builder
        self.preset = preset
        self.semantic_evaluator = semantic_evaluator
        self.seed = seed
        self.evolve_root = evolve_root
        # Časová hloubka simulace. Dokud tu nebyla, generátor měl natvrdo
        # horizont 200 let a dvě pravidla — jazyky ztuhly hned na začátku
        # a pozdější kontakt už zastihl nehybný stav.
        self.end_year = end_year
        self.inventory_validator = inventory_validator
        self.schema_multipliers = schema_multipliers
        self.profile_macro = dict(profile_macro or {})
        self.profile_lexical = dict(profile_lexical or {})
        self.decision_engine = ChangeDecisionEngine()
        # Generátor se staví pro každý uzel zvlášť, aby měl vlastní seed
        # i vlastní makro-parametry (viz _generator_for).
        self._generators: Dict[str, SoundChangeGenerator] = {}
        self._generated_history: Dict[str, List[Rule]] = {}
        self._sound_changes: Dict[str, SoundChangeEvent] = {}
        self._sound_change_adoptions: Dict[str, set[tuple[str, int, str]]] = {}
        self._sound_change_exposure: Dict[str, set[tuple[str, int, str]]] = {}
        self._sound_change_sequence = 0
        self.semantic_history = SemanticChangeRuntime()
        self.social_dynamics = SocialDynamicsEngine()
        # Baseline se ukládá po parametru. Efektivní stav se vždy znovu složí
        # ze všech právě působících událostí, takže konec jedné z nich nemůže
        # zrušit účinek jiné překrývající se události.
        self._historical_baselines: Dict[tuple[str, str], float] = {}
        self._historical_event_changes: Dict[str, Dict[str, Any]] = {}
        # Paměť přenosů je součástí simulovaného historického procesu. Brání
        # tomu, aby stoletý administrativní kontakt pokaždé znovu importoval
        # tutéž část slovní zásoby jako novou vrstvu.
        self._contact_loan_ledger: Dict[tuple[str, str, str, int], set[str]] = {}

    def _generator_for(self, node_id: str) -> Optional[SoundChangeGenerator]:
        """
        Generátor pro konkrétní uzel.

        Seed se odvozuje z globálního seedu a ID uzlu (CEE_master.md 5.5:
        „seed je součástí hashe uzlu"). Jeden sdílený seed znamenal, že tři
        jazyky se stejným biomem dostaly identickou chronologii — což je
        vlastnost losování, ne jazykové skutečnosti.
        """
        if not self.preset:
            return None

        if node_id not in self._generators:
            node_cfg = self.graph.node_configs.get(node_id, {})
            social = node_cfg.get("map", {}).get("social", node_cfg.get("social", {}))
            social_macro: Dict[str, float] = {}
            if isinstance(social, dict) and social:
                # Gramotný/standardizovaný jazyk šíří inovace pomaleji,
                # mobilní populace je naopak rychleji přijímá. Jde o jemnou
                # korekci makroparametrů, ne o přepsání uživatelovy volby.
                standard = float(social.get("standardization", 0.0))
                literacy = float(social.get("literacy", 0.0))
                mobility = float(social.get("mobility", 0.5))
                social_macro = {
                    "conservatism": min(1.0, max(0.0, 0.35 * standard + 0.15 * literacy)),
                    "change_rate": max(0.1, 0.65 + mobility),
                }
            social_macro["isolation"] = float(
                node_cfg.get("map", {}).get("isolation", node_cfg.get("isolation", 0.5))
            )
            social_macro["contact_intensity"] = self._contact_intensity(node_id)
            macro = MacroParams.from_config(
                self.preset.get("macro"),
                self.profile_macro,
                social_macro,
                node_cfg.get("macro"),
                node_cfg.get("map", {}).get("macro"),
            )
            self._generators[node_id] = SoundChangeGenerator(
                self.preset,
                seed=derive_seed(self.seed, node_id),
                macro=macro,
                inventory_validator=self.inventory_validator,
                schema_multipliers=self.schema_multipliers,
            )
        return self._generators[node_id]

    def simulate(self, root_state: State) -> Dict[str, State]:
        """Zpětně kompatibilní varianta pro jeden protojazyk."""
        # Zachováme i diagnostiku staršího jednorodinného rozhraní.
        self._collect_tree(root_state.node_id)
        return self.simulate_many([root_state])

    def simulate_many(self, root_states: List[State]) -> Dict[str, State]:
        """
        Odsimuluje společnou historii více nezávislých protojazyků.

        Kořeny nesdílejí dědičnost, ale sdílejí jednu časovou frontu; kontakt,
        stát a obchod proto mohou působit i mezi rodinami.
        """
        if not root_states:
            raise ValueError("Simulace potřebuje alespoň jeden protojazyk.")
        root_by_id = {state.node_id: state for state in root_states}
        if len(root_by_id) != len(root_states):
            raise ValueError("Protojazyky musí mít jedinečná ID.")
        for root_state in root_states:
            root_config = self.graph.node_configs.get(root_state.node_id, {})
            root_state.map = self._state_map_config(root_config)
            root_state.__post_init__()
            for index, word in enumerate(root_state.lexicon.words):
                word.id = self._deterministic_word_id(
                    "root", root_state.node_id, str(root_state.year), str(index), word.concept_id
                )
                word.lineage_id = word.lineage_id or word.id
                word.parent_word_id = None

        parent_of: Dict[str, str] = {}
        for root_state in root_states:
            for child_id, parent_id in self._collect_tree(root_state.node_id, warn_unreachable=False).items():
                if child_id in parent_of:
                    raise ValueError(f"Uzel '{child_id}' patří do více protojazykových rodin.")
                parent_of[child_id] = parent_id
        global_start = min(state.year for state in root_states)

        if self.graph_builder:
            for root_state in root_states:
                for w in root_state.lexicon.words:
                    self._record_word(w, root_state.year, root_state.node_id)
                self.graph_builder.add_event("simulation_start", root_state.year, root_state.node_id)

        if not parent_of and not self.evolve_root:
            return dict(root_by_id)

        # Rodič musí existovat dřív než dítě, proto řadíme podle hloubky.
        fork_years = self._compute_fork_years(root_by_id, parent_of)

        # Root žije jen jako zdroj pro odštěpení, do výsledku se nevrací.
        states: Dict[str, State] = dict(root_by_id)

        queue: List = []
        counter = 0

        def push(year: int, prio: int, event) -> None:
            nonlocal counter
            heapq.heappush(queue, (year, prio, counter, event))
            counter += 1

        for child_id, parent_id in parent_of.items():
            push(
                fork_years[child_id],
                _PRIO_FORK,
                ForkEvent(fork_years[child_id], parent_id, child_id),
            )

        if self.evolve_root:
            for root_state in root_states:
                self._schedule_phonology_slots(root_state.node_id, root_state.year, push)
                self._schedule_semantics(root_state.node_id, root_state.year, push)
                self._schedule_morphology(root_state.node_id, root_state.year, push)
                self._schedule_lexicon(root_state.node_id, root_state.year, push)
                self._schedule_social(root_state.node_id, root_state.year, push)

        for edge in self.graph.vertical_edges:
            bez_roku = [r.name for r in edge.rules if r.year is None]
            if bez_roku:
                # Bez roku nelze pravidlo zařadit na společnou časovou osu,
                # takže by se tiše neaplikovalo vůbec.
                warnings.warn(
                    f"Pravidla {bez_roku} na hraně "
                    f"'{edge.parent_id}' -> '{edge.child_id}' nemají 'year' "
                    f"a v lockstep simulaci se přeskočí.",
                    stacklevel=2,
                )
            for rule in edge.rules:
                if rule.year is not None:
                    push(rule.year, _PRIO_PHONOLOGY, PhonologyEvent(rule.year, edge.child_id, rule))

        for contact in self.graph.contact_edges:
            # Oboustranný kontakt se rozpadne na dvě události, aby si každý
            # směr nesl vlastní stopu ve výpůjčkách i v historii.
            for source_id, target_id in contact.directions():
                push(
                    contact.year,
                    _PRIO_CONTACT,
                    ContactEvent(
                        contact.year,
                        source_id,
                        target_id,
                        contact.volume,
                        contact.domain,
                        contact.prestige,
                        contact.calque_rate,
                        contact.adapt,
                        contact.layer,
                        contact.transfer_morphology,
                        contact.resolve_homophony,
                        contact.construction_ids,
                    ),
                )

        # Stát není jazyková rodina: pouze zvyšuje kontakt mezi svými jazyky a
        # může vytvářet standardizační tlak prostřednictvím institucí.
        for polity in self.graph.polities.values():
            institution_contact = max(0.0, min(1.0, float(polity.institutions.get("internal_contact", 0.35))))
            standardization = polity.institutions.get("standardization")
            # Kontakt má smysl až od okamžiku, kdy existují oba jazyky.
            # Předtím se dnes správně přeskočil, ale zanechal hlučné varování.
            for index, source_id in enumerate(polity.language_ids):
                for target_id in polity.language_ids[index + 1 :]:
                    first_year = max(
                        global_start,
                        fork_years.get(source_id, global_start),
                        fork_years.get(target_id, global_start),
                    )
                    for year in range(first_year, self.end_year + 1, 100):
                        volume = max(1, round(2 + institution_contact * 6))
                        push(year, _PRIO_CONTACT, ContactEvent(
                            year, source_id, target_id, volume, "polity", 1.0,
                            0.0, True, "folk", False,
                        ))
            if standardization is not None:
                for language_id in polity.language_ids:
                    first_year = max(global_start, fork_years.get(language_id, global_start))
                    for year in range(first_year, self.end_year + 1, 100):
                        push(year, _PRIO_SOCIAL, SocialEvent(
                            year, language_id, {"standardization": float(standardization)}
                        ))

        # Trasa je mapový zdroj kontaktu, ne skrytá přímá hrana. V každé
        # aktivní epoše propojí sousední jazyky uvedené worldbuilderem.
        for route in self.graph.trade_routes:
            stop = min(route.end_year if route.end_year is not None else self.end_year, self.end_year)
            for year in range(max(global_start, route.start_year), stop + 1, 100):
                # Pokud má autor trasu nakreslenou, jazyk musí skutečně ležet
                # u jejího průběhu. Staré seznamové trasy bez geometrie tím
                # nezměníme: zůstávají plně kompatibilní.
                route_languages = [
                    language_id for language_id in route.language_ids
                    if self._route_reaches_language(route, language_id)
                ]
                for source_id, target_id in zip(route_languages, route_languages[1:]):
                    if year < max(fork_years.get(source_id, global_start), fork_years.get(target_id, global_start)):
                        continue
                    volume = max(1, round(max(0.0, min(1.0, route.intensity)) * 10))
                    push(year, _PRIO_CONTACT, ContactEvent(
                        year, source_id, target_id, volume, "trade", 1.0,
                        0.0, True, "folk", False,
                    ))

        for event in self.graph.historical_events:
            polity = self.graph.polities.get(event.target_polity_id or "")
            targets = event.target_language_ids or (polity.language_ids if polity else [])
            changes = dict(event.effects)
            defaults = {
                "migration": {"mobility": 0.8, "contact_intensity": 0.75},
                "war": {"mobility": 0.65, "contact_intensity": 0.25, "isolation": 0.7},
                "collapse": {"standardization": 0.1, "literacy": 0.2, "institutional_pressure": 0.15},
                "urbanization": {
                    "mobility": 0.7, "contact_intensity": 0.7, "receptivity": 0.65,
                    "urbanity": {"value": 0.7, "curve": "persistent"},
                },
                "standardization": {
                    "standardization": 0.8, "literacy": 0.7,
                    "institutional_pressure": 0.8, "register_pressure": 0.7,
                },
                "religious_reform": {
                    "prestige": 0.7, "literacy": 0.65,
                    "institutional_pressure": 0.7, "register_pressure": 0.65,
                },
                "trade_boom": {"mobility": 0.8, "prestige": 0.6, "contact_intensity": 0.85},
            }
            for key, value in defaults.get(event.kind, {}).items():
                changes.setdefault(key, value)
            self._historical_event_changes[event.id] = changes
            for target in targets:
                for effect_year, phase in self._historical_checkpoints(event, changes):
                    if global_start <= effect_year <= self.end_year:
                        push(effect_year, _PRIO_SOCIAL, SocialEvent(
                            effect_year, target, changes,
                            {
                                "id": event.id,
                                "event_kind": event.kind,
                                "duration": max(0, event.duration),
                                "end_year": event.start_year + max(0, event.duration),
                                "start_year": event.start_year,
                                "phase": phase,
                                "historical_effect": True,
                            },
                        ))

        last_year = global_start

        while queue:
            year, _prio, _seq, event = heapq.heappop(queue)
            last_year = max(last_year, year)

            if isinstance(event, ForkEvent):
                parent_state = states.get(event.parent_id)
                if parent_state is None:
                    warnings.warn(
                        f"Uzel '{event.child_id}' se nemohl odštěpit: rodič "
                        f"'{event.parent_id}' v roce {year} neexistuje.",
                        stacklevel=2,
                    )
                    continue

                child_state = self._fork(parent_state, event.child_id, year)
                states[event.child_id] = child_state
                self._generated_history[event.child_id] = list(
                    self._generated_history.get(event.parent_id, [])
                )
                self._inherit_active_sound_changes(
                    event.parent_id, event.child_id, year, push
                )
                self.semantic_history.inherit(
                    event.parent_id, event.child_id, year, push, _PRIO_SEMANTICS
                )
                # Pravidlo se vybere až ve svém budoucím slotu. Pozdější
                # výpůjčky, morfologie i sociální změny tak mohou ovlivnit
                # inventář a tempo, ze kterých generátor skutečně vychází.
                if not self.graph.get_rules_for_edge(event.parent_id, event.child_id):
                    self._schedule_phonology_slots(event.child_id, year, push)
                self._schedule_semantics(event.child_id, year, push)
                self._schedule_morphology(event.child_id, year, push)
                self._schedule_lexicon(event.child_id, year, push)
                self._schedule_social(event.child_id, year, push)

            elif isinstance(event, PhonologySlotEvent):
                branch_state = states.get(event.branch_id)
                if branch_state is None:
                    continue
                self._generate_and_schedule_slot(branch_state, event.year, push)

            elif isinstance(event, SoundChangeEvent):
                branch_state = states.get(event.branch_id)
                if branch_state is None:
                    continue
                # Událost se zapíše do historie už při plánování: pozdější
                # kandidát pak nemůže být okamžitým zvratem inovace, která se
                # právě šíří, i když ještě nezasáhla celý lexikon.
                self._sound_changes[event.change_id] = event
                self._sound_change_adoptions[event.change_id] = set()
                self._sound_change_exposure[event.change_id] = set()
                phases = max(1, math.ceil(event.duration / SPREAD_PHASE_YEARS))
                self._propagate_sound_change(branch_state, event, 1 / phases, event.year)
                self._schedule_sound_change_spread(event, push)

            elif isinstance(event, SoundChangeSpreadEvent):
                branch_state = states.get(event.branch_id)
                change = self._sound_changes.get(event.change_id)
                if branch_state is not None and change is not None:
                    self._propagate_sound_change(branch_state, change, event.progress, event.year)

            elif isinstance(event, PhonologyEvent):
                branch_state = states.get(event.branch_id)
                if branch_state is None:
                    continue
                # Ručně zadaná historie je stejně důležitá jako generovaná:
                # potomci ji zdědí a generátor pak nenabídne okamžitý obrat.
                self._generated_history.setdefault(event.branch_id, []).append(event.rule)
                self._apply_phonology(branch_state, event.rule, event.year)

            elif isinstance(event, SemanticEvent):
                branch_state = states.get(event.branch_id)
                if branch_state is not None and self.semantic_evaluator:
                    # Událost v lockstepu: větev se nejdřív dostane do
                    # zadaného roku, potom se její významy změní. Dítě, které
                    # vznikne později, tak dědí právě tehdejší lexikon.
                    branch_state.year = event.year
                    before = self._word_versions(branch_state)
                    semantic_rng = random.Random(
                        derive_seed(self.seed, "semantics", event.branch_id, str(event.year))
                    )
                    if hasattr(self.semantic_evaluator, "propose_changes"):
                        semantic_context = self._semantic_context(branch_state)
                        register_changes = (
                            self.semantic_evaluator.evolve_registers(
                                branch_state.lexicon, semantic_context
                            )
                            if hasattr(self.semantic_evaluator, "evolve_registers")
                            else []
                        )
                        register_hit_count = self._record_changed_words(
                            branch_state,
                            before,
                            event.year,
                            "register_change",
                            "semantic register transition",
                        )
                        if self.graph_builder:
                            for transition in register_changes:
                                self.graph_builder.add_event(
                                    "register_transition",
                                    event.year,
                                    event.branch_id,
                                    **transition,
                                )
                            if register_hit_count:
                                self.graph_builder.add_event(
                                    "semantic_registers",
                                    event.year,
                                    event.branch_id,
                                    hit_count=register_hit_count,
                                )
                        self.semantic_history.schedule_proposals(
                            branch_state,
                            event.year,
                            self.semantic_evaluator,
                            semantic_rng,
                            push,
                            _PRIO_SEMANTICS,
                            self._horizon_for(branch_state.year, event.branch_id),
                            context=semantic_context,
                            approval_mode=str(
                                self.graph.node_configs.get(event.branch_id, {})
                                .get("semantic", {}).get("approval_mode", "auto")
                            ),
                            approved_changes=set(
                                self.graph.node_configs.get(event.branch_id, {})
                                .get("semantic", {}).get("approved_changes", [])
                            ),
                            innovation_group=self.graph.node_configs.get(event.branch_id, {})
                            .get("semantic", {}).get("innovation_group"),
                            graph_builder=self.graph_builder,
                        )
                    else:
                        parameters = inspect.signature(self.semantic_evaluator.evaluate).parameters
                        if "random_gen" in parameters:
                            self.semantic_evaluator.evaluate(
                                branch_state.lexicon, random_gen=semantic_rng
                            )
                        else:  # zpětná kompatibilita malých uživatelských evaluátorů
                            self.semantic_evaluator.evaluate(branch_state.lexicon)
                        hit_count = self._record_changed_words(
                            branch_state,
                            before,
                            event.year,
                            "semantic_shift",
                            "semantic change",
                        )
                        if self.graph_builder:
                            self.graph_builder.add_event(
                                "semantics", event.year, event.branch_id, hit_count=hit_count
                            )

            elif isinstance(event, SemanticChangeEvent):
                branch_state = states.get(event.branch_id)
                if branch_state is None:
                    continue
                self.semantic_history.start(
                    branch_state,
                    event,
                    push,
                    _PRIO_SEMANTICS,
                    self._record_changed_words,
                    self._word_versions,
                    self.graph_builder,
                )

            elif isinstance(event, SemanticChangeSpreadEvent):
                branch_state = states.get(event.branch_id)
                if branch_state is not None:
                    self.semantic_history.spread(
                        branch_state,
                        event,
                        self._record_changed_words,
                        self._word_versions,
                        self.graph_builder,
                    )

            elif isinstance(event, MorphologyEvent):
                branch_state = states.get(event.branch_id)
                if branch_state is not None:
                    branch_state.year = event.year
                    before = self._word_versions(branch_state)
                    self._apply_morphology(branch_state)
                    hit_count = self._record_changed_words(
                        branch_state, before, event.year, "morphological_change", "morphology"
                    )
                    if self.graph_builder:
                        self.graph_builder.add_event(
                            "morphology", event.year, event.branch_id, hit_count=hit_count
                        )

            elif isinstance(event, LexicalEvent):
                branch_state = states.get(event.branch_id)
                if branch_state is not None:
                    branch_state.year = event.year
                    before = self._word_versions(branch_state)
                    rng = random.Random(
                        derive_seed(self.seed, "lexicon", event.branch_id, str(event.year))
                    )
                    lexical = {
                        **self.profile_lexical,
                        **self.graph.node_configs.get(event.branch_id, {}).get("lexical", {}),
                    }
                    divergence = self._divergence_profile(event.branch_id)
                    evaluator = LexicalEvaluator(
                        replacement_rate=float(lexical.get("replacement_rate", 0.015)) * divergence["lexical_rate"],
                        loss_rate=float(lexical.get("loss_rate", 0.01)) * divergence["lexical_rate"],
                        homophony_resolution_rate=float(
                            lexical.get("homophony_resolution_rate", 1.0)
                        ),
                        homophony_policy=str(
                            lexical.get(
                                "homophony_policy",
                                "audit" if lexical.get("resolve_homophones", False) else "off",
                            )
                        ),
                        homophony_strategies=lexical.get("homophony_strategies", {}),
                        innovation_rate=float(lexical.get("innovation_rate", 0.0)) * divergence["lexical_rate"],
                        innovation_sources=lexical.get("innovation_sources", {}),
                    )
                    evaluator.evaluate(
                        branch_state,
                        event.year,
                        rng,
                        taboo_concepts=lexical.get("taboo_concepts", []),
                        render=self.mapper.render_word,
                    )
                    hit_count = self._record_changed_words(
                        branch_state, before, event.year, "lexical_change", "lexical change"
                    )
                    if self.graph_builder:
                        self.graph_builder.add_event(
                            "lexicon", event.year, event.branch_id, hit_count=hit_count
                        )
                        for decision in evaluator.last_homophony_decisions:
                            self.graph_builder.add_event(
                                "homophony_pressure",
                                event.year,
                                event.branch_id,
                                pressure=decision.pressure,
                                context_overlap=decision.context_overlap,
                                evidence_level=decision.evidence_level,
                                action=decision.action,
                                reason=decision.reason,
                                winner_id=decision.winner_id,
                                loser_id=decision.loser_id,
                            )
                            if decision.action == "needs_legitimate_innovation":
                                self.graph_builder.add_event(
                                    "homophony_pending",
                                    event.year,
                                    event.branch_id,
                                    decision_id=(
                                        f"{event.branch_id}:{event.year}:"
                                        f"{decision.winner_id}:{decision.loser_id}"
                                    ),
                                    winner_id=decision.winner_id,
                                    loser_id=decision.loser_id,
                                    pressure=decision.pressure,
                                    reason=decision.reason,
                                    status="pending",
                                )
                        for competition in evaluator.last_competitions:
                            self.graph_builder.add_event(
                                "lexical_competition", event.year, event.branch_id, **competition
                            )

            elif isinstance(event, SocialEvent):
                branch_state = states.get(event.branch_id)
                if branch_state is not None:
                    branch_state.year = event.year
                    history = event.history or {}
                    is_historical = bool(history.get("historical_effect"))
                    effect_audit = []
                    if is_historical:
                        effect_audit = self._apply_historical_effects(branch_state, event.year)
                    else:
                        for key, value in event.changes.items():
                            if key in SOCIAL_PARAMETERS:
                                normalized = max(0.0, min(1.0, float(value)))
                                # Instituce a explicitní sociální historie jsou
                                # baseline, ne další historická vrstva. Pokud
                                # přijdou během události, její pozdější konec je
                                # proto nesmí vrátit na zastaralou hodnotu.
                                baseline_key = (event.branch_id, key)
                                if baseline_key in self._historical_baselines:
                                    self._historical_baselines[baseline_key] = normalized
                                branch_state.social[key] = normalized

                    # Materiální následky (komunita, síť, autorovo přejmenování)
                    # vznikají přesně jednou při nástupu, nikdy při každém vzorku
                    # křivky ani samovolně z typu události.
                    materialized_changes = (
                        event.changes if not is_historical or history.get("phase") == "start" else {}
                    )
                    name_change = materialized_changes.get("name_change")
                    if isinstance(name_change, dict):
                        config = self.graph.node_configs.setdefault(event.branch_id, {})
                        endonym = str(name_change.get("endonym", config.get("endonym", config.get("label", event.branch_id))))
                        exonym = str(name_change.get("exonym", config.get("exonym", endonym)))
                        config.update({"endonym": endonym, "exonym": exonym, "label": endonym})
                        if self.graph_builder:
                            self.graph_builder.add_event(
                                "language_name_change", event.year, event.branch_id,
                                endonym=endonym, exonym=exonym,
                                reason=str(name_change.get("reason", "historical_event")),
                            )
                    migration = materialized_changes.get("migration")
                    if isinstance(migration, dict):
                        source = branch_state.communities.get(str(migration.get("from", "")))
                        target = branch_state.communities.get(str(migration.get("to", "")))
                        target_id = str(migration.get("to", "")).strip()
                        create = migration.get("create")
                        if source is not None and target is None and target_id and isinstance(create, dict):
                            target = SpeechCommunity(
                                id=target_id,
                                share=0.0,
                                prestige=max(0.0, min(1.0, float(create.get("prestige", source.prestige)))),
                                mobility=max(0.0, min(1.0, float(create.get("mobility", source.mobility)))),
                                domains={str(value) for value in create.get("domains", source.domains)},
                                kind=str(create.get("kind", "regional")),
                                variety_id=str(create.get("variety_id", f"variety:{target_id}")),
                                urbanity=max(0.0, min(1.0, float(create.get("urbanity", source.urbanity)))),
                                generation=str(create.get("generation", source.generation)),
                            )
                            branch_state.communities[target_id] = target
                            branch_state.varieties[target.variety_id] = VarietyState(target.variety_id, target_id)
                            link_strength = max(0.0, min(1.0, float(create.get("link_strength", 0.65))))
                            source.links[target_id] = max(source.links.get(target_id, 0.0), link_strength)
                            target.links[source.id] = max(target.links.get(source.id, 0.0), link_strength)
                            bilingualism = max(0.0, min(1.0, float(create.get("bilingualism", 0.5))))
                            source.bilingualism[target_id] = max(source.bilingualism.get(target_id, 0.0), bilingualism)
                            target.bilingualism[source.id] = max(target.bilingualism.get(source.id, 0.0), bilingualism)
                            if self.graph_builder:
                                self.graph_builder.add_event(
                                    "migration_community_created", event.year, event.branch_id,
                                    source_community=source.id, target_community=target_id,
                                    contact_strength=link_strength, bilingualism=bilingualism,
                                )
                        if source is not None and target is not None:
                            share = max(0.0, min(source.share, float(migration.get("share", 0.0))))
                            source.share -= share
                            target.share += share
                            total = sum(item.share for item in branch_state.communities.values())
                            if total:
                                for item in branch_state.communities.values():
                                    item.share /= total
                            if self.graph_builder:
                                self.graph_builder.add_event(
                                    "migration",
                                    event.year,
                                    event.branch_id,
                                    source_community=source.id,
                                    target_community=target.id,
                                    share=round(share, 6),
                                )
                    variety_action = materialized_changes.get("variety_action")
                    if isinstance(variety_action, dict):
                        variety_id = str(variety_action.get("variety_id", ""))
                        action = str(variety_action.get("action", ""))
                        variety = branch_state.varieties.get(variety_id)
                        if variety is None:
                            variety = branch_state.varieties.get(f"variety:{variety_id}")
                        if variety is not None and action == "assimilate":
                            variety.divergence = 0.0
                            for community in branch_state.communities.values():
                                if community.variety_id == variety.id:
                                    community.status = "assimilated"
                        elif variety is not None and action == "stabilize":
                            variety.divergence = max(variety.divergence, 0.12)
                            for community in branch_state.communities.values():
                                if community.variety_id == variety.id:
                                    community.status = "supported"
                        if self.graph_builder and action in {"assimilate", "stabilize"}:
                            self.graph_builder.add_event(
                                "variety_decision", event.year, event.branch_id,
                                variety_id=variety_id, action=action,
                            )
                    if self.graph_builder:
                        if event.history:
                            historical_payload = dict(event.history)
                            if effect_audit:
                                historical_payload["effects"] = effect_audit
                            self.graph_builder.add_event(
                                "historical_event",
                                event.year,
                                event.branch_id,
                                **historical_payload,
                            )
                        self.graph_builder.add_event(
                            "social_change",
                            event.year,
                            event.branch_id,
                            changes=dict(branch_state.social),
                        )

            elif isinstance(event, SocialDynamicsEvent):
                branch_state = states.get(event.branch_id)
                if branch_state is not None:
                    branch_state.year = event.year
                    for change in self.social_dynamics.advance(branch_state, event.year):
                        if self.graph_builder:
                            kind = change.pop("kind")
                            change.pop("year", None)
                            self.graph_builder.add_event(kind, event.year, event.branch_id, **change)

            elif isinstance(event, ContactEvent):
                source_state = states.get(event.source_id)
                target_state = states.get(event.target_id)
                if source_state is None or target_state is None:
                    warnings.warn(
                        f"Kontakt v roce {event.year} mezi '{event.source_id}' a "
                        f"'{event.target_id}' se přeskakuje: jeden z uzlů v té době neexistuje.",
                        stacklevel=2,
                    )
                    continue
                self._apply_contact(
                    source_state,
                    target_state,
                    event.year,
                    max(0, round(event.volume * self._divergence_profile(event.target_id)["contact_permeability"])),
                    event.domain,
                    event.prestige,
                    event.calque_rate,
                    event.adapt,
                    event.layer,
                    event.transfer_morphology,
                    event.resolve_homophony,
                    event.construction_ids,
                    push=push,
                )

        result = {
            node_id: state
            for node_id, state in states.items()
            if node_id in parent_of or (self.evolve_root and node_id in root_by_id)
        }
        final_year = max(last_year, self.end_year or last_year)

        for state in result.values():
            state.year = final_year

        return result

    # --- pomocné metody ---------------------------------------------------

    @staticmethod
    def _historical_checkpoints(event, changes: Dict[str, Any] | None = None) -> List[tuple[int, str]]:
        """Vzorky křivky: nástup, pravidelný průběh a přesný konec.

        Simulátor jinak pracuje převážně ve stoletých krocích; střed pulzu je
        přidán zvlášť, aby krátká událost neměla neviditelný vrchol.
        """
        start = event.start_year
        duration = max(0, int(event.duration))
        if duration == 0:
            return [(start, "start")]
        end = start + duration
        points = {start: "start", end: "end"}
        curves = (changes or {}).get("curves", {}) if isinstance(changes, dict) else {}
        shaped = any(
            (isinstance(value, dict) and value.get("curve") in {"linear", "pulse", "persistent"})
            or (isinstance(curves, dict) and curves.get(key) in {"linear", "pulse", "persistent"})
            for key, value in (changes or {}).items()
            if key != "curves"
        )
        if shaped:
            points[start + duration // 2] = "peak"
        for year in range(start + 100, end, 100):
            points.setdefault(year, "active")
        return sorted(points.items())

    def _event_targets(self, event) -> List[str]:
        polity = self.graph.polities.get(event.target_polity_id or "")
        return event.target_language_ids or (polity.language_ids if polity else [])

    def _event_effects(self, event) -> List[Dict[str, Any]]:
        changes = self._historical_event_changes.get(event.id, event.effects)
        curves = changes.get("curves", {}) if isinstance(changes, dict) else {}
        result = []
        for parameter, raw in changes.items():
            if parameter == "curves":
                continue
            if isinstance(curves, dict) and parameter in curves and not isinstance(raw, dict):
                raw = {"value": raw, "curve": curves[parameter]}
            effect = normalize_effect(parameter, raw, event.duration)
            if effect is not None:
                result.append(effect)
        return result

    def _apply_historical_effects(self, state: State, year: int) -> List[Dict[str, Any]]:
        """Složí efektivní sociální stav a vrátí audit jednotlivých efektů."""
        active: Dict[str, List[tuple[str, Dict[str, Any], float]]] = {}
        for historical_event in self.graph.historical_events:
            if state.node_id not in self._event_targets(historical_event):
                continue
            for effect in self._event_effects(historical_event):
                strength = curve_strength(
                    effect["curve"], historical_event.start_year, effect["duration"], year
                )
                if strength > 0:
                    active.setdefault(effect["parameter"], []).append(
                        (historical_event.id, effect, strength)
                    )

        audit: List[Dict[str, Any]] = []
        for parameter, entries in sorted(active.items()):
            baseline_key = (state.node_id, parameter)
            if baseline_key not in self._historical_baselines:
                self._historical_baselines[baseline_key] = float(state.social.get(parameter, 0.0))
            value = self._historical_baselines[baseline_key]
            for event_id, effect, strength in sorted(entries, key=lambda item: item[0]):
                before = value
                if effect["mode"] == "add":
                    value += effect["value"] * strength
                else:
                    value += (effect["value"] - value) * strength
                value = max(0.0, min(1.0, value))
                audit.append({
                    "source_event_id": event_id,
                    "parameter": parameter,
                    "curve": effect["curve"],
                    "strength": round(strength, 6),
                    "before": round(before, 6),
                    "after": round(value, 6),
                    "year": year,
                })
            state.social[parameter] = value

        # Když dočasný efekt skončí, explicitně obnovíme baseline. Persistent
        # účinky zůstávají v ``active`` a proto se zde nikdy nevracejí zpět.
        for (node_id, parameter), baseline in list(self._historical_baselines.items()):
            if node_id == state.node_id and parameter not in active:
                state.social[parameter] = baseline
        return audit

    def _collect_tree(self, root_id: str, *, warn_unreachable: bool = True) -> Dict[str, str]:
        """
        Vrátí mapu {potomek: rodič} pro všechny uzly dosažitelné z rootu,
        v pořadí od nejmělčích. Na hrany mimo strom upozorní.
        """
        parent_of: Dict[str, str] = {}
        frontier = [root_id]
        seen = {root_id}

        while frontier:
            next_frontier = []
            for node_id in frontier:
                for child_id in self.graph.get_children(node_id):
                    if child_id in seen:
                        warnings.warn(
                            f"Uzel '{child_id}' má víc než jednoho rodiče nebo tvoří cyklus; "
                            f"druhá hrana z '{node_id}' se ignoruje.",
                            stacklevel=2,
                        )
                        continue
                    seen.add(child_id)
                    parent_of[child_id] = node_id
                    next_frontier.append(child_id)
            frontier = next_frontier

        unreachable = {e.child_id for e in self.graph.vertical_edges} - seen
        if unreachable and warn_unreachable:
            warnings.warn(
                f"Uzly {sorted(unreachable)} nejsou z '{root_id}' dosažitelné "
                f"a nebudou simulovány.",
                stacklevel=2,
            )

        return parent_of

    def _compute_fork_years(self, roots: Dict[str, State], parent_of: Dict[str, str]) -> Dict[str, int]:
        """Uzel se odštěpí v roce svého prvního pravidla, jinak spolu s rodičem."""
        fork_years: Dict[str, int] = {node_id: state.year for node_id, state in roots.items()}
        default_year = min(fork_years.values())

        for child_id, parent_id in parent_of.items():
            rules = self.graph.get_rules_for_edge(parent_id, child_id)
            years = [r.year for r in rules if r.year is not None]
            parent_year = fork_years.get(parent_id, default_year)
            # Dynamické UI hrany nemají vlastní pravidla, ale uzel zná svůj
            # rok vzniku. Bez něj by se jazyk odštěpil hned v roce 0 a
            # kontakty na časové ose nedávaly smysl.
            configured_year = self.graph.node_configs.get(child_id, {}).get("year", parent_year)
            fork_years[child_id] = min(years) if years else int(configured_year)

            # Dítě nikdy nesmí vzniknout dřív než rodič.
            fork_years[child_id] = max(fork_years[child_id], parent_year)

        return fork_years

    def _fork(self, parent_state: State, child_id: str, year: int) -> State:
        """Odštěpí nový uzel jako nezávislou kopii rodiče v daném roce."""
        node_cfg = self.graph.node_configs.get(child_id, {})
        new_lexicon = Lexicon(words=[])

        for index, parent_word in enumerate(parent_state.lexicon.words):
            new_word = copy.deepcopy(parent_word)
            new_word.parent_word_id = parent_word.id
            new_word.id = self._deterministic_word_id(
                "fork", parent_word.id, child_id, str(year), str(index)
            )
            new_word.origin_type = "inherited"
            new_word.origin_rule = None
            new_word.origin_year = year
            new_lexicon.words.append(new_word)

            if self.graph_builder:
                self._record_word(new_word, year, child_id)
                self.graph_builder.add_origin_edge(new_word.id, parent_word.id, "inherited")

        if self.graph_builder:
            self.graph_builder.add_event("split", year, child_id, parent_id=parent_state.node_id)
            self.graph_builder.add_event(
                "branch_divergence_profile", year, child_id,
                parent_id=parent_state.node_id,
                **self._divergence_profile(child_id),
            )

        child_map = self._state_map_config(node_cfg)
        child_state = State(
            node_id=child_id,
            year=year,
            inventory=copy.deepcopy(parent_state.inventory),
            lexicon=new_lexicon,
            parent_id=parent_state.node_id,
            map=child_map,
            population=copy.deepcopy(parent_state.population),
            communities=copy.deepcopy(parent_state.communities),
            varieties=copy.deepcopy(parent_state.varieties),
        )
        return child_state

    @staticmethod
    def _state_map_config(node_config: Dict[str, Any]) -> Dict[str, Any]:
        """Sloučí mapová a sociální data do stavu bez změny veřejného YAML."""
        base = node_config.get("map", node_config)
        result = dict(base) if isinstance(base, dict) else {}
        for key in ("population", "communities"):
            if key in node_config:
                result[key] = node_config[key]
        return result

    def _horizon_for(self, start_year: int, child_id: str) -> int:
        """
        Dokdy se pro danou hranu generují pravidla.

        Sahá až k zadané hloubce simulace, nejméně však k poslední události,
        která se uzlu týká — jinak by jazyk ztuhl dřív, než na něj někdo naváže.
        """
        candidates = [self.end_year] if self.end_year else []

        candidates += [
            c.year for c in self.graph.contact_edges if child_id in (c.source_id, c.target_id)
        ]
        candidates += [
            r.year
            for e in self.graph.vertical_edges
            if e.parent_id == child_id
            for r in e.rules
            if r.year is not None
        ]

        horizon = max([c for c in candidates if c is not None], default=start_year + 200)
        return max(horizon, start_year + 1)

    def _contact_intensity(self, node_id: str) -> float:
        """Převede hrany kontaktu na jemný modifikátor inovačního tempa."""
        exposure = sum(
            max(0, edge.volume) * max(0.0, edge.prestige)
            for edge in self.graph.contact_edges
            if node_id in (edge.source_id, edge.target_id)
        )
        # Saturace brání tomu, aby jedna hustá hranice znamenala nekonečný
        # příval inovací; nula zůstává legitimním izolovaným jazykem.
        return exposure / (exposure + 5.0) if exposure else 0.0

    def _schedule_phonology_slots(self, node_id: str, start_year: int, push) -> None:
        """Rozloží pouze příležitosti ke změně, ne hotová pravidla.

        Kandidát se vytvoří až při zpracování slotu z tehdejšího živého
        inventáře. Pevná hustota slotů dovolí, aby sociální historie
        průběžně měnila pravděpodobnost i počet inovací.
        """
        generator = self._generator_for(node_id)
        if generator is None:
            return
        horizon = self._horizon_for(start_year, node_id)
        span = max(1, horizon - start_year)
        expected = span * generator.macro.innovations_per_millennium / 1_000
        count_rng = random.Random(
            derive_seed(self.seed, "phonology-count", node_id, str(start_year), str(horizon))
        )
        slot_count = int(expected)
        if count_rng.random() < expected - slot_count:
            slot_count += 1
        if slot_count <= 0:
            return
        for slot in range(slot_count):
            window_start = start_year + span * slot / slot_count
            window_end = start_year + span * (slot + 1) / slot_count
            rng = random.Random(
                derive_seed(self.seed, "phonology-slot", node_id, str(slot), str(start_year))
            )
            center = (window_start + window_end) / 2
            wobble = (window_end - window_start) * generator.macro.timing_jitter / 2
            year = int(round(rng.uniform(center - wobble, center + wobble)))
            year = min(horizon, max(start_year + 1, year))
            push(year, _PRIO_PHONOLOGY, PhonologySlotEvent(year, node_id))

    def _current_macro(self, state: State) -> MacroParams:
        node_cfg = self.graph.node_configs.get(state.node_id, {})
        divergence = self._divergence_profile(state.node_id)
        standard = state.social.get("standardization", 0.0)
        literacy = state.social.get("literacy", 0.0)
        mobility = state.social.get("mobility", 0.5)
        social_macro = {
            "conservatism": min(1.0, max(0.0, 0.35 * standard + 0.15 * literacy)),
            "change_rate": max(0.1, 0.65 + mobility),
            "isolation": float(node_cfg.get("map", {}).get("isolation", node_cfg.get("isolation", 0.5))),
            "contact_intensity": self._contact_intensity(state.node_id),
        }
        macro = MacroParams.from_config(
            self.preset.get("macro") if self.preset else None,
            self.profile_macro,
            social_macro,
            node_cfg.get("macro"),
            node_cfg.get("map", {}).get("macro"),
        )
        # Po odštěpení nemají větve jen jiný seed, ale vlastní historické
        # tempo. Násobitel je záměrně až zde: sociální historie dál upravuje
        # společný základ a profil ji pouze individualizuje.
        macro.change_rate *= divergence["phonological_rate"]
        return macro

    def _divergence_profile(self, node_id: str) -> dict[str, float]:
        """Normalizovaný profil nezávislého vývoje jedné větve.

        Hodnota 1 zachovává dosavadní chování. Profil nezná cílovou vzdálenost;
        určuje jen tempo a propustnost procesů, takže běh není účelově tažený
        k jedné moderní jazykové dvojici.
        """
        raw = self.graph.node_configs.get(node_id, {}).get("divergence", {})
        raw = raw if isinstance(raw, dict) else {}
        values = {}
        for key in ("phonological_rate", "lexical_rate", "morphological_rate", "contact_permeability"):
            try:
                values[key] = max(0.0, float(raw.get(key, 1.0)))
            except (TypeError, ValueError):
                values[key] = 1.0
        return values

    def _generate_and_schedule_slot(self, state: State, year: int, push) -> None:
        generator = self._generator_for(state.node_id)
        if generator is None:
            return
        generator.macro = self._current_macro(state)
        activity = generator.macro.activity
        whole = int(activity)
        fraction = activity - whole
        slot_rng = random.Random(
            derive_seed(self.seed, "phonology-activity", state.node_id, str(year))
        )
        attempts = whole + (1 if slot_rng.random() < fraction else 0)
        if attempts == 0:
            return

        history = self._generated_history.setdefault(state.node_id, [])
        for _ in range(attempts):
            inventory = InventoryView.from_lexicon(state.lexicon, self.mapper)
            state.inventory = inventory.to_inventory()
            decisions = {}

            def pressure(rule: Rule) -> float:
                # Při generování se vyhodnotí kandidát nad skutečným
                # lexikonem, bez hlubokého kopírování všech forem. Uchováme
                # auditovatelný výsledek pro vítěznou inovaci.
                decision = self.decision_engine.assess_sound_change(state, rule, self.mapper)
                decisions[id(rule)] = decision
                return decision.pressure

            previous = history[-1] if history else None
            candidate = generator.generate_pressure_driven(
                state,
                year,
                inventory,
                previous=previous,
                history=history,
                score=pressure,
            )
            if candidate is None:
                continue
            decision = decisions.get(id(candidate))
            if decision is None:
                continue
            # Hned rezervujeme pravidlo v historii, aby další kandidát
            # v témže slotu nemohl vygenerovat jeho zvrat.
            history.append(candidate)
            self._sound_change_sequence += 1
            change_id = f"{state.node_id}:{year}:{self._sound_change_sequence}"
            duration = min(
                decision.duration(generator.macro.change_spread_years),
                max(0, self._horizon_for(state.year, state.node_id) - year),
            )
            push(
                year,
                _PRIO_PHONOLOGY,
                SoundChangeEvent(
                    year=year,
                    branch_id=state.node_id,
                    rule=candidate,
                    change_id=change_id,
                    duration=duration,
                    pressure=decision.pressure,
                    applicable_words=decision.applicable_words,
                    frequency_coverage=decision.frequency_coverage,
                    contrast_retention=decision.contrast_retention,
                    functional_load=decision.functional_load,
                    paradigm_retention=decision.paradigm_retention,
                    innovation_group=decision.innovation_group,
                    innovation_class=decision.innovation_class,
                ),
            )

    def _inherit_active_sound_changes(self, parent_id: str, child_id: str, year: int, push) -> None:
        """Potomek pokračuje v inovacích, které při odštěpení ještě dobíhaly."""
        inherited = [
            change
            for change in self._sound_changes.values()
            if change.branch_id == parent_id and change.year < year < change.year + change.duration
        ]
        for change in inherited:
            child_change = copy.copy(change)
            child_change.branch_id = child_id
            child_change.change_id = f"{change.change_id}:fork:{child_id}"
            self._sound_changes[child_change.change_id] = child_change
            self._sound_change_adoptions[child_change.change_id] = set(
                self._sound_change_adoptions[change.change_id]
            )
            self._sound_change_exposure[child_change.change_id] = set(
                self._sound_change_exposure.get(change.change_id, set())
            )
            self._schedule_sound_change_spread(child_change, push, after_year=year)

    def _schedule_sound_change_spread(
        self, change: SoundChangeEvent, push, *, after_year: Optional[int] = None
    ) -> None:
        """Rozepíše zbývající kumulativní fáze šíření na společnou časovou osu."""
        if change.duration <= 0:
            return
        phases = max(1, math.ceil(change.duration / SPREAD_PHASE_YEARS))
        for phase in range(2, phases + 1):
            progress = phase / phases
            year = change.year + int(round(change.duration * progress))
            if after_year is not None and year <= after_year:
                continue
            push(
                year,
                _PRIO_PHONOLOGY,
                SoundChangeSpreadEvent(year, change.branch_id, change.change_id, progress),
            )

    @staticmethod
    def _sound_change_word_key(word) -> tuple[str, int, str]:
        return word.concept_id, word.origin_year, word.source_id or ""

    @staticmethod
    def _network_adoption_bias(state: State, innovation_group: str | None, word) -> float:
        """Převede explicitní síť komunit na malý práh šíření inovace.

        Není to simulace lidí: vazba pouze zrychlí či zpomalí přijetí konkrétní
        již vzniklé změny v jiné komunitě. Bez sítě zůstává staré chování.
        """
        target_group = word.grammatical_features.get("social.group", "").strip()
        if not innovation_group or not target_group or target_group == innovation_group:
            return 0.0
        source = state.communities.get(innovation_group)
        target = state.communities.get(target_group)
        if source is None or target is None:
            return 0.0
        strength = max(
            float(source.links.get(target_group, 0.0)),
            float(target.links.get(innovation_group, 0.0)),
            float(source.bilingualism.get(target_group, 0.0)),
            float(target.bilingualism.get(innovation_group, 0.0)),
        )
        # Přímá, silná vazba znamená dřívější přijetí. U izolovaných komunit
        # změna stále může projít, jen v pozdější fázi.
        return round(0.12 - 0.24 * max(0.0, min(1.0, strength)), 6)

    def _propagate_sound_change(
        self, state: State, change: SoundChangeEvent, progress: float, year: int
    ) -> None:
        """Aplikuje dosud neadoptovanou, deterministicky vybranou část lexikonu."""
        state.year = year
        adopted = self._sound_change_adoptions[change.change_id]
        exposed = self._sound_change_exposure[change.change_id]
        threshold = min(1.0, max(0.0, progress * change.intensity))
        selected = []
        phonotactic_profile = PhonotacticProfile.learn(state.lexicon.words)
        pressure_context = [
            (other.id, other.concept_id, tuple(tuple(sorted(s.features.items())) for s in other.segments))
            for other in state.lexicon.words
            if other.active
        ]
        ranked_candidates = []
        for word in state.lexicon.words:
            if not word.active:
                continue
            key = self._sound_change_word_key(word)
            if key in adopted or not change.rule.can_apply_to_word(word):
                continue
            if not self._preserves_content_word_shape(word, change.rule):
                # Lexikální difuze dovoluje výjimky. Obsahový kořen, který by
                # opakovanou erozí klesl do miniaturního prostoru CV/V, však
                # tuto inovaci nepřejme bez kompenzačního mechanismu.
                adopted.add(key)
                continue
            pressure_before, pressure_after = self._word_pressure_transition(
                state, word, change.rule, phonotactic_profile, pressure_context
            )
            if not self._permits_pressure_transition(
                word, pressure_before, pressure_after
            ):
                # Změna není odmítnuta proto, že by byla „neestetická“, ale
                # protože by už přetížený lexém dál prodloužila či rytmicky
                # zdvojila. Takové formy jsou historicky mnohem spíš cílem
                # redukce než dalšího rozšiřování.
                adopted.add(key)
                continue
            ranked_candidates.append((word, key, pressure_before, pressure_after))

        # Pořadí je vysvětlitelné a závislé na konkrétním pravidle. Náhoda
        # v prahu níže zůstává: vysoká priorita zvyšuje šanci, není rozkazem.
        ranked_candidates.sort(
            key=lambda item: self._change_priority(item[2], item[3]), reverse=True
        )
        for word, key, pressure_before, pressure_after in ranked_candidates:
            temperature = self._phonology_temperature(state)
            if self._has_phonology_temperature(state) and key not in exposed:
                # Teplota řídí, kdo vůbec vstoupí do procesu. Při 1 vstoupí
                # každý vhodný lexém; při 0 nikdo. Mezi tím priorita tlaků
                # pouze probabilisticky mění pořadí expozice.
                priority = self._change_priority(pressure_before, pressure_after)
                exposure_probability = (
                    1.0 if temperature >= 1.0 else temperature * (0.60 + 0.40 * priority)
                )
                exposure_sample = random.Random(
                    derive_seed(self.seed, "sound-change-exposure", change.change_id, *map(str, key))
                ).random()
                exposed.add(key)
                if exposure_sample > exposure_probability:
                    adopted.add(key)
                    continue
                # Expozice spustí proces, ne hotovou změnu. Uchycení je
                # nezávislý seedovaný pokus, takže ani teplota 1 neznamená
                # automatickou aplikaci všude.
                catch_probability = min(0.90, 0.25 + 0.55 * change.pressure + 0.20 * priority)
                catch_sample = random.Random(
                    derive_seed(self.seed, "sound-change-catch", change.change_id, *map(str, key))
                ).random()
                if catch_sample > catch_probability:
                    adopted.add(key)
                    continue
            sample = random.Random(
                derive_seed(self.seed, "sound-change-adoption", change.change_id, *map(str, key))
            ).random()
            adoption_threshold = self.decision_engine.sound_change_adoption_threshold(
                word,
                change.rule,
                sample,
                innovation_group=change.innovation_group,
                innovation_class=change.innovation_class,
                network_bias=self._network_adoption_bias(state, change.innovation_group, word),
            )
            priority = self._change_priority(pressure_before, pressure_after)
            adoption_threshold = min(
                1.0,
                max(0.0, adoption_threshold + self._complexity_adoption_bias(
                    pressure_before, pressure_after
                ) - 0.20 * priority),
            )
            if adoption_threshold <= threshold:
                selected.append(word)
                adopted.add(key)
        self._apply_phonology(
            state,
            change.rule,
            year,
            words=selected,
            event_metadata={
                "change_id": change.change_id,
                "start_year": change.year,
                "end_year": change.year + change.duration,
                "duration": change.duration,
                "progress": round(progress, 4),
                "intensity": change.intensity,
                "pressure": change.pressure,
                "applicable_words": change.applicable_words,
                "frequency_coverage": change.frequency_coverage,
                "contrast_retention": change.contrast_retention,
                "functional_load": change.functional_load,
                "paradigm_retention": change.paradigm_retention,
                "innovation_group": change.innovation_group,
                "innovation_class": change.innovation_class,
            },
        )

    def _phonology_temperature(self, state: State) -> float:
        """Nastavitelná intenzita expozice fonologické inovaci (0 až 1)."""
        config = self.graph.node_configs.get(state.node_id, {})
        phonology = config.get("phonology", {})
        macro = config.get("macro", {})
        raw = (
            phonology.get("temperature", macro.get("change_temperature", 1.0))
            if isinstance(phonology, dict) and isinstance(macro, dict)
            else 1.0
        )
        try:
            return max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            return 1.0

    def _has_phonology_temperature(self, state: State) -> bool:
        config = self.graph.node_configs.get(state.node_id, {})
        phonology = config.get("phonology", {})
        macro = config.get("macro", {})
        return (
            isinstance(phonology, dict) and "temperature" in phonology
        ) or (
            isinstance(macro, dict) and "change_temperature" in macro
        )

    @staticmethod
    def _preserves_content_word_shape(word, rule: Rule) -> bool:
        """Chrání lexikální prostor, neexistující zákaz krátkých slov.

        Funkční a původně krátké lexémy smějí zůstat krátké. Ochrana se týká
        jen obsahového slova, které má alespoň tři segmenty a nová pravidelná
        změna by ho stáhla pod tuto hranici.
        """
        if word.is_grammatical or word.grammatical_features.get("lexical.class") == "function":
            return True
        if len(word.segments) < 3:
            return True
        candidate = copy.deepcopy(word)
        rule.apply_to_word(candidate)
        return len(candidate.segments) >= 3

    def word_pressures(self, state: State, word) -> WordPressure:
        """Vrátí vysvětlitelný vektor tlaků nad aktuálním stavem lexému."""
        context = [
            (other.id, other.concept_id, tuple(tuple(sorted(s.features.items())) for s in other.segments))
            for other in state.lexicon.words
            if other.active
        ]
        return self._word_pressure(state, word, PhonotacticProfile.learn(state.lexicon.words), context)

    def _word_pressure(
        self, state: State, word, phonotactics: PhonotacticProfile, context: list[tuple]
    ) -> WordPressure:
        segments = [tuple(sorted(segment.features.items())) for segment in word.segments]
        segment_count = len(segments)
        nuclei = word.syllable_nuclei()
        adjacent_doubles = sum(segments[index] == segments[index - 1] for index in range(1, segment_count))
        bigrams = [tuple(segments[index:index + 2]) for index in range(segment_count - 1)]
        repeated_bigrams = max(0, len(bigrams) - len(set(bigrams)))
        competitors = [
            signature for other_id, concept_id, signature in context
            if other_id != word.id and concept_id != word.concept_id
        ]
        exact_collisions = sum(signature == tuple(segments) for signature in competitors)
        similarities = [
            self._form_similarity(segments, signature) for signature in competitors
        ]
        return WordPressure(
            segment_length=round(min(1.0, max(0, segment_count - 5) / 5), 6),
            syllable_length=round(min(1.0, max(0, len(nuclei) - 2) / 3), 6),
            vowel_duration=round(min(1.0, len(word.long_nuclei) / max(1, len(nuclei))), 6),
            repetition=round(min(1.0, 0.45 * adjacent_doubles + 0.30 * repeated_bigrams), 6),
            phonotactics=round(min(1.0, sum(phonotactics.score(word).values()) / 3), 6),
            homophony=1.0 if exact_collisions else 0.0,
            neighborhood_similarity=round(max(similarities, default=0.0), 6),
        )

    @staticmethod
    def _form_similarity(left: list[tuple], right: list[tuple]) -> float:
        """Normalizovaná podobnost segmentových podpisů, bez IPA heuristik."""
        row = list(range(len(right) + 1))
        for left_index, left_value in enumerate(left, 1):
            old, row[0] = row[0], left_index
            for right_index, right_value in enumerate(right, 1):
                old, row[right_index] = row[right_index], min(
                    row[right_index] + 1,
                    row[right_index - 1] + 1,
                    old + (left_value != right_value),
                )
        distance = row[-1]
        return 1.0 - distance / max(1, len(left), len(right))

    def _word_pressure_transition(
        self, state: State, word, rule: Rule, phonotactics: PhonotacticProfile, context: list[tuple]
    ) -> tuple[WordPressure, WordPressure]:
        before = self._word_pressure(state, word, phonotactics, context)
        candidate = copy.deepcopy(word)
        rule.apply_to_word(candidate)
        return before, self._word_pressure(state, candidate, phonotactics, context)

    @staticmethod
    def _permits_pressure_transition(word, before: WordPressure, after: WordPressure) -> bool:
        """Rozhoduje po osách tlaku; žádný součet nezakrývá důvod odmítnutí."""
        if word.is_grammatical or word.grammatical_features.get("lexical.class") == "function":
            return True
        if after.homophony > before.homophony:
            return False
        if after.phonotactics > max(0.50, before.phonotactics):
            return False
        if after.segment_length > before.segment_length and after.segment_length >= 0.60:
            return False
        if after.syllable_length > before.syllable_length and after.syllable_length >= 0.67:
            return False
        if after.repetition > before.repetition and after.repetition >= 0.45:
            return False
        return True

    @staticmethod
    def _complexity_adoption_bias(before: WordPressure, after: WordPressure) -> float:
        """Jemný bias sčítá konkrétní účinky, nikoli skryté celkové skóre."""
        changes = (
            (before.segment_length, after.segment_length, 0.10),
            (before.syllable_length, after.syllable_length, 0.08),
            (before.vowel_duration, after.vowel_duration, 0.05),
            (before.repetition, after.repetition, 0.12),
            (before.phonotactics, after.phonotactics, 0.10),
            (before.neighborhood_similarity, after.neighborhood_similarity, 0.06),
        )
        return max(-0.22, min(0.22, sum((after_value - before_value) * weight for before_value, after_value, weight in changes)))

    @staticmethod
    def _change_priority(before: WordPressure, after: WordPressure) -> float:
        """Priorita lexému pro jednu změnu, nikoli globální známka slova.

        Každá osa zůstává odděleně viditelná. Priorita zvýhodní formu, jíž
        dané pravidlo skutečně ulevuje, a mírně zvýhodní i neutrální změnu v
        již přetížené formě. Růst kteréhokoli tlaku prioritu odečítá.
        """
        axes = (
            (before.segment_length, after.segment_length, 0.26),
            (before.syllable_length, after.syllable_length, 0.18),
            (before.vowel_duration, after.vowel_duration, 0.10),
            (before.repetition, after.repetition, 0.20),
            (before.phonotactics, after.phonotactics, 0.16),
            (before.homophony, after.homophony, 0.30),
            (before.neighborhood_similarity, after.neighborhood_similarity, 0.08),
        )
        relief = sum(max(0.0, before_value - after_value) * weight for before_value, after_value, weight in axes)
        growth = sum(max(0.0, after_value - before_value) * weight for before_value, after_value, weight in axes)
        existing = sum(before_value * weight for before_value, _after_value, weight in axes)
        return round(max(0.0, min(1.0, relief + 0.20 * existing - growth)), 6)

    def rank_words_for_change(self, state: State, rule: Rule) -> list[tuple]:
        """Vrátí aktivní lexémy od nejvhodnějšího k nejméně vhodnému přijetí.

        Výstup nese oba vektory tlaků i pravděpodobnostní prioritu, aby UI či
        audit mohly navrhnout změnu s důvodem místo jednoho neprůhledného čísla.
        """
        profile = PhonotacticProfile.learn(state.lexicon.words)
        context = [
            (other.id, other.concept_id, tuple(tuple(sorted(s.features.items())) for s in other.segments))
            for other in state.lexicon.words
            if other.active
        ]
        ranked = []
        for word in state.lexicon.words:
            if not word.active or not rule.can_apply_to_word(word):
                continue
            before, after = self._word_pressure_transition(state, word, rule, profile, context)
            ranked.append((word, before, after, self._change_priority(before, after)))
        return sorted(ranked, key=lambda item: item[3], reverse=True)

    def _route_reaches_language(self, route, language_id: str) -> bool:
        """Zkontroluje, že zastávka leží poblíž kreslené trasy.

        Geometrie je záměrně jen jemné omezení mapového editoru, nikoli
        fyzický model. Bez alespoň dvou waypointů nebo bez pozice jazyka se
        vracíme ke starému explicitnímu seznamu zastávek.
        """
        points = route.waypoints
        position = self.graph.node_configs.get(language_id, {}).get("position", {})
        if len(points) < 2 or not {"x", "y"}.issubset(position):
            return True
        px, py = float(position["x"]), float(position["y"])
        # 180 mapových jednotek odpovídá zhruba průměru jednoho uzlu a jeho
        # štítku; autor tak nemusí kreslit trasu přes střed každého uzlu.
        max_distance_sq = 180.0 ** 2
        for start, end in zip(points, points[1:]):
            ax, ay = float(start["x"]), float(start["y"])
            bx, by = float(end["x"]), float(end["y"])
            dx, dy = bx - ax, by - ay
            length_sq = dx * dx + dy * dy
            ratio = 0.0 if length_sq == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
            cx, cy = ax + ratio * dx, ay + ratio * dy
            if (px - cx) ** 2 + (py - cy) ** 2 <= max_distance_sq:
                return True
        return False

    def _apply_phonology(
        self,
        state: State,
        rule: Rule,
        year: int,
        *,
        words=None,
        event_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        changed = 0
        deleted_segments = 0
        phonotactics = PhonotacticProfile.learn(state.lexicon.words)
        repaired_forms = 0
        for word in words if words is not None else state.lexicon.words:
            if not word.active:
                continue
            before = self._word_signature(word)
            before_segments = len(word.segments)
            old_id = word.id
            rule.apply_to_word(word)
            # Oprava je součást téže historické události; genealogie
            # nikdy neuloží mezitvar, který ve výsledném lexikonu neexistuje.
            # Formu nesrovnáváme s globální hranicí tří souhlásek, ale s
            # fonotaktikou, kterou jazyk doložil před touto inovací.
            if phonotactics.repair(word):
                repaired_forms += 1
            deleted_segments += max(0, before_segments - len(word.segments))
            if self._word_signature(word) == before:
                continue
            self._version_word(word, old_id, state.node_id, year, "mutated", rule.name)
            changed += 1

        state.inventory = Inventory(segments=self._inventory_of(state.lexicon))
        if self.graph_builder:
            payload = {
                "rule": rule.name,
                "schema_id": rule.schema_id or "manual",
                "hit_count": changed,
                "deleted_segments": deleted_segments,
                "phonotactic_repairs": repaired_forms,
            }
            if event_metadata:
                payload.update(event_metadata)
            self.graph_builder.add_event("sound_change", year, state.node_id, **payload)

    def _schedule_semantics(self, node_id: str, start_year: int, push) -> None:
        """Vloží sémantiku do stejné absolutní chronologie jako kontakt."""
        if not self.semantic_evaluator:
            return
        horizon = self._horizon_for(start_year, node_id)
        semantic = self.graph.node_configs.get(node_id, {}).get("semantic", {})
        profile = str(semantic.get("profile", "balanced"))
        interval = {"conservative": 200, "balanced": 100, "dynamic": 50}.get(profile, 100)
        # Sto let je jednotka pravděpodobností SemanticEvaluatoru. První
        # posun přichází až po vzniku jazyka, nikdy při samotném odštěpení.
        for year in range(start_year + interval, horizon + 1, interval):
            push(year, _PRIO_SEMANTICS, SemanticEvent(year, node_id))

    def _semantic_context(self, state: State) -> Dict[str, Any]:
        """Sestaví dohledatelný kontext významového užití pro jeden uzel."""
        node_config = self.graph.node_configs.get(state.node_id, {})
        map_config = state.map or {}
        configured_social = map_config.get("social", map_config.get("society", {}))
        return {
            "map": map_config,
            "social": state.social or configured_social or {},
            "semantic": node_config.get("semantic", (state.map or {}).get("semantic", {})),
            "lexical": node_config.get("lexical", (state.map or {}).get("lexical", {})),
        }

    def _schedule_morphology(self, node_id: str, start_year: int, push) -> None:
        """Složeniny, derivace a analogie patří do stejné časové osy."""
        config = self.graph.node_configs.get(node_id, {})
        morphology = config.get("morphology", {})
        has_creation = bool(
            config.get("compounds")
            or morphology.get("compounds")
            or morphology.get("derivations")
            or morphology.get("paradigms")
            or morphology.get("grammaticalize")
            or morphology.get("reanalyze")
            or morphology.get("enabled")
        )
        analogy_rate = float(morphology.get("analogy_rate", 0.0))
        if has_creation:
            push(start_year + 1, _PRIO_MORPHOLOGY, MorphologyEvent(start_year + 1, node_id))
        rate = self._divergence_profile(node_id)["morphological_rate"]
        if morphology.get("enabled") and rate > 0:
            horizon = self._horizon_for(start_year, node_id)
            interval = max(25, round(100 / rate))
            for year in range(start_year + interval, horizon + 1, interval):
                push(year, _PRIO_MORPHOLOGY, MorphologyEvent(year, node_id))
        if analogy_rate > 0 and rate > 0:
            horizon = self._horizon_for(start_year, node_id)
            interval = max(50, round(200 / rate))
            for year in range(start_year + interval, horizon + 1, interval):
                push(year, _PRIO_MORPHOLOGY, MorphologyEvent(year, node_id))

    def _schedule_lexicon(self, node_id: str, start_year: int, push) -> None:
        config = self.graph.node_configs.get(node_id, {})
        lexical = config.get("lexical", {})
        if not lexical.get("enabled", False):
            return
        horizon = self._horizon_for(start_year, node_id)
        for year in range(start_year + 100, horizon + 1, 100):
            push(year, _PRIO_LEXICON, LexicalEvent(year, node_id))

    def _schedule_social(self, node_id: str, start_year: int, push) -> None:
        """Naprogramované společenské zlomy (urbanizace, standardizace…)."""
        history = self.graph.node_configs.get(node_id, {}).get("social_history", [])
        for item in history:
            try:
                year = int(item["year"])
            except (KeyError, TypeError, ValueError):
                warnings.warn(f"Neplatná sociální událost pro '{node_id}': {item!r}", stacklevel=2)
                continue
            if year < start_year:
                continue
            changes = item.get(
                "changes", {key: value for key, value in item.items() if key != "year"}
            )
            if isinstance(changes, dict):
                push(year, _PRIO_SOCIAL, SocialEvent(year, node_id, changes))
        config = self.graph.node_configs.get(node_id, {})
        map_config = config.get("map", config)
        population = map_config.get("population", config.get("population", {}))
        communities = map_config.get("communities", config.get("communities", []))
        has_social_topology = bool(communities) or (
            isinstance(population, dict) and int(population.get("centers", 1)) > 1
        )
        if not has_social_topology:
            return
        horizon = self._horizon_for(start_year, node_id)
        for year in range(start_year + 100, horizon + 1, 100):
            push(year, _PRIO_SOCIAL, SocialDynamicsEvent(year, node_id))

    def _word_signature(self, word) -> tuple:
        """Vše, co tvoří historicky rozlišitelný stav lexému."""
        return (
            tuple(tuple(sorted(segment.features.items())) for segment in word.segments),
            word.concept_id,
            tuple(sorted(word.polysemy)),
            word.stress_index,
            tuple(sorted(word.long_nuclei)),
            tuple(sorted(word.tones.items())),
            tuple(sorted(word.morpheme_boundaries)),
            word.paradigm,
            tuple(sorted(word.grammatical_features.items())),
            word.is_grammatical,
            word.active,
            round(word.frequency, 8),
        )

    def _word_versions(self, state: State) -> Dict[str, tuple]:
        return {word.id: self._word_signature(word) for word in state.lexicon.words}

    def _deterministic_word_id(self, *parts: str) -> str:
        material = "\x1f".join((str(self.seed), *parts))
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"cee:{material}"))

    def _record_word(self, word, year: int, node_id: str) -> None:
        if not self.graph_builder:
            return
        self.graph_builder.add_word(
            word.id,
            word.concept_id,
            self.mapper.render_word(word),
            year,
            node_id,
            sorted(word.polysemy),
            lineage_id=word.lineage_id,
            ipa_prosodic=self.mapper.render_word_prosodic(word),
            stress_index=word.stress_index,
            long_nuclei=sorted(word.long_nuclei),
            tones=dict(word.tones),
            morpheme_boundaries=sorted(word.morpheme_boundaries),
            active=word.active,
            frequency=word.frequency,
            paradigm=word.paradigm,
            grammatical_features=dict(word.grammatical_features),
            is_grammatical=word.is_grammatical,
            origin_type=word.origin_type,
        )

    def _version_word(
        self,
        word,
        old_id: str,
        node_id: str,
        year: int,
        origin_type: str,
        rule: str,
    ) -> None:
        word.lineage_id = word.lineage_id or old_id
        word.parent_word_id = old_id
        word.id = self._deterministic_word_id(
            "version", old_id, node_id, str(year), origin_type, rule
        )
        word.origin_type = origin_type
        word.origin_rule = rule
        word.origin_year = year
        self._record_word(word, year, node_id)
        if self.graph_builder:
            self.graph_builder.add_origin_edge(word.id, old_id, origin_type, rule)

    def _record_changed_words(
        self,
        state: State,
        before: Dict[str, tuple],
        year: int,
        origin_type: str,
        rule: str,
    ) -> int:
        """Verzuje změněné objekty a zapíše nově vytvořené lexémy."""
        new_index = 0
        changed = 0
        for word in state.lexicon.words:
            if word.id not in before:
                word.id = self._deterministic_word_id(
                    "new",
                    state.node_id,
                    str(year),
                    origin_type,
                    word.parent_word_id or "",
                    word.concept_id,
                    str(new_index),
                )
                new_index += 1
                word.lineage_id = word.lineage_id or word.id
                changed += 1
                self._record_word(word, year, state.node_id)
                if self.graph_builder and word.parent_word_id:
                    self.graph_builder.add_origin_edge(
                        word.id,
                        word.parent_word_id,
                        word.origin_type or origin_type,
                        word.origin_rule or rule,
                    )
                continue
            if self._word_signature(word) != before[word.id]:
                self._version_word(word, word.id, state.node_id, year, origin_type, rule)
                changed += 1
        return changed

    def _inventory_of(self, lexicon: Lexicon) -> set:
        return set(InventoryView.from_lexicon(lexicon, self.mapper))

    def _apply_morphology(self, state: State) -> None:
        """
        Vytvoří složeniny předepsané v topologii daného uzlu, např.:

            nodes:
              - id: north
                compounds:
                  - head: "město"
                    modifier: "zlatý"
                    id: "zlaté_město"
        """
        config = self.graph.node_configs.get(state.node_id, {})
        morphology = config.get("morphology", {})
        specs = [*config.get("compounds", []), *morphology.get("compounds", [])]

        morph = MorphologyEvaluator()
        for spec in specs:
            head, modifier, new_id = spec.get("head"), spec.get("modifier"), spec.get("id")
            if not (head and modifier and new_id):
                warnings.warn(
                    f"Složenina {spec!r} v uzlu '{state.node_id}' vyžaduje "
                    f"'head', 'modifier' i 'id'; přeskakuji.",
                    stacklevel=2,
                )
                continue
            if morph.compound(state, head, modifier, new_id) is None:
                warnings.warn(
                    f"Složeninu '{new_id}' v uzlu '{state.node_id}' nelze vytvořit: "
                    f"'{head}' nebo '{modifier}' není v lexikonu.",
                    stacklevel=2,
                )

        # Kurátorované sémantické recepty jsou alternativou k ručně zapsané
        # trojici head/modifier/id. Vytváří se jen chybějící koncept s oběma
        # živými zdroji; existující kořeny se nikdy nepřepisují složeninou.
        if morphology.get("recipe_compounds", False):
            from cee.semantics.swadesh import apply_suggestion, automatic_suggestions

            for suggestion in automatic_suggestions(state):
                word = apply_suggestion(state, suggestion)
                if word is not None and self.graph_builder:
                    self.graph_builder.add_event(
                        "semantic_compound",
                        state.year,
                        state.node_id,
                        concept_id=word.concept_id,
                        head=suggestion.head,
                        modifier=suggestion.modifier,
                        recipe=suggestion.label,
                    )

        for spec in morphology.get("derivations", []):
            root, affix, new_id = spec.get("root"), spec.get("affix"), spec.get("id")
            if not (root and affix and new_id):
                warnings.warn(
                    f"Derivace {spec!r} vyžaduje 'root', 'affix' i 'id'; přeskakuji.", stacklevel=2
                )
                continue
            morph.derive(state, root, affix, new_id, prefix=spec.get("prefix"))

        for word_id in morphology.get("grammaticalize", []):
            morph.grammaticalize(state, str(word_id))

        for spec in morphology.get("paradigms", []):
            paradigm_id = str(spec.get("id", "default"))
            stem_id = spec.get("stem")
            if stem_id:
                morph.inflect(state, str(stem_id), paradigm_id, spec.get("forms", []))

        if morphology.get("reanalyze", False):
            morph.reanalyze_boundaries(state, morphology.get("reanalyze_paradigm"))

        if float(morphology.get("analogy_rate", 0.0)) > 0:
            morph.level_analogies(state, threshold=float(morphology.get("analogy_threshold", 0.75)))

        if morphology.get("enabled"):
            morph.promote_productive_affixes(
                state, minimum_uses=int(morphology.get("productivity_minimum_uses", 2))
            )
            if morphology.get("affix_erosion", True):
                morph.erode_productive_affixes(
                    state, threshold=float(morphology.get("erosion_frequency_threshold", 0.75))
                )

    def _apply_contact(
        self,
        source: State,
        target: State,
        year: int,
        volume: int,
        domain: str = "neighborhood",
        prestige: float = 1.0,
        calque_rate: float = 0.0,
        adapt: bool = False,
        layer: str = "folk",
        transfer_morphology: bool = False,
        resolve_homophony: bool = False,
        construction_ids: Optional[List[str]] = None,
        *,
        push=None,
    ):
        """
        Provede výpůjčku `volume` slov ze `source` do `target`.
        Slova získají origin_year = year a source_id = source.node_id.
        """
        if not source.lexicon.words:
            return

        construction_ids = construction_ids or []

        # Prestiž a sociální asymetrie mění množství výpůjček, nikoli jen
        # jejich vykreslený popisek. Mobilní cílová společnost přejímá víc,
        # silně standardizovaná naopak méně.
        source_prestige = source.social.get("prestige", 0.5)
        target_mobility = target.social.get("mobility", 0.5)
        target_standard = target.social.get("standardization", 0.0)
        multiplier = (
            max(0.2, prestige)
            * (0.75 + target_mobility)
            * (1.25 - target_standard)
            * (0.75 + source_prestige)
        )
        requested = min(max(1, round(volume * multiplier)), len(source.lexicon.words))
        # Politická sounáležitost vytváří opakované příležitosti ke kontaktu,
        # ne automatický přísun nových slov v každém století. Rozpočet je
        # společný pro čtyřsetletou vrstvu a pamatuje si již přenesené
        # koncepty. Ostatní kanály jsou také chráněny před duplicitou, ale
        # mají štědřejší rozpočet.
        period = year // 400
        ledger_key = (source.node_id, target.node_id, domain, period)
        borrowed_concepts = self._contact_loan_ledger.setdefault(ledger_key, set())
        channel_cap = {
            "polity": max(1, min(3, round(volume * 0.35))),
            "trade": max(1, min(4, round(volume * 0.50))),
            "war": max(1, min(3, round(volume * 0.40))),
            "religion": max(1, min(3, round(volume * 0.40))),
        }.get(domain, max(1, min(4, round(volume * 0.55))))
        remaining_budget = max(0, channel_cap - len(borrowed_concepts))
        num_borrow = min(requested, remaining_budget)
        rng = random.Random(
            derive_seed(self.seed, "contact", source.node_id, target.node_id, str(year), domain)
        )
        candidates = [
            word for word in source.lexicon.words
            if word.active and word.concept_id not in borrowed_concepts
        ]
        domain_candidates = [word for word in candidates if self._matches_contact_domain(word, domain)]
        # Doména je preference, ne absolutní zákaz: malý či neanotovaný
        # lexikon stále dovolí kontakt, ale anotovaný korpus dostane přednost.
        if domain_candidates:
            candidates = domain_candidates
        if not transfer_morphology:
            candidates = [word for word in candidates if not word.is_grammatical]
        if not candidates:
            return
        # Obchod zvýhodní frekventní lexémy, válka naopak méně stabilní
        # okrajové položky; bez domény je kontakt neutrální.
        exponent = 1.8 if domain in {"trade", "religion"} else 0.65 if domain == "war" else 1.0
        weights = [max(0.02, word.frequency) ** exponent for word in candidates]
        words_to_borrow = []
        while candidates and len(words_to_borrow) < num_borrow:
            selected = rng.choices(candidates, weights=weights, k=1)[0]
            selected_index = candidates.index(selected)
            words_to_borrow.append(selected)
            candidates.pop(selected_index)
            weights.pop(selected_index)
        target_view = InventoryView.from_lexicon(target.lexicon, self.mapper)

        borrowed_count = 0
        calque_count = 0
        homophony_replacements = 0
        for borrow_index, w in enumerate(words_to_borrow):
            existing_words = target.lexicon.get_words(w.concept_id)

            # Kalk přenáší významovou asociaci bez importu cizího tvaru.
            if existing_words and rng.random() < max(0.0, min(1.0, calque_rate)):
                existing_words[0].polysemy.update(w.polysemy)
                calque_count += 1
                continue

            new_word = copy.deepcopy(w)
            new_word.parent_word_id = w.id
            new_word.id = self._deterministic_word_id(
                "borrow",
                w.id,
                target.node_id,
                str(year),
                str(borrow_index),
            )
            new_word.origin_type = "borrowed"
            new_word.origin_rule = None
            new_word.origin_year = year
            new_word.source_id = source.node_id
            new_word.frequency = max(0.08, w.frequency * 0.65)
            if adapt:
                self._adapt_loan(new_word, target_view)
                PhonotacticProfile.learn(target.lexicon.words).repair(new_word)

            layer_register = {"folk": "ordinary", "elite": "formal", "written": "formal", "ritual": "ritual"}
            new_word.grammatical_features["contact.layer"] = layer
            new_word.grammatical_features["lexical.register"] = layer_register.get(layer, "neutral")

            target.lexicon.words.append(new_word)
            borrowed_count += 1
            borrowed_concepts.add(w.concept_id)

            if self.graph_builder:
                self._record_word(new_word, year, target.node_id)
                self.graph_builder.add_origin_edge(new_word.id, w.id, "borrowed")

        # Kontakt je legitimní zdroj nové formy jen při explicitním rozhodnutí
        # autora a jen pro kolizi, která má skutečnou funkční zátěž. Nevybíráme
        # náhodný cizí tvar: dárce musí vyjadřovat právě koncept poraženého
        # lexému a po nativizaci se nesmí shodovat s vítězem.
        if resolve_homophony:
            groups: dict[str, list] = {}
            for word in target.lexicon.words:
                if word.active:
                    groups.setdefault(self.mapper.render_word(word), []).append(word)
            decision_engine = ChangeDecisionEngine()
            decisions = [
                decision
                for forms in groups.values()
                if len(forms) > 1
                for decision in decision_engine.assess_homophones(forms)
            ]
            by_id = {word.id: word for word in target.lexicon.words}
            for decision in decisions:
                if decision.action != "needs_legitimate_innovation":
                    continue
                loser = by_id.get(decision.loser_id)
                winner = by_id.get(decision.winner_id)
                if loser is None or winner is None:
                    continue
                donors = [
                    word for word in source.lexicon.get_words(loser.concept_id)
                    if word.active and word.segments != loser.segments
                ]
                if not donors:
                    continue
                donor = max(donors, key=lambda word: word.frequency)
                replacement = copy.deepcopy(donor)
                if adapt:
                    self._adapt_loan(replacement, target_view)
                    PhonotacticProfile.learn(target.lexicon.words).repair(replacement)
                if replacement.segments == winner.segments or replacement.segments == loser.segments:
                    continue
                old_id = loser.id
                loser.segments = replacement.segments
                loser.stress_index = replacement.stress_index
                loser.long_nuclei = replacement.long_nuclei
                loser.tones = replacement.tones
                loser.morpheme_boundaries = replacement.morpheme_boundaries
                loser.source_id = source.node_id
                loser.grammatical_features["homophony.resolution"] = "contact_loan"
                loser.grammatical_features["contact.layer"] = layer
                self._version_word(
                    loser, old_id, target.node_id, year,
                    "borrowed_homophony_replacement", "contact",
                )
                if self.graph_builder:
                    self.graph_builder.add_origin_edge(loser.id, donor.id, "borrowed_homophony_replacement")
                    self.graph_builder.add_event(
                        "homophony_contact_resolution", year, target.node_id,
                        winner_id=winner.id, loser_id=loser.id, donor_id=donor.id,
                        pressure=decision.pressure, source_id=source.node_id,
                    )
                homophony_replacements += 1
            if homophony_replacements:
                target.inventory = Inventory(segments=self._inventory_of(target.lexicon))

        transferred_constructions = self._transfer_contact_constructions(
            source, target, year, construction_ids, adapt, target_view
        )

        semantic_variants = 0
        if push is not None and (calque_rate > 0 or domain == "trade"):
            semantic_variants = self.semantic_history.transfer_contact(
                source,
                target,
                year,
                max(calque_rate, min(1.0, volume / 10.0) if domain == "trade" else 0.0),
                push,
                _PRIO_SEMANTICS,
                self.graph_builder,
            )

        if self.graph_builder:
            self.graph_builder.add_event(
                "contact",
                year,
                target.node_id,
                source_id=source.node_id,
                domain=domain,
                requested_volume=volume,
                requested_borrows=requested,
                channel_cap=channel_cap,
                remaining_budget=remaining_budget,
                borrowed_count=borrowed_count,
                calque_count=calque_count,
                prestige=prestige,
                adapted=adapt,
                layer=layer,
                morphology_transferred=transfer_morphology,
                homophony_replacements=homophony_replacements,
                transferred_constructions=transferred_constructions,
                semantic_variants=semantic_variants,
            )

    def _transfer_contact_constructions(
        self,
        source: State,
        target: State,
        year: int,
        construction_ids: List[str],
        adapt: bool,
        target_view: InventoryView,
    ) -> list[str]:
        """Přenese výslovně vybrané produktivní konstrukce, ne celý systém.

        Konstrukce je malý přenositelný recept v ``morphology.constructions``:
        ``compound`` používá ``head_concept`` a ``modifier_concept``;
        ``derivation`` používá ``root_concept`` a ``affix_concept``. Příslušný
        afix se před aplikací vypůjčí a každý vzniklý tvar nese dohledatelný
        původ. Neznámý nebo neproveditelný recept se pouze neaplikuje.
        """
        if not construction_ids:
            return []
        source_morphology = self.graph.node_configs.get(source.node_id, {}).get("morphology", {})
        specs = source_morphology.get("constructions", [])
        selected = [spec for spec in specs if isinstance(spec, dict) and str(spec.get("id")) in construction_ids]
        if not selected:
            return []

        target_config = self.graph.node_configs.setdefault(target.node_id, {})
        target_morphology = dict(target_config.get("morphology", {}))
        carried = list(target_morphology.get("borrowed_constructions", []))
        morph = MorphologyEvaluator()
        transferred: list[str] = []
        for spec in selected:
            construction_id = str(spec["id"])
            if any(item.get("id") == construction_id and item.get("source_id") == source.node_id for item in carried if isinstance(item, dict)):
                continue
            recipe = {**copy.deepcopy(spec), "source_id": source.node_id, "borrowed_year": year}
            carried.append(recipe)
            kind = str(spec.get("kind", ""))
            created = None
            if kind == "compound":
                head = target.lexicon.get_word(str(spec.get("head_concept", "")))
                modifier = target.lexicon.get_word(str(spec.get("modifier_concept", "")))
                result = str(spec.get("result_concept", ""))
                if head and modifier and result:
                    created = morph.compound(target, head.concept_id, modifier.concept_id, result)
            elif kind == "derivation":
                root = target.lexicon.get_word(str(spec.get("root_concept", "")))
                affix_concept = str(spec.get("affix_concept", ""))
                affix = target.lexicon.get_word(affix_concept)
                donor_affix = source.lexicon.get_word(affix_concept)
                if affix is None and donor_affix is not None:
                    affix = copy.deepcopy(donor_affix)
                    affix.id = self._deterministic_word_id("construction-affix", donor_affix.id, target.node_id, str(year))
                    affix.parent_word_id = donor_affix.id
                    affix.source_id = source.node_id
                    affix.origin_type = "borrowed_morpheme"
                    affix.origin_year = year
                    affix.is_grammatical = True
                    if adapt:
                        self._adapt_loan(affix, target_view)
                    target.lexicon.words.append(affix)
                    if self.graph_builder:
                        self._record_word(affix, year, target.node_id)
                        self.graph_builder.add_origin_edge(affix.id, donor_affix.id, "borrowed_morpheme")
                result = str(spec.get("result_concept", ""))
                if root and affix and result:
                    created = morph.derive(target, root.concept_id, affix.concept_id, result, prefix=spec.get("prefix"))
            if created is not None:
                created.grammatical_features["morphology.borrowed_construction"] = construction_id
                self._record_word(created, year, target.node_id)
            transferred.append(construction_id)

        target_morphology["borrowed_constructions"] = carried
        target_config["morphology"] = target_morphology
        if transferred and self.graph_builder:
            self.graph_builder.add_event(
                "construction_transfer", year, target.node_id,
                source_id=source.node_id, construction_ids=transferred,
            )
        return transferred

    @staticmethod
    def _matches_contact_domain(word, domain: str) -> bool:
        domain = domain.lower()
        expected = {
            "trade": {"commerce", "money", "possession", "quantity", "exchange"},
            "religion": {"religion", "ritual", "belief", "spiritual"},
            "war": {"war", "weapon", "society", "politics", "government"},
        }.get(domain)
        if not expected:
            return False
        values = word.grammatical_features.get("semantic.domains", word.grammatical_features.get("lexical.domains", ""))
        actual = {value.strip().lower() for value in str(values).split(",") if value.strip()}
        return bool(actual & expected)

    def _adapt_loan(self, word, target_view: InventoryView) -> None:
        """Nahradí cizí foném nejbližším dostupným fonémem cílového jazyka."""
        if not target_view:
            return
        candidates = [(ipa, target_view.features_of(ipa)) for ipa in target_view]
        for segment in word.segments:
            ipa = self.mapper.segment_to_ipa(segment)
            if ipa in target_view:
                continue
            same_class = [
                pair
                for pair in candidates
                if pair[1] and pair[1].get("syl") == segment.features.get("syl")
            ]
            options = same_class or candidates
            best_ipa, best_features = max(
                options,
                key=lambda pair: sum(
                    value == (pair[1].get(feature) if pair[1] else None)
                    for feature, value in segment.features.items()
                ),
            )
            del best_ipa
            segment.features = dict(best_features or {})
        word.ensure_stress()
