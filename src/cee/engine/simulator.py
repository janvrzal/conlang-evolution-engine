import copy
import heapq
import random
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from cee.core.models import Inventory, Lexicon, State, Word
from cee.engine.generator import SoundChangeGenerator
from cee.engine.morphology import MorphologyEvaluator
from cee.engine.phonology import FeatureMapper
from cee.engine.rules import Rule
from cee.engine.topology import EvolutionGraph

# Priorita událostí ve stejném roce: uzel musí nejdřív vzniknout, teprve pak
# na něj smí dopadnout zvuková změna, a až nakonec kontakt s jiným jazykem.
_PRIO_FORK = 0
_PRIO_PHONOLOGY = 1
_PRIO_CONTACT = 2


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

    def __init__(self, graph: EvolutionGraph, mapper: FeatureMapper, preset: Dict[str, Any] = None,
                 seed: int = 42, semantic_evaluator=None):
        self.graph = graph
        self.mapper = mapper
        self.preset = preset
        self.random = random.Random(seed)
        self.semantic_evaluator = semantic_evaluator
        if self.preset:
            self.generator = SoundChangeGenerator(self.preset, seed)
        else:
            self.generator = None

    def simulate(self, root_state: State) -> Dict[str, State]:
        """
        Odsimuluje celou síť od root_state a vrátí finální stavy (uzly).

        Prochází strom do libovolné hloubky: každý uzel se odštěpí od svého
        rodiče v roce prvního pravidla na příslušné hraně.
        """
        parent_of = self._collect_tree(root_state.node_id)
        if not parent_of:
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
            push(contact.year, _PRIO_CONTACT,
                 ContactEvent(contact.year, contact.source_id, contact.target_id, contact.volume))

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
                    event.rule.apply_to_word(word)
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

        result = {node_id: state for node_id, state in states.items() if node_id in parent_of}

        for state in result.values():
            state.year = last_year

            if self.semantic_evaluator:
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
            fork_years[child_id] = min(years) if years else parent_year

            # Dítě nikdy nesmí vzniknout dřív než rodič.
            fork_years[child_id] = max(fork_years[child_id], parent_year)

        return fork_years

    def _fork(self, parent_state: State, child_id: str, year: int) -> State:
        """Odštěpí nový uzel jako nezávislou kopii rodiče v daném roce."""
        node_cfg = self.graph.node_configs.get(child_id, {})
        new_lexicon = Lexicon(words=[copy.deepcopy(w) for w in parent_state.lexicon.words])

        return State(
            node_id=child_id,
            year=year,
            inventory=copy.deepcopy(parent_state.inventory),
            lexicon=new_lexicon,
            parent_id=parent_state.node_id,
            map=node_cfg.get('map', {}),
        )

    def _generated_rules_for(self, child_id: str, state: State, start_year: int) -> List[Rule]:
        """
        Dogeneruje pravidla pro hranu, která žádná nemá. Výsledek se nezapisuje
        zpět do topologie — graf zůstává neměnný, takže opakované volání
        `simulate()` dá stejný výsledek.
        """
        if not self.generator:
            return []

        edge_rules = self.graph.get_rules_for_edge(state.parent_id, child_id)
        if edge_rules:
            return []

        if not state.inventory.segments:
            state.inventory = Inventory(segments=self._inventory_of(state.lexicon))

        return self.generator.generate_rules_for_edge(
            state, start_year, start_year + 200, num_rules=2
        )

    def _inventory_of(self, lexicon: Lexicon) -> set:
        inventory = set()
        for word in lexicon.words:
            for segment in word.segments:
                ipa = self.mapper.segment_to_ipa(segment)
                if ipa and ipa != "?":
                    inventory.add(ipa)
        return inventory

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
        words_to_borrow = self.random.sample(source.lexicon.words, num_borrow)

        for w in words_to_borrow:
            new_word = copy.deepcopy(w)
            # Nastavíme stopu výpůjčky — díky origin_year slovo unikne starším
            # zvukovým změnám (viz Rule.apply_to_word).
            new_word.origin_year = year
            new_word.source_id = source.node_id

            # Pokud už tam slovo se stejným concept_id je, budeme mít obě formy
            # (např. domácí 'brother' a cizí 'frater' jako synonyma).
            target.lexicon.words.append(new_word)
