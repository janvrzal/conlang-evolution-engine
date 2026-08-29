"""Jednorázový, explicitně vyvolaný import výsledku ze starého globálního Neo4j."""
from __future__ import annotations

from cee.engine.graph_builder import GraphBuilder


def import_legacy_graph(uri: str, username: str, password: str) -> GraphBuilder:
    """Převede starý neadresovaný graf do builderu, bez jakéhokoli mazání."""
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Import starého Neo4j vyžaduje extra 'cee[neo4j]'.") from exc

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session() as session:
            nodes = [dict(row) for row in session.run(
                "MATCH (word:Word)-[:BELONGS_TO]->(language:Language) "
                "RETURN word.id AS id, word.concept_id AS concept_id, word.ipa AS ipa, "
                "word.year AS year, word.polysemy AS polysemy, language.id AS language_id"
            )]
            edges = [dict(row) for row in session.run(
                "MATCH (target:Word)-[origin:ORIGIN]->(source:Word) "
                "RETURN target.id AS target_id, source.id AS source_id, "
                "origin.type AS type, origin.rule AS rule"
            )]
    finally:
        driver.close()

    if not nodes:
        raise RuntimeError("Ve starém Neo4j není žádný slovní graf k importu.")
    builder = GraphBuilder()
    builder.nodes = nodes
    builder.edges = edges
    return builder
