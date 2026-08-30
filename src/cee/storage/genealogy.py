"""Úložiště genealogie výsledků simulace.

Výchozí implementace je lokální JSON soubor v ``~/.cee/runs``. Neo4j je
volitelný adaptér aktivovaný až explicitní konfigurací; běžná instalace CEE
tak pro simulaci, prohlížení ani export nepotřebuje databázový server.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol

from cee.engine.graph_builder import GraphBuilder


class GenealogyStore(Protocol):
    """Port pro uložení a čtení genealogie právě jedné simulace."""

    backend_name: str

    def save(self, run_id: str, builder: GraphBuilder) -> None: ...

    def delete(self, run_id: str) -> None: ...

    def language(
        self, run_id: str, node_id: str, year: int | None = None
    ) -> list[dict[str, Any]]: ...

    def isogloss(self, run_id: str, concept_id: str, year: int | None = None) -> dict[str, str]: ...

    def word_trace(self, run_id: str, word_id: str) -> list[dict[str, Any]]: ...

    def export(self, run_id: str) -> dict[str, Any]: ...


class RunNotFoundError(KeyError):
    """Požadovaný výsledek simulace už v úložišti není."""


def _active_words(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]], node_id: str, year: int | None
) -> list[dict[str, Any]]:
    """Vrátí aktuální řez slovníkem jazyka v zadaném roce."""
    timed = [
        word
        for word in nodes
        if word["language_id"] == node_id and (year is None or word["year"] <= year)
    ]
    timed_ids = {word["id"] for word in timed}
    superseded = {edge["source_id"] for edge in edges if edge["target_id"] in timed_ids}
    return [word for word in timed if word["id"] not in superseded and word.get("active", True)]


def _ancestor(
    word: dict[str, Any], by_id: dict[str, dict[str, Any]], parent_of: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    current = word
    seen: set[str] = set()
    while current["id"] not in seen and current["id"] in parent_of:
        seen.add(current["id"])
        parent = by_id.get(parent_of[current["id"]]["source_id"])
        if parent is None:
            break
        current = parent
    return current


def _trace_step(word: Any) -> dict[str, Any]:
    """Společná podoba historického kroku pro JSON i Neo4j adaptér."""
    get = word.get
    grammatical_features = get("grammatical_features")
    if grammatical_features is None and get("grammatical_features_json"):
        grammatical_features = json.loads(get("grammatical_features_json"))
    return {
        "year": word["year"],
        "form": word["ipa"],
        "form_prosodic": get("ipa_prosodic") or word["ipa"],
        "concept_id": get("concept_id"),
        "stress_index": get("stress_index"),
        "long_nuclei": get("long_nuclei") or [],
        "morpheme_boundaries": get("morpheme_boundaries") or [],
        "paradigm": get("paradigm"),
        "grammatical_features": grammatical_features or {},
        "active": True if get("active") is None else get("active"),
        "origin_type": get("origin_type") or "inherited",
    }


class FileGenealogyStore:
    """Bezserverové úložiště, jeden atomicky zapisovaný JSON na simulaci."""

    backend_name = "file"

    def __init__(self, directory: Path | None = None):
        configured = os.environ.get("CEE_RUNS_DIR")
        self.directory = directory or Path(configured).expanduser() if configured else directory
        if self.directory is None:
            self.directory = Path.home() / ".cee" / "runs"

    def _path(self, run_id: str) -> Path:
        if not run_id or any(
            char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for char in run_id
        ):
            raise ValueError("ID simulace smí obsahovat jen písmena, číslice, '-' a '_'.")
        assert self.directory is not None
        return self.directory / f"{run_id}.json"

    def _read(self, run_id: str) -> dict[str, Any]:
        path = self._path(run_id)
        try:
            with path.open(encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError as exc:
            raise RunNotFoundError(run_id) from exc

    def save(self, run_id: str, builder: GraphBuilder) -> None:
        path = self._path(run_id)
        assert self.directory is not None
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 2,
            "run_id": run_id,
            "nodes": builder.nodes,
            "edges": builder.edges,
            "events": builder.events,
        }
        fd, temporary = tempfile.mkstemp(prefix=f".{run_id}-", suffix=".json", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            Path(temporary).replace(path)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise

    def delete(self, run_id: str) -> None:
        self._path(run_id).unlink(missing_ok=True)

    def language(self, run_id: str, node_id: str, year: int | None = None) -> list[dict[str, Any]]:
        payload = self._read(run_id)
        nodes = payload["nodes"]
        edges = payload["edges"]
        by_id = {word["id"]: word for word in nodes}
        parent_of = {edge["target_id"]: edge for edge in edges}
        words = []
        for word in _active_words(nodes, edges, node_id, year):
            proto = _ancestor(word, by_id, parent_of)
            words.append(
                {
                    "id": word["id"],
                    "concept_id": word["concept_id"],
                    "to": word["ipa"],
                    "from": proto["ipa"],
                    "to_prosodic": word.get("ipa_prosodic", word["ipa"]),
                    "from_prosodic": proto.get("ipa_prosodic", proto["ipa"]),
                    "polysemy": word.get("polysemy", []),
                    "stress_index": word.get("stress_index"),
                    "long_nuclei": word.get("long_nuclei", []),
                    "morpheme_boundaries": word.get("morpheme_boundaries", []),
                    "paradigm": word.get("paradigm"),
                    "grammatical_features": word.get("grammatical_features", {}),
                    "frequency": word.get("frequency", 1.0),
                    "is_grammatical": word.get("is_grammatical", False),
                    "active": word.get("active", True),
                    "origin_type": word.get("origin_type", "inherited"),
                }
            )
        return words

    def isogloss(self, run_id: str, concept_id: str, year: int | None = None) -> dict[str, str]:
        payload = self._read(run_id)
        result: dict[str, str] = {}
        languages = {word["language_id"] for word in payload["nodes"]}
        for language_id in languages:
            candidates = [
                word
                for word in _active_words(payload["nodes"], payload["edges"], language_id, year)
                if word["concept_id"] == concept_id
            ]
            if candidates:
                result[language_id] = candidates[0]["ipa"]
        return result

    def word_trace(self, run_id: str, word_id: str) -> list[dict[str, Any]]:
        payload = self._read(run_id)
        by_id = {word["id"]: word for word in payload["nodes"]}
        if word_id not in by_id:
            return []
        parent_of = {edge["target_id"]: edge for edge in payload["edges"]}
        current = by_id[word_id]
        reverse_trace: list[tuple[dict[str, Any], dict[str, Any] | None]] = [(current, None)]
        seen: set[str] = set()
        while current["id"] not in seen and current["id"] in parent_of:
            seen.add(current["id"])
            relation = parent_of[current["id"]]
            parent = by_id.get(relation["source_id"])
            if parent is None:
                break
            reverse_trace.append((parent, relation))
            current = parent

        trace = []
        chronological = list(reversed(reverse_trace))
        for index, (word, incoming) in enumerate(chronological):
            step = _trace_step(word)
            if index == 0:
                step["note"] = "výchozí tvar"
            else:
                relation_to_child = chronological[index - 1][1]
                if relation_to_child:
                    step["rule_name"] = relation_to_child.get("rule")
                    step["type"] = relation_to_child["type"]
            trace.append(step)
        return trace

    def export(self, run_id: str) -> dict[str, Any]:
        return self._read(run_id)


class Neo4jGenealogyStore:
    """Volitelný Neo4j adaptér; nikdy nemaže cizí simulace."""

    backend_name = "neo4j"

    def __init__(self, uri: str, username: str, password: str):
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:  # pragma: no cover - záleží na extra balíčku
            raise RuntimeError(
                "Pro CEE_GENEALOGY_STORE=neo4j nainstaluj extra 'cee[neo4j]'."
            ) from exc
        self.driver = GraphDatabase.driver(uri, auth=(username, password))

    def save(self, run_id: str, builder: GraphBuilder) -> None:
        # Nahrazuje jen jeden běh, nikoli celý server Neo4j.
        self.delete(run_id)
        nodes = []
        for source in builder.nodes:
            node = dict(source)
            node["grammatical_features_json"] = json.dumps(
                node.pop("grammatical_features", {}), ensure_ascii=False, sort_keys=True
            )
            nodes.append(node)
        with self.driver.session() as session:
            session.run(
                "CREATE (:Simulation {id: $run_id, events_json: $events})",
                run_id=run_id,
                events=json.dumps(builder.events, ensure_ascii=False),
            ).consume()
            session.run(
                """
                UNWIND $nodes AS node
                MATCH (simulation:Simulation {id: $run_id})
                MERGE (language:Language {simulation_id: $run_id, id: node.language_id})
                MERGE (word:Word {simulation_id: $run_id, id: node.id})
                SET word.concept_id = node.concept_id, word.ipa = node.ipa,
                    word.ipa_prosodic = node.ipa_prosodic,
                    word.year = node.year, word.polysemy = node.polysemy,
                    word.stress_index = node.stress_index,
                    word.long_nuclei = node.long_nuclei,
                    word.morpheme_boundaries = node.morpheme_boundaries,
                    word.active = node.active, word.frequency = node.frequency,
                    word.paradigm = node.paradigm,
                    word.grammatical_features_json = node.grammatical_features_json,
                    word.is_grammatical = node.is_grammatical,
                    word.origin_type = node.origin_type
                MERGE (simulation)-[:CONTAINS]->(language)
                MERGE (language)<-[:BELONGS_TO]-(word)
                """,
                run_id=run_id,
                nodes=nodes,
            ).consume()
            session.run(
                """
                UNWIND $edges AS edge
                MATCH (target:Word {simulation_id: $run_id, id: edge.target_id})
                MATCH (source:Word {simulation_id: $run_id, id: edge.source_id})
                CREATE (target)-[:ORIGIN {type: edge.type, rule: edge.rule}]->(source)
                """,
                run_id=run_id,
                edges=builder.edges,
            ).consume()

    def delete(self, run_id: str) -> None:
        with self.driver.session() as session:
            session.run(
                "MATCH (simulation:Simulation {id: $run_id}) DETACH DELETE simulation",
                run_id=run_id,
            ).consume()
            session.run(
                "MATCH (word:Word {simulation_id: $run_id}) DETACH DELETE word", run_id=run_id
            ).consume()
            session.run(
                "MATCH (language:Language {simulation_id: $run_id}) DETACH DELETE language",
                run_id=run_id,
            ).consume()

    def _file_equivalent(self, run_id: str) -> FileGenealogyStore:
        raise NotImplementedError("Neo4j čtecí adaptér se implementuje přes Cypher dotazy.")

    def language(self, run_id: str, node_id: str, year: int | None = None) -> list[dict[str, Any]]:
        query = """
            MATCH (word:Word {simulation_id: $run_id})-[:BELONGS_TO]->(:Language {simulation_id: $run_id, id: $node_id})  # noqa: E501
            WHERE ($year IS NULL OR word.year <= $year)
              AND coalesce(word.active, true)
              AND NOT EXISTS {
                MATCH (word)<-[:ORIGIN]-(child:Word {simulation_id: $run_id})-[:BELONGS_TO]->(:Language {simulation_id: $run_id, id: $node_id})  # noqa: E501
                WHERE $year IS NULL OR child.year <= $year
              }
            OPTIONAL MATCH path = (word)-[:ORIGIN*]->(proto:Word {simulation_id: $run_id})
            WHERE NOT (proto)-[:ORIGIN]->()
            RETURN word.id AS id, word.concept_id AS concept_id, word.ipa AS to,
                   proto.ipa AS from, word.ipa_prosodic AS to_prosodic,
                   proto.ipa_prosodic AS from_prosodic, word.polysemy AS polysemy,
                   word.stress_index AS stress_index, word.long_nuclei AS long_nuclei,
                   word.morpheme_boundaries AS morpheme_boundaries,
                   word.paradigm AS paradigm,
                   word.grammatical_features_json AS grammatical_features_json,
                   word.frequency AS frequency, word.is_grammatical AS is_grammatical,
                   word.active AS active, word.origin_type AS origin_type
        """
        with self.driver.session() as session:
            result = []
            for record in session.run(query, run_id=run_id, node_id=node_id, year=year):
                item = dict(record)
                item["grammatical_features"] = json.loads(
                    item.pop("grammatical_features_json") or "{}"
                )
                result.append(item)
            return result

    def isogloss(self, run_id: str, concept_id: str, year: int | None = None) -> dict[str, str]:
        # Výběr aktivní varianty pro každý jazyk je stejný jako v `language`.
        query = """
            MATCH (word:Word {simulation_id: $run_id, concept_id: $concept_id})-[:BELONGS_TO]->(language:Language {simulation_id: $run_id})  # noqa: E501
            WHERE ($year IS NULL OR word.year <= $year)
              AND coalesce(word.active, true)
              AND NOT EXISTS {
                MATCH (word)<-[:ORIGIN]-(child:Word {simulation_id: $run_id})-[:BELONGS_TO]->(language)  # noqa: E501
                WHERE $year IS NULL OR child.year <= $year
              }
            RETURN language.id AS language_id, word.ipa AS ipa
        """
        with self.driver.session() as session:
            return {
                record["language_id"]: record["ipa"]
                for record in session.run(query, run_id=run_id, concept_id=concept_id, year=year)
            }

    def word_trace(self, run_id: str, word_id: str) -> list[dict[str, Any]]:
        query = """
            MATCH path = (word:Word {simulation_id: $run_id, id: $word_id})-[:ORIGIN*0..]->(proto:Word {simulation_id: $run_id})  # noqa: E501
            WHERE NOT (proto)-[:ORIGIN]->()
            RETURN nodes(path) AS nodes, relationships(path) AS relationships
        """
        with self.driver.session() as session:
            record = session.run(query, run_id=run_id, word_id=word_id).single()
        if not record:
            return []
        nodes = list(reversed(record["nodes"]))
        relationships = list(reversed(record["relationships"]))
        trace = []
        for index, node in enumerate(nodes):
            step = _trace_step(node)
            if index == 0:
                step["note"] = "výchozí tvar"
            else:
                relation = relationships[index - 1]
                step["rule_name"] = relation.get("rule")
                step["type"] = relation["type"]
            trace.append(step)
        return trace

    def export(self, run_id: str) -> dict[str, Any]:
        with self.driver.session() as session:
            simulation = session.run(
                "MATCH (simulation:Simulation {id: $run_id}) RETURN simulation.events_json AS events_json",  # noqa: E501
                run_id=run_id,
            ).single()
            nodes = [
                dict(record)
                for record in session.run(
                    (
                        "MATCH (word:Word {simulation_id: $run_id})-[:BELONGS_TO]->(language:Language {simulation_id: $run_id}) "  # noqa: E501
                        "RETURN word.id AS id, word.concept_id AS concept_id, word.ipa AS ipa, word.ipa_prosodic AS ipa_prosodic, "  # noqa: E501
                        "word.year AS year, word.polysemy AS polysemy, word.stress_index AS stress_index, word.long_nuclei AS long_nuclei, "  # noqa: E501
                        "word.morpheme_boundaries AS morpheme_boundaries, word.active AS active, word.frequency AS frequency, "  # noqa: E501
                        "word.paradigm AS paradigm, word.grammatical_features_json AS grammatical_features_json, "  # noqa: E501
                        "word.is_grammatical AS is_grammatical, word.origin_type AS origin_type, language.id AS language_id"  # noqa: E501
                    ),
                    run_id=run_id,
                )
            ]
            edges = [
                dict(record)
                for record in session.run(
                    (
                        "MATCH (target:Word {simulation_id: $run_id})-[origin:ORIGIN]->(source:Word {simulation_id: $run_id}) "  # noqa: E501
                        "RETURN target.id AS target_id, source.id AS source_id, origin.type AS type, origin.rule AS rule"  # noqa: E501
                    ),
                    run_id=run_id,
                )
            ]
        for node in nodes:
            node["grammatical_features"] = json.loads(node.pop("grammatical_features_json") or "{}")
        events = json.loads(simulation["events_json"] or "[]") if simulation else []
        return {
            "schema_version": 2,
            "run_id": run_id,
            "nodes": nodes,
            "edges": edges,
            "events": events,
        }


_store: GenealogyStore | None = None


def get_genealogy_store() -> GenealogyStore:
    """Vrátí adaptér z konfigurace; bez konfigurace vždy funguje souborový."""
    global _store
    if _store is None:
        kind = os.environ.get("CEE_GENEALOGY_STORE", "file").lower()
        if kind == "neo4j":
            uri = os.environ.get("CEE_NEO4J_URI")
            if not uri:
                raise RuntimeError("CEE_NEO4J_URI chybí pro CEE_GENEALOGY_STORE=neo4j.")
            _store = Neo4jGenealogyStore(
                uri,
                os.environ.get("CEE_NEO4J_USERNAME", "neo4j"),
                os.environ.get("CEE_NEO4J_PASSWORD", ""),
            )
        elif kind == "file":
            _store = FileGenealogyStore()
        else:
            raise RuntimeError("CEE_GENEALOGY_STORE musí být 'file' nebo 'neo4j'.")
    return _store
