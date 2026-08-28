import networkx as nx
import random
import os
import yaml
from pathlib import Path

class SemanticGraph:
    """
    Obaluje NetworkX DiGraph pro práci s DatSemShift sítěmi.
    Zajišťuje načtení .graphml a metody pro náhodné sémantické posuny.
    """
    def __init__(self, graphml_path: str = None):
        if graphml_path is None:
            home = str(Path.home())
            graphml_path = os.path.join(home, ".cee", "semantics", "graph.graphml")
            
        if not os.path.exists(graphml_path):
            raise FileNotFoundError(f"Sémantický graf nenalezen: {graphml_path}. Spusťte nejdřív builder.py")
            
        if graphml_path.endswith('.yaml'):
            self._load_yaml(graphml_path)
        else:
            self.G = nx.read_graphml(graphml_path)
            
    def _load_yaml(self, filepath: str):
        self.G = nx.DiGraph()
        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            for shift in data.get('shifts', []):
                u = shift['source']
                v = shift['target']
                w = shift.get('weight', 1.0)
                fields = shift.get('fields', [])
                self.G.add_node(u, name=u)
                self.G.add_node(v, name=v)
                self.G.add_edge(u, v, weight=w, type='yaml_mock', fields=fields)
        
    def get_concept_name(self, concept_id: str) -> str:
        if self.G.has_node(concept_id):
            return self.G.nodes[concept_id].get('name', concept_id)
        return concept_id
        
    def get_possible_shifts(self, concept_id: str):
        """
        Vrátí seznam možných cílových konceptů a jejich pravděpodobností (vah).
        Vrací list of tuples: (target_id, target_name, weight, shift_type)
        """
        if not self.G.has_node(concept_id):
            return []
            
        shifts = []
        for target in self.G.successors(concept_id):
            edge_data = self.G.get_edge_data(concept_id, target)
            weight = edge_data.get('weight', 1)
            edge_type = edge_data.get('type', 'unknown')
            name = self.G.nodes[target].get('name', target)
            shifts.append((target, name, weight, edge_type))
            
        # Seřadíme podle váhy klesajíc
        shifts.sort(key=lambda x: x[2], reverse=True)
        return shifts

    def random_shift(self, concept_id: str, random_gen=None):
        """
        Vybere jeden cílový koncept na základě vážené pravděpodobnosti.
        Pokud uzel nemá následníky, vrátí None.
        """
        shifts = self.get_possible_shifts(concept_id)
        if not shifts:
            return None
            
        targets = [s[0] for s in shifts]
        weights = [float(s[2]) for s in shifts]
        
        gen = random_gen if random_gen else random
        chosen = gen.choices(targets, weights=weights, k=1)[0]
        return chosen

if __name__ == "__main__":
    # Rychlý test pro ukázku
    sg = SemanticGraph()
    print(f"Načten graf s {sg.G.number_of_nodes()} koncepty.")
    
    # Zkusíme najít něco zajímavého
    # Projdeme uzly a najdeme uzel obsahující slovo "animal"
    animal_id = None
    for n, d in sg.G.nodes(data=True):
        if d.get('name', '').lower() == 'animal':
            animal_id = n
            break
            
    if animal_id:
        print(f"\nCo se může vyvinout z konceptu ANIMAL ({animal_id})?")
        shifts = sg.get_possible_shifts(animal_id)
        for t_id, name, w, t_type in shifts:
            print(f" -> {name} (Váha: {w}, Typ: {t_type})")
            
    # Tree (strom) - v concepticonu ID "1209" nebo podobně, ale zkusíme hledat
    tree_id = None
    for n, d in sg.G.nodes(data=True):
        if d.get('name', '').lower() == 'tree':
            tree_id = n
            break
            
    if tree_id:
        print(f"\nCo se může vyvinout z konceptu TREE ({tree_id})?")
        shifts = sg.get_possible_shifts(tree_id)
        for t_id, name, w, t_type in shifts[:10]: # Top 10
            print(f" -> {name} (Váha: {w}, Typ: {t_type})")
