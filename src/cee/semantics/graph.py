import os
import random
from pathlib import Path

import networkx as nx
import yaml

from cee.semantics.builder import normalize_gloss


class SemanticGraph:
    """
    Obaluje NetworkX DiGraph pro práci s DatSemShift/CLICS4 sítěmi.
    Zajišťuje načtení .graphml a metody pro náhodné sémantické posuny.
    """

    def __init__(self, graphml_path: str = None):
        if graphml_path is None:
            home = str(Path.home())
            graphml_path = os.path.join(home, ".cee", "semantics", "graph.graphml")

        if not os.path.exists(graphml_path):
            raise FileNotFoundError(f"Sémantický graf nenalezen: {graphml_path}. Spusťte nejdřív builder.py")

        if graphml_path.endswith(".yaml"):
            self._load_yaml(graphml_path)
        else:
            self.G = nx.read_graphml(graphml_path)

        # CLICS4/DatSemShift builder klíčuje uzly normalizovaným (velkými
        # písmeny) Concepticon glosem — viz semantics/builder.py. Proto-lexikon
        # ale typicky nese anglická concept_id malými písmeny (`concepts.json`
        # generuje "sun", "water", ...). Bez sjednocení casingu tady by
        # `has_node("sun")` bylo vždy False a sémantika by potichu nedělala
        # vůbec nic, i když je graf sestavený správně.
        self.G = nx.relabel_nodes(self.G, {n: normalize_gloss(str(n)) for n in self.G.nodes})

    def _load_yaml(self, filepath: str):
        self.G = nx.DiGraph()
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            for shift in data.get("shifts", []):
                u = shift["source"]
                v = shift["target"]
                w = shift.get("weight", 1.0)
                fields = shift.get("fields", [])
                self.G.add_node(u, name=u)
                self.G.add_node(v, name=v)
                self.G.add_edge(u, v, weight=w, type="yaml_mock", fields=fields)

    def get_concept_name(self, concept_id: str) -> str:
        key = normalize_gloss(concept_id)
        if self.G.has_node(key):
            return self.G.nodes[key].get("name", concept_id)
        return concept_id

    def get_possible_shifts(self, concept_id: str):
        """
        Vrátí seznam možných cílových konceptů a jejich pravděpodobností (vah).
        Vrací list of tuples: (target_id, target_name, weight, shift_type)
        """
        key = normalize_gloss(concept_id)
        if not self.G.has_node(key):
            return []

        shifts = []
        for target in self.G.successors(key):
            edge_data = self.G.get_edge_data(key, target)
            weight = edge_data.get("weight", 1)
            edge_type = edge_data.get("type", "unknown")
            name = self.G.nodes[target].get("name", target)
            shifts.append((target, name, weight, edge_type))

        # Seřadíme podle váhy klesajíc
        shifts.sort(key=lambda x: x[2], reverse=True)
        return shifts

    def random_shift(self, concept_id: str, random_gen=None, edge_type: str = None):
        """
        Vybere jeden cílový koncept na základě vážené pravděpodobnosti.
        Pokud `edge_type` je zadaný, filtruje hrany pouze na tento typ (např. 'shift' nebo 'colexification').
        Pokud uzel nemá následníky odpovídající filtru, vrátí None.
        """
        shifts = self.get_possible_shifts(concept_id)
        if edge_type:
            shifts = [s for s in shifts if s[3] == edge_type]

        if not shifts:
            return None

        targets = [s[0] for s in shifts]
        weights = [float(s[2]) for s in shifts]

        gen = random_gen if random_gen else random
        chosen = gen.choices(targets, weights=weights, k=1)[0]
        return chosen

    def lexical_entries(self) -> list[dict[str, object]]:
        """Vrátí deterministický výchozí slovník pokrývající celý graf.

        Každý význam v CLICS4/DatSemShiftu dostane pokrytí. Kde je doložená
        kolexifikace, spojíme dvojici významů do jednoho lexému — protojazyk
        tak nezačíná mechanicky jedním slovem pro každý koncept, ale stále
        neztrácí žádný sémantický uzel.
        """
        uncovered = set(str(node) for node in self.G.nodes)
        entries: list[dict[str, object]] = []

        while uncovered:
            concept = min(uncovered)
            neighbors = []
            for target in self.G.successors(concept):
                data = self.G.get_edge_data(concept, target) or {}
                if target in uncovered and data.get("type") == "colexification":
                    neighbors.append((float(data.get("weight", 1)), str(target)))

            partner = max(neighbors, default=None, key=lambda item: (item[0], item[1]))
            meanings = [concept]
            if partner:
                meanings.append(partner[1])

            uncovered.difference_update(meanings)
            entries.append(
                {
                    "id": concept.lower(),
                    "polysemy": [meaning.lower() for meaning in meanings[1:]],
                }
            )

        return entries


if __name__ == "__main__":
    # Rychlý test pro ukázku
    sg = SemanticGraph()
    print(f"Načten graf s {sg.G.number_of_nodes()} koncepty.")

    for gloss in ["animal", "tree", "sun", "water"]:
        shifts = sg.get_possible_shifts(gloss)
        print(f"\nCo se může vyvinout z konceptu {gloss.upper()}?")
        for t_id, name, w, t_type in shifts[:10]:
            print(f" -> {name} (Váha: {w}, Typ: {t_type})")
