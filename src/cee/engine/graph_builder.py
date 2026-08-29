from typing import Dict, List, Any, Optional

class GraphBuilder:
    """Sbírá uzly slov a hrany původu během simulace v paměti.

    Po dokončení jej zpracuje zvolený adaptér `GenealogyStore`: výchozí
    souborový, nebo volitelný Neo4j. Builder proto nezná žádnou databázi.
    """
    def __init__(self):
        self.nodes: List[Dict[str, Any]] = []
        self.edges: List[Dict[str, Any]] = []

    def add_word(self, word_id: str, concept_id: str, ipa: str, year: int, language_id: str, polysemy: List[str]):
        """Přidá uzel slova do grafu."""
        self.nodes.append({
            "id": word_id,
            "concept_id": concept_id,
            "ipa": ipa,
            "year": year,
            "language_id": language_id,
            "polysemy": polysemy,
        })

    def add_origin_edge(self, target_id: str, source_id: str, origin_type: str, rule: Optional[str] = None):
        """Přidá hranu původu od target k source."""
        edge = {
            "target_id": target_id,
            "source_id": source_id,
            "type": origin_type,
        }
        if rule:
            edge["rule"] = rule
        self.edges.append(edge)
