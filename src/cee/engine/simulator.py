import uuid

import copy
import heapq
import random
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from cee.core.models import Inventory, Lexicon, State
from cee.engine.generator import MacroParams, SoundChangeGenerator

from cee.engine.graph_builder import GraphBuilder
from cee.engine.inventory import InventoryView
from cee.engine.rng import derive_seed
from cee.engine.morphology import MorphologyEvaluator
from cee.engine.phonology import FeatureMapper
from cee.engine.rules import Rule
from cee.engine.topology import EvolutionGraph

# Priorita událostí ve stejném roce: uzel musí nejdřív vzniknout, teprve pak
# na něj smí dopadnout zvuková změna, a až nakonec kontakt s jiným jazykem.
_PRIO_FORK = 0
_PRIO_PHONOLOGY = 1
_PRIO_CONTACT = 2

# Kolik let v průměru připadá na jednu zvukovou změnu, než se do toho promítnou
# makro-parametry uzlu. Řádově odpovídá tempu doloženému v historických
# gramatikách; přesné ladění je práce pro validaci V2a.
YEARS_PER_RULE_SLOT = 25


@dataclass
class ForkEvent:
    year: int
    parent_id: str
    child_id: str


@dataclass
class PhonologyEvent:
    year: int
    branch_id: str
    rule: Rule


@dataclass
class ContactEvent:
    year: int
    source_id: str
    target_id: str
    volume: int


class EvolutionSimulator:
    """
    Řídí globální lockstep simulaci evoluční sítě.

    Všechny události (větvení, zvukové změny, kontakty) se slijí do jedné
    fronty seřazené podle absolutního roku a zpracují chronologicky, takže
    všechny větve sdílejí tutéž časovou osu.
    """

    def __init__(self, graph_topo: EvolutionGraph, mapper: FeatureMapper, preset: Dict[str, Any] = None,
                 seed: int = 42, semantic_evaluator=None,
                 graph_builder: Optional[GraphBuilder] = None,
                 end_year: Optional[int] = None, evolve_root: bool = False):
        self.graph = graph_topo
        self.mapper = mapper
        self.graph_builder = graph_builder
        self.preset = preset
        self.random = random.Random(seed)
        self.semantic_evaluator = semantic_evaluator
        self.seed = seed
        self.evolve_root = evolve_root
        # Časová hloubka simulace. Dokud tu nebyla, generátor měl natvrdo
        # horizont 200 let a dvě pravidla — jazyky ztuhly hned na začátku
        # a pozdější kontakt už zastihl nehybný stav.
        self.end_year = end_year
        # Generátor se staví pro každý uzel zvlášť, aby měl vlastní seed
        # i vlastní makro-parametry (viz _generator_for).
        self._generators: Dict[str, SoundChangeGenerator] = {}

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
            macro = MacroParams.from_config(
                self.preset.get("macro"),
                node_cfg.get("macro"),
                node_cfg.get("map", {}).get("macro"),
            )
            self._generators[node_id] = SoundChangeGenerator(
                self.preset, seed=derive_seed(self.seed, node_id), macro=macro
            )
        return self._generators[node_id]

    def simulate(self, root_state: State) -> Dict[str, State]:
        """
        Odsimuluje celou síť od root_state a vrátí finální stavy (uzly).

        Prochází strom do libovolné hloubky: každý uzel se odštěpí od svého
        rodiče v roce prvního pravidla na příslušné hraně.
        """
        parent_of = self._collect_tree(root_state.node_id)
        
        if self.graph_builder:
            for w in root_state.lexicon.words:
                self.graph_builder.add_word(
                    w.id, w.concept_id, self.mapper.render_word(w),
                    root_state.year, root_state.node_id, list(w.polysemy)
                )

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
            push(fork_years[child_id], _PRIO_FORK, ForkEvent(fork_years[child_id], parent_id, child_id))

        if self.evolve_root:
            for rule in self._generated_rules_for_root(root_state):
                push(rule.year, _PRIO_PHONOLOGY, PhonologyEvent(rule.year, root_state.node_id, rule))

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
                push(contact.year, _PRIO_CONTACT,
                     ContactEvent(contact.year, source_id, target_id, contact.volume))

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
                # Pravidla se generují až tady — čerstvě odštěpený uzel už zná
                # svůj inventář i biom, takže generátor má z čeho vycházet.
                for rule in self._generated_rules_for(event.child_id, child_state, year):
                    push(rule.year, _PRIO_PHONOLOGY, PhonologyEvent(rule.year, event.child_id, rule))

            elif isinstance(event, PhonologyEvent):
                branch_state = states.get(event.branch_id)
                if branch_state is None:
                    continue

                for word in branch_state.lexicon.words:
                    before_ipa = self.mapper.render_word(word)
                    old_id = word.id
                    
                    if event.rule.apply_to_word(word):
                        after_ipa = self.mapper.render_word(word)
                        if after_ipa != before_ipa:
                            word.parent_word_id = old_id
                            word.id = str(uuid.uuid4())
                            word.origin_type = "mutated"
                            word.origin_rule = event.rule.name
                            word.origin_year = event.year
                            
                            if self.graph_builder:
                                self.graph_builder.add_word(
                                    word.id, word.concept_id, after_ipa,
                                    event.year, event.branch_id, list(word.polysemy)
                                )
                                self.graph_builder.add_origin_edge(
                                    word.id, old_id, "mutated", event.rule.name
                                )

                branch_state.inventory = Inventory(
                    segments=self._inventory_of(branch_state.lexicon)
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
                self._apply_contact(source_state, target_state, event.year, event.volume)

        result = {
            node_id: state
            for node_id, state in states.items()
            if node_id in parent_of or (self.evolve_root and node_id == root_state.node_id)
        }
        final_year = max(last_year, self.end_year or last_year)

        for state in result.values():
            start_year = state.year
            state.year = final_year

            if self.semantic_evaluator:
                # Sémantický posun nyní škáluje s časem (jednou za 100 let)
                centuries = max(1, round((final_year - start_year) / 100))
                for _ in range(centuries):
                    self.semantic_evaluator.evaluate(state.lexicon)

            self._apply_compounds(state)

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
        
        for parent_word in parent_state.lexicon.words:
            new_word = copy.deepcopy(parent_word)
            new_word.parent_word_id = parent_word.id
            new_word.id = str(uuid.uuid4())
            new_word.origin_type = "inherited"
            new_word.origin_rule = None
            new_word.origin_year = year
            new_lexicon.words.append(new_word)
            
            if self.graph_builder:
                self.graph_builder.add_word(
                    new_word.id, new_word.concept_id, self.mapper.render_word(new_word),
                    year, child_id, list(new_word.polysemy)
                )
                self.graph_builder.add_origin_edge(
                    new_word.id, parent_word.id, "inherited"
                )

        return State(
            node_id=child_id,
            year=year,
            inventory=copy.deepcopy(parent_state.inventory),
            lexicon=new_lexicon,
            parent_id=parent_state.node_id,
            map=node_cfg.get('map', {}),
        )

    def _horizon_for(self, start_year: int, child_id: str) -> int:
        """
        Dokdy se pro danou hranu generují pravidla.

        Sahá až k zadané hloubce simulace, nejméně však k poslední události,
        která se uzlu týká — jinak by jazyk ztuhl dřív, než na něj někdo naváže.
        """
        candidates = [self.end_year] if self.end_year else []

        candidates += [c.year for c in self.graph.contact_edges
                       if child_id in (c.source_id, c.target_id)]
        candidates += [r.year for e in self.graph.vertical_edges if e.parent_id == child_id
                       for r in e.rules if r.year is not None]

        horizon = max([c for c in candidates if c is not None], default=start_year + 200)
        return max(horizon, start_year + 1)

    def _generated_rules_for(self, child_id: str, state: State, start_year: int) -> List[Rule]:
        """
        Dogeneruje pravidla pro hranu, která žádná nemá. Výsledek se nezapisuje
        zpět do topologie — graf zůstává neměnný, takže opakované volání
        `simulate()` dá stejný výsledek.
        """
        generator = self._generator_for(child_id)
        if not generator:
            return []

        edge_rules = self.graph.get_rules_for_edge(state.parent_id, child_id)
        if edge_rules:
            return []

        view = InventoryView.from_lexicon(state.lexicon, self.mapper)
        state.inventory = view.to_inventory()

        end_year = self._horizon_for(start_year, child_id)

        # Počet pokusů roste s délkou období, ne s pevným číslem — jinak by
        # tisíciletý vývoj měl stejně změn jako dvě století.
        slots = max(1, round((end_year - start_year) / YEARS_PER_RULE_SLOT))

        return generator.generate_rules_for_edge(
            state, start_year, end_year, num_rules=slots, inventory=view
        )

    def _generated_rules_for_root(self, state: State) -> List[Rule]:
        """Vygeneruje historii i pro kořenový protojazyk zobrazený v UI."""
        generator = self._generator_for(state.node_id)
        if not generator:
            return []

        view = InventoryView.from_lexicon(state.lexicon, self.mapper)
        state.inventory = view.to_inventory()
        end_year = self.end_year or state.year + 200
        slots = max(1, round((end_year - state.year) / YEARS_PER_RULE_SLOT))
        return generator.generate_rules_for_edge(
            state, state.year, end_year, num_rules=slots, inventory=view
        )

    def _inventory_of(self, lexicon: Lexicon) -> set:
        return set(InventoryView.from_lexicon(lexicon, self.mapper))

    def _apply_compounds(self, state: State) -> None:
        """
        Vytvoří složeniny předepsané v topologii daného uzlu, např.:

            nodes:
              - id: north
                compounds:
                  - head: "město"
                    modifier: "zlatý"
                    id: "zlaté_město"
        """
        specs = self.graph.node_configs.get(state.node_id, {}).get('compounds', [])
        if not specs:
            return

        morph = MorphologyEvaluator()
        for spec in specs:
            head, modifier, new_id = spec.get('head'), spec.get('modifier'), spec.get('id')
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

    def _apply_contact(self, source: State, target: State, year: int, volume: int):
        """
        Provede výpůjčku `volume` slov ze `source` do `target`.
        Slova získají origin_year = year a source_id = source.node_id.
        """
        if not source.lexicon.words:
            return

        num_borrow = min(volume, len(source.lexicon.words))
        rng = random.Random(derive_seed(self.seed, "contact", source.node_id,
                                        target.node_id, str(year)))
        words_to_borrow = rng.sample(source.lexicon.words, num_borrow)


        for w in words_to_borrow:
            # Zabráníme zbytečným duplicitám: Pokud už cílový jazyk má pro tento koncept 
            # slovo, které zní úplně stejně, výpůjčku přeskočíme.
            existing_words = [x for x in target.lexicon.words if x.concept_id == w.concept_id]
            if any(x.segments == w.segments for x in existing_words):
                continue
                
            new_word = copy.deepcopy(w)
            new_word.parent_word_id = w.id
            new_word.id = str(uuid.uuid4())
            new_word.origin_type = "borrowed"
            new_word.origin_rule = None
            new_word.origin_year = year
            new_word.source_id = source.node_id

            target.lexicon.words.append(new_word)
            
            if self.graph_builder:
                self.graph_builder.add_word(
                    new_word.id, new_word.concept_id, self.mapper.render_word(new_word),
                    year, target.node_id, list(new_word.polysemy)
                )
                self.graph_builder.add_origin_edge(
                    new_word.id, w.id, "borrowed"
                )
