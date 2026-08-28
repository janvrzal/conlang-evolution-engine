import copy
import random
from dataclasses import dataclass
from typing import List, Dict, Any

from cee.core.models import State, Lexicon, Word
from cee.engine.topology import EvolutionGraph
from cee.engine.rules import Rule
from cee.engine.phonology import FeatureMapper
from cee.engine.generator import SoundChangeGenerator

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
    """
    def __init__(self, graph: EvolutionGraph, mapper: FeatureMapper, preset: Dict[str, Any] = None, seed: int = 42):
        self.graph = graph
        self.mapper = mapper
        self.preset = preset
        self.random = random.Random(seed)
        if self.preset:
            self.generator = SoundChangeGenerator(self.preset, seed)
        else:
            self.generator = None
            
    def simulate(self, root_state: State) -> Dict[str, State]:
        """
        Odsimuluje celou síť od root_state a vrátí finální stavy (uzly).
        """
        # 1. Identifikace větví a počátečních stavů
        active_branches: Dict[str, State] = {}
        # Root uzel se hned zkopíruje do svých dětí (začátek jejich cesty)
        children = self.graph.get_children(root_state.node_id)
        if not children:
            return {root_state.node_id: root_state}
            
        for child_id in children:
            # Deepcopy slovníku, aby se větve vyvíjely nezávisle
            new_lexicon = Lexicon(words=[copy.deepcopy(w) for w in root_state.lexicon.words])
            
            node_cfg = self.graph.node_configs.get(child_id, {})
            node_map = node_cfg.get('map', {})
            
            state = State(
                node_id=child_id,
                year=root_state.year, # Startují v čase rodiče
                inventory=copy.deepcopy(root_state.inventory),
                lexicon=new_lexicon,
                parent_id=root_state.node_id
            )
            state.map = node_map
            active_branches[child_id] = state
            
        # 2. Posbírání všech událostí a jejich seřazení v čase (globální lockstep)
        events = []
        for edge in self.graph.vertical_edges:
            # Pokud na hraně nejsou pravidla a máme generátor, vygenerujeme je!
            if not edge.rules and self.generator:
                # Zjistíme rok uzlu
                start_year = root_state.year
                # Najdeme kdy se stane nějaký kontakt s touto větví, abychom znali konec.
                # Zjednodušeně: dáme hranici na +200 let, pokud není zadáno jinak
                end_year = start_year + 200
                
                # Získáme state
                state = active_branches.get(edge.child_id)
                if state:
                    edge.rules = self.generator.generate_rules_for_edge(state, start_year, end_year, num_rules=2)
                    
            for rule in edge.rules:
                if rule.year is not None:
                    events.append(PhonologyEvent(year=rule.year, branch_id=edge.child_id, rule=rule))
                    
        for contact in self.graph.contact_edges:
            events.append(ContactEvent(year=contact.year, source_id=contact.source_id, target_id=contact.target_id, volume=contact.volume))
            
        # Třídění událostí podle roku
        events.sort(key=lambda e: e.year)
        
        # 3. Zpracování událostí chronologicky
        for event in events:
            if isinstance(event, PhonologyEvent):
                # Aplikace fonologického pravidla na danou větev
                branch_state = active_branches.get(event.branch_id)
                if branch_state:
                    for word in branch_state.lexicon.words:
                        event.rule.apply_to_word(word)
                    # Zde by se měl aktualizovat Inventory (stejně jako ve Foldu)
                    
            elif isinstance(event, ContactEvent):
                # Výpůjčka z jedné větve do druhé
                source_state = active_branches.get(event.source_id)
                target_state = active_branches.get(event.target_id)
                
                if source_state and target_state:
                    self._apply_contact(source_state, target_state, event.year, event.volume)
                    
        # Na konci simulace aktualizujeme rok větví (např. na rok poslední události nebo předepsaný konec)
        # Zde zjednodušeně nastavíme rok poslední události
        last_year = events[-1].year if events else root_state.year
        for branch_id, state in active_branches.items():
            state.year = last_year
            
        return active_branches
        
    def _apply_contact(self, source: State, target: State, year: int, volume: int):
        """
        Provede výpůjčku `volume` slov ze `source` do `target`.
        Slova získají origin_year = year a source_id = source.node_id.
        """
        # Vybereme náhodná slova ze zdroje (v budoucnu váženo sémantickými kategoriemi výpůjčky)
        if not source.lexicon.words:
            return
            
        num_borrow = min(volume, len(source.lexicon.words))
        words_to_borrow = self.random.sample(source.lexicon.words, num_borrow)
        
        for w in words_to_borrow:
            # Zkopírujeme slovo
            new_word = copy.deepcopy(w)
            # Nastavíme stopu výpůjčky!
            new_word.origin_year = year
            new_word.source_id = source.node_id
            
            # Přidáme do cílového jazyka
            # Pokud už tam slovo se stejným concept_id je, budeme mít obě formy 
            # (např. domácí 'brother' a cizí 'frater' jako synonyma)
            target.lexicon.words.append(new_word)
