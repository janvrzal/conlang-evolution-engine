from typing import Any, Dict, List, Optional


class GraphBuilder:
    """Sbírá uzly slov a hrany původu během simulace v paměti.

    Po dokončení jej zpracuje zvolený adaptér `GenealogyStore`: výchozí
    souborový, nebo volitelný Neo4j. Builder proto nezná žádnou databázi.
    """

    def __init__(self):
        self.nodes: List[Dict[str, Any]] = []
        self.edges: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        # Výstupní artefakty větví (gramatiky a souhrn metrik) se ukládají
        # spolu s genealogickým grafem, aby byly po restartu API stále dostupné.
        self.artifacts: Dict[str, Any] = {}

    def add_word(
        self,
        word_id: str,
        concept_id: str,
        ipa: str,
        year: int,
        language_id: str,
        polysemy: List[str],
        **metadata: Any,
    ):
        """Přidá uzel slova do grafu."""
        node = {
            "id": word_id,
            "concept_id": concept_id,
            "ipa": ipa,
            "year": year,
            "language_id": language_id,
            "polysemy": polysemy,
        }
        node.update(metadata)
        self.nodes.append(node)

    def add_origin_edge(
        self, target_id: str, source_id: str, origin_type: str, rule: Optional[str] = None
    ):
        """Přidá hranu původu od target k source."""
        edge = {
            "target_id": target_id,
            "source_id": source_id,
            "type": origin_type,
        }
        if rule:
            edge["rule"] = rule
        self.edges.append(edge)

    def add_event(self, kind: str, year: int, language_id: str, **payload: Any) -> None:
        """Zaznamená i nesegmentovou událost simulace pro audit a export."""
        self.events.append({"kind": kind, "year": year, "language_id": language_id, **payload})
