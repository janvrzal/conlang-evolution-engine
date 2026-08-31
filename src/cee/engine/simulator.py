import copy
import heapq
import inspect
import math
import random
import uuid
import warnings
from typing import Any, Dict, List, Optional

from cee.core.models import Inventory, Lexicon, State
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
    SocialEvent,
    SoundChangeEvent,
    SoundChangeSpreadEvent,
)
from cee.engine.generator import MacroParams, SoundChangeGenerator
from cee.engine.graph_builder import GraphBuilder
from cee.engine.inventory import InventoryView
from cee.engine.lexicon import LexicalEvaluator
from cee.engine.morphology import MorphologyEvaluator
from cee.engine.phonology import FeatureMapper
from cee.engine.phonotactics import PhonotacticProfile
from cee.engine.rng import derive_seed
from cee.engine.rules import Rule
from cee.engine.semantic_history import SemanticChangeRuntime
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
        self._sound_change_sequence = 0
        self.semantic_history = SemanticChangeRuntime()

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
        """
        Odsimuluje celou síť od root_state a vrátí finální stavy (uzly).

        Prochází strom do libovolné hloubky: každý uzel se odštěpí od svého
        rodiče v roce prvního pravidla na příslušné hraně.
        """
        root_config = self.graph.node_configs.get(root_state.node_id, {})
        root_state.map = root_config.get("map", root_config)
        root_state.__post_init__()
        for index, word in enumerate(root_state.lexicon.words):
            word.id = self._deterministic_word_id(
                "root", root_state.node_id, str(root_state.year), str(index), word.concept_id
            )
            word.lineage_id = word.lineage_id or word.id
            word.parent_word_id = None
        parent_of = self._collect_tree(root_state.node_id)

        if self.graph_builder:
            for w in root_state.lexicon.words:
                self._record_word(w, root_state.year, root_state.node_id)
            self.graph_builder.add_event("simulation_start", root_state.year, root_state.node_id)

        if not parent_of and not self.evolve_root:
            return {root_state.node_id: root_state}

        # Rodič musí existovat dřív než dítě, proto řadíme podle hloubky.
        fork_years = self._compute_fork_years(root_state, parent_of)

        # Root žije jen jako zdroj pro odštěpení, do výsledku se nevrací.
        states: Dict[str, State] = {root_state.node_id: root_state}

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
                    ),
                )

        last_year = root_state.year

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
                        self.semantic_history.schedule_proposals(
                            branch_state,
                            event.year,
                            self.semantic_evaluator,
                            semantic_rng,
                            push,
                            _PRIO_SEMANTICS,
                            self._horizon_for(branch_state.year, event.branch_id),
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
                    evaluator = LexicalEvaluator(
                        replacement_rate=float(lexical.get("replacement_rate", 0.015)),
                        loss_rate=float(lexical.get("loss_rate", 0.01)),
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
                            )

            elif isinstance(event, SocialEvent):
                branch_state = states.get(event.branch_id)
                if branch_state is not None:
                    branch_state.year = event.year
                    for key, value in event.changes.items():
                        if key in {
                            "prestige",
                            "mobility",
                            "literacy",
                            "standardization",
                            "population",
                        }:
                            branch_state.social[key] = max(0.0, min(1.0, float(value)))
                    if self.graph_builder:
                        self.graph_builder.add_event(
                            "social_change",
                            event.year,
                            event.branch_id,
                            changes=dict(branch_state.social),
                        )

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
                    event.volume,
                    event.domain,
                    event.prestige,
                    event.calque_rate,
                    event.adapt,
                )

        result = {
            node_id: state
            for node_id, state in states.items()
            if node_id in parent_of or (self.evolve_root and node_id == root_state.node_id)
        }
        final_year = max(last_year, self.end_year or last_year)

        for state in result.values():
            state.year = final_year

        return result

    # --- pomocné metody ---------------------------------------------------

    def _collect_tree(self, root_id: str) -> Dict[str, str]:
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
        if unreachable:
            warnings.warn(
                f"Uzly {sorted(unreachable)} nejsou z '{root_id}' dosažitelné "
                f"a nebudou simulovány.",
                stacklevel=2,
            )

        return parent_of

    def _compute_fork_years(self, root_state: State, parent_of: Dict[str, str]) -> Dict[str, int]:
        """Uzel se odštěpí v roce svého prvního pravidla, jinak spolu s rodičem."""
        fork_years: Dict[str, int] = {root_state.node_id: root_state.year}

        for child_id, parent_id in parent_of.items():
            rules = self.graph.get_rules_for_edge(parent_id, child_id)
            years = [r.year for r in rules if r.year is not None]
            parent_year = fork_years.get(parent_id, root_state.year)
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

        return State(
            node_id=child_id,
            year=year,
            inventory=copy.deepcopy(parent_state.inventory),
            lexicon=new_lexicon,
            parent_id=parent_state.node_id,
            map=node_cfg.get("map", {}),
        )

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
        standard = state.social.get("standardization", 0.0)
        literacy = state.social.get("literacy", 0.0)
        mobility = state.social.get("mobility", 0.5)
        social_macro = {
            "conservatism": min(1.0, max(0.0, 0.35 * standard + 0.15 * literacy)),
            "change_rate": max(0.1, 0.65 + mobility),
            "isolation": float(node_cfg.get("map", {}).get("isolation", node_cfg.get("isolation", 0.5))),
            "contact_intensity": self._contact_intensity(state.node_id),
        }
        return MacroParams.from_config(
            self.preset.get("macro") if self.preset else None,
            self.profile_macro,
            social_macro,
            node_cfg.get("macro"),
            node_cfg.get("map", {}).get("macro"),
        )

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

    def _propagate_sound_change(
        self, state: State, change: SoundChangeEvent, progress: float, year: int
    ) -> None:
        """Aplikuje dosud neadoptovanou, deterministicky vybranou část lexikonu."""
        state.year = year
        adopted = self._sound_change_adoptions[change.change_id]
        threshold = min(1.0, max(0.0, progress * change.intensity))
        selected = []
        for word in state.lexicon.words:
            if not word.active:
                continue
            key = self._sound_change_word_key(word)
            if key in adopted or not change.rule.can_apply_to_word(word):
                continue
            sample = random.Random(
                derive_seed(self.seed, "sound-change-adoption", change.change_id, *map(str, key))
            ).random()
            adoption_threshold = self.decision_engine.sound_change_adoption_threshold(
                word, change.rule, sample
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
            },
        )

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
        # Sto let je jednotka pravděpodobností SemanticEvaluatoru. První
        # posun přichází až po vzniku jazyka, nikdy při samotném odštěpení.
        for year in range(start_year + 100, horizon + 1, 100):
            push(year, _PRIO_SEMANTICS, SemanticEvent(year, node_id))

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
        )
        analogy_rate = float(morphology.get("analogy_rate", 0.0))
        if has_creation:
            push(start_year + 1, _PRIO_MORPHOLOGY, MorphologyEvent(start_year + 1, node_id))
        if analogy_rate > 0:
            horizon = self._horizon_for(start_year, node_id)
            for year in range(start_year + 200, horizon + 1, 200):
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

    def _word_signature(self, word) -> tuple:
        """Vše, co tvoří historicky rozlišitelný stav lexému."""
        return (
            tuple(tuple(sorted(segment.features.items())) for segment in word.segments),
            word.concept_id,
            tuple(sorted(word.polysemy)),
            word.stress_index,
            tuple(sorted(word.long_nuclei)),
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
    ):
        """
        Provede výpůjčku `volume` slov ze `source` do `target`.
        Slova získají origin_year = year a source_id = source.node_id.
        """
        if not source.lexicon.words:
            return

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
        num_borrow = min(max(1, round(volume * multiplier)), len(source.lexicon.words))
        rng = random.Random(
            derive_seed(self.seed, "contact", source.node_id, target.node_id, str(year), domain)
        )
        candidates = [word for word in source.lexicon.words if word.active]
        if not candidates:
            return
        # Obchod zvýhodní frekventní lexémy, válka naopak méně stabilní
        # okrajové položky; bez domény je kontakt neutrální.
        exponent = 1.8 if domain in {"trade", "religion"} else 0.65 if domain == "war" else 1.0
        weights = [max(0.02, word.frequency) ** exponent for word in candidates]
        words_to_borrow = rng.choices(candidates, weights=weights, k=num_borrow)
        target_view = InventoryView.from_lexicon(target.lexicon, self.mapper)

        borrowed_count = 0
        calque_count = 0
        for borrow_index, w in enumerate(words_to_borrow):
            # Zabráníme zbytečným duplicitám: Pokud už cílový jazyk má pro tento koncept
            # slovo, které zní úplně stejně, výpůjčku přeskočíme.
            existing_words = target.lexicon.get_words(w.concept_id)
            if any(x.segments == w.segments for x in existing_words):
                continue

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

            target.lexicon.words.append(new_word)
            borrowed_count += 1

            if self.graph_builder:
                self._record_word(new_word, year, target.node_id)
                self.graph_builder.add_origin_edge(new_word.id, w.id, "borrowed")

        if self.graph_builder:
            self.graph_builder.add_event(
                "contact",
                year,
                target.node_id,
                source_id=source.node_id,
                domain=domain,
                requested_volume=volume,
                borrowed_count=borrowed_count,
                calque_count=calque_count,
                prestige=prestige,
                adapted=adapt,
            )

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
