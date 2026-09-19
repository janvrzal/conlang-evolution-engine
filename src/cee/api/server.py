"""
Lokální HTTP API pro grafické rozhraní.

Vlastní logika simulace žije v `cee.pipeline` — tenhle modul jen překládá
HTTP požadavky na volání služby a zpátky na JSON.
"""

import os
import subprocess
import uuid
from dataclasses import asdict
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from cee import __version__, projects
from cee.api.ports import API_REVISION, DEFAULT_PORT, ENGINE_SIGNATURE
from cee.api.runs import router as run_router
from cee.engine.empirical import phoible_status, update_phoible_cache
from cee.engine.parser import YamlParser
from cee.engine.topology import ContactEdge, EvolutionGraph, HistoricalEventSpec, Polity, TradeRoute, VerticalEdge
from cee.metrics.schema_profiles import available_schema_profiles
from cee.project_schema import validate_simulation_topology
from cee.pipeline import (
    DEFAULT_SEED,
    SimulationConfig,
    build_branch_views,
    load_lexicon_from_records,
    resolve_semantics_path,
    run_simulation,
)
from cee.semantics.graph import SemanticGraph
from cee.storage.genealogy import get_genealogy_store
from cee.storage.legacy_neo4j import import_legacy_graph

app = FastAPI(title="CEE Engine API")
app.include_router(run_router)

# Vite dev server si při obsazeném 5173 vezme 5174, 5175, ... — proto povolujeme
# jakýkoli lokální origin, ne pevný seznam. Server je určený jen pro localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    # `engine` je podpis, podle kterého frontend při hledání portu pozná CEE
    # od jiné lokální aplikace, která taky odpovídá na /api/health.
    return {
        "status": "ok",
        "engine": ENGINE_SIGNATURE,
        "version": __version__,
        "api_revision": API_REVISION,
    }


@app.get("/")
def read_root():
    return {"message": "API běží. Frontend spusťte přes 'npm run dev' ve složce 'ui'."}


@app.get("/api/schema-profiles")
def list_schema_profiles():
    """Vestavěné profily, které UI může bezpečně nabídnout uživateli."""
    return [asdict(profile) for profile in available_schema_profiles()]


@app.get("/api/phonology/status")
def get_phonology_status():
    """Stav volitelné lokální PHOIBLE cache; nikdy nic nestahuje."""
    return phoible_status()


@app.post("/api/phonology/update-data")
def update_phonology_data():
    """Výslovně spuštěná jediná síťová operace fonologické vrstvy."""
    try:
        return update_phoible_cache()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise HTTPException(status_code=502, detail=f"Aktualizace PHOIBLE selhala: {exc}") from exc


class SimulateRequest(BaseModel):
    topology: str = "scenario_split.yaml"
    proto_csv: str = "fantasy_v1.csv"
    preset: str = "src/cee/data/presets/fantasy_preset.yaml"
    #: Prázdné = engine sám zkusí skutečný CLICS4+DatSemShift graf, a když
    #: chybí (čerstvý klon, CI), spadne na zabalený YAML mock — viz
    #: `cee.pipeline.resolve_semantics_path`.
    semantics: Optional[str] = None
    seed: int = DEFAULT_SEED


class ProtolangRequest(BaseModel):
    consonants: str = "p t k m n s l r"
    vowels: str = "a e i o u"
    syllable_structure: str = "(C)V(C)"
    #: Kurátorované jádro je výchozí; tisíce položek z CLICS4 jsou vědomá
    #: rozšiřující volba, ne nečekaná cena za založení projektu.
    vocabulary_profile: Literal["core", "full"] = "core"
    #: Světově specifické významy, které se přidají k jádru daného projektu.
    custom_concepts: list[str] = []


class DynamicSimulateRequest(BaseModel):
    """Topologie sestavená v UI: uzly jako mapa id -> konfigurace, hrany jako seznam."""

    topology_data: dict
    proto_lexicon: list
    preset: str = "src/cee/data/presets/fantasy_preset.yaml"
    #: Prázdné = engine sám zkusí skutečný CLICS4+DatSemShift graf, a když
    #: chybí (čerstvý klon, CI), spadne na zabalený YAML mock — viz
    #: `cee.pipeline.resolve_semantics_path`.
    semantics: Optional[str] = None
    seed: int = DEFAULT_SEED
    #: Časová hloubka; slouží i jako výchozí rok kontaktu bez zadaného roku.
    years: int = 1000
    #: UI používá existující lokální cache; její absence je bezpečný fallback.
    empirical_phonology: bool = True
    schema_profile_id: str = "heuristic-default"
    #: Prázdné ID založí nový běh; opakování se stejným ID nahradí jen jeho data.
    run_id: Optional[str] = None
    #: Jednoduché ovladače worldbuildera, uložené spolu s projektem.
    calibration: dict = {}


def _config(req, preset_path: str) -> SimulationConfig:
    preset = YamlParser.parse_preset(preset_path) if preset_path else None
    calibration = getattr(req, "calibration", {}) or {}
    return SimulationConfig(
        preset=preset,
        semantics_path=req.semantics or None,
        seed=req.seed,
        years=getattr(req, "years", None),
        use_empirical_phonology=getattr(req, "empirical_phonology", False),
        schema_profile_id=getattr(req, "schema_profile_id", "heuristic-default"),
        macro_overrides={
            key: float(calibration[key])
            for key in ("sound_changes_per_millennium", "change_spread_years", "isolation")
            if key in calibration
        },
        lexical_overrides={
            key: float(calibration[key])
            for key in ("replacement_rate", "loss_rate", "homophony_resolution_rate")
            if key in calibration
        },
    )


@app.post("/api/protolang/generate")
def generate_protolang(req: ProtolangRequest):
    from cee.data.core_vocabulary import core_concepts
    from cee.engine.protolang import ProtolangGenerator

    generator = ProtolangGenerator()
    if req.vocabulary_profile == "full":
        graph_path = resolve_semantics_path(None)
        graph = SemanticGraph(graph_path) if graph_path else None
        concepts = graph.lexical_entries() if graph else core_concepts()
        # Vlastní významy nesmí plný korpus zahodit; deduplikace chrání i
        # případ, kdy už je shodný koncept součástí CLICS4.
        known = {str(concept.get("id", "")).lower() for concept in concepts}
        concepts.extend(
            concept
            for concept in core_concepts(req.custom_concepts)
            if str(concept["id"]).lower() not in known
        )
        source = (
            "CLICS4 + DatSemShift (plný korpus)"
            if graph_path and graph_path.endswith(".graphml")
            else "základní slovní zásoba (plný korpus není lokálně dostupný)"
        )
    else:
        concepts = core_concepts(req.custom_concepts)
        source = "Swadeshovo jádro + rozšířené koncepty"
    words = generator.generate_lexicon(req.consonants, req.vowels, req.syllable_structure, concepts)
    return {
        "status": "success",
        "words": words,
        "concept_count": sum(1 + len(word["polysemy"]) for word in words),
        "source": source,
    }


# --- Projekty (persistence rozdělané práce) ----------------------------------


class ProjectPayload(BaseModel):
    name: str = "Nový projekt"
    data: dict = {}


def _project_or_404(project_id: str):
    try:
        return projects.load(project_id)
    except projects.InvalidProjectId as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except projects.ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except projects.ProjectError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/projects")
def list_projects():
    return {"status": "success", "projects": projects.list_projects()}


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    return {"status": "success", "project": _project_or_404(project_id).as_dict()}


@app.put("/api/projects/{project_id}")
def put_project(project_id: str, payload: ProjectPayload):
    """Uloží (nebo založí) projekt. Frontend sem posílá celý svůj stav."""
    try:
        project = projects.load_or_create(project_id, payload.name)
    except projects.InvalidProjectId as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    project.name = payload.name
    project.data = payload.data
    try:
        projects.save(project)
    except projects.ProjectError as exc:
        # Neplatná reference je chyba vstupu uživatele, ne selhání serveru.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "success", "project": project.as_dict()}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    project = _project_or_404(project_id)
    run_id = project.data.get("simulationRunId")
    if isinstance(run_id, str):
        get_genealogy_store().delete(run_id)
    projects.delete(project_id)
    return {"status": "success"}


@app.post("/api/projects/{project_id}/import-legacy-neo4j")
def import_legacy_neo4j(project_id: str):
    """Výslovně přenese poslední starý globální graf do nového běhu projektu."""
    project = _project_or_404(project_id)
    run_id = uuid.uuid4().hex
    builder = import_legacy_graph(
        os.environ.get("CEE_LEGACY_NEO4J_URI", "bolt://localhost:7687"),
        os.environ.get("CEE_LEGACY_NEO4J_USERNAME", "neo4j"),
        os.environ.get("CEE_LEGACY_NEO4J_PASSWORD", "password"),
    )
    store = get_genealogy_store()
    store.save(run_id, builder)
    project.data["simulationRunId"] = run_id
    project.data["simulationRunAt"] = project.updated_at
    projects.save(project)
    return {"status": "success", "run_id": run_id, "words": len(builder.nodes)}


@app.post("/api/simulate_dynamic")
def run_dynamic_simulation(req: DynamicSimulateRequest):
    """Spustí simulaci nad celou časovou osou sestavenou v grafovém editoru."""
    from cee.pipeline import get_feature_mapper

    try:
        # Simulátor má stejnou bránu jako persistentní projekt. Transportní
        # aliasy se zde jen ověří a přeloží do V3, nikdy se neposílají dál
        # jako nestrukturovaný vstup bez kontroly.
        validate_simulation_topology(req.topology_data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Neplatná topologie simulace: {exc}") from exc

    mapper = get_feature_mapper()
    lexicon = load_lexicon_from_records(req.proto_lexicon, mapper)

    graph = EvolutionGraph()
    for raw in req.topology_data.get("polities", []):
        if isinstance(raw, dict) and raw.get("id"):
            graph.polities[str(raw["id"])] = Polity(
                id=str(raw["id"]), name=str(raw.get("name", raw["id"])),
                territory=list(raw.get("territory", [])), institutions=dict(raw.get("institutions", {})),
                language_ids=[str(value) for value in raw.get("languageIds", [])],
            )
    for raw in req.topology_data.get("tradeRoutes", []):
        if isinstance(raw, dict) and raw.get("id"):
            end_year = raw.get("endYear")
            graph.trade_routes.append(TradeRoute(
                str(raw["id"]), str(raw.get("kind", "land")),
                float(raw.get("intensity", 0.5)),
                [str(value) for value in raw.get("languageIds", [])],
                int(raw.get("startYear", 0)),
                int(end_year) if end_year not in (None, "") else None,
                [
                    {"x": float(point["x"]), "y": float(point["y"])}
                    for point in raw.get("waypoints", [])
                    if isinstance(point, dict) and "x" in point and "y" in point
                ],
            ))
    for raw in req.topology_data.get("historicalEvents", []):
        if isinstance(raw, dict) and raw.get("id"):
            effects = dict(raw.get("effects", {}))
            if raw.get("kind") == "rename":
                effects["name_change"] = {
                    "endonym": str(raw.get("endonym", "")).strip(),
                    "exonym": str(raw.get("exonym", "")).strip(),
                    "reason": "political_event",
                }
            graph.historical_events.append(HistoricalEventSpec(str(raw["id"]), str(raw.get("kind", "migration")), int(raw.get("startYear", 0)), int(raw.get("duration", 0)), [str(value) for value in raw.get("targetLanguageIds", [])], raw.get("targetPolityId"), effects))

    snapshots = req.topology_data.get("snapshots")
    if snapshots:
        # Snímky jsou seřazené podle času. Nejde o čtyři alternativní grafy:
        # každý je stav světa po předchozí epoše. Dědičnost proto bereme jen
        # z okamžiku, kdy je hrana ještě přímá, zatímco kontakt provádíme v
        # každé epoše, v níž je na mapě vidět.
        vertical_pairs = set()
        for snapshot in sorted(snapshots, key=lambda item: int(item["year"])):
            epoch_year = int(snapshot["year"])
            for node in snapshot.get("nodes", []):
                node_id = node["id"]
                data = node.get("data", {})
                if node_id not in graph.node_configs:
                    graph.node_configs[node_id] = {
                        **data,
                        "map": data,
                        "position": dict(node.get("position", {})),
                    }

            for edge in snapshot.get("edges", []):
                if edge.get("type") == "contact":
                    data = edge.get("data", {})
                    direction = data.get("direction", "both")
                    source_id, target_id = edge["source"], edge["target"]
                    if direction == "ba":
                        source_id, target_id = target_id, source_id
                    graph.contact_edges.append(
                        ContactEdge(
                            year=epoch_year,
                            source_id=source_id,
                            target_id=target_id,
                            volume=max(
                                1,
                                round(
                                    int(data.get("volume", 5))
                                    * float(data.get("intensity", 50))
                                    / 50
                                ),
                            ),
                            mutual=direction == "both" or bool(data.get("mutual", False)),
                            domain=data.get("contactType", "neighborhood"),
                            prestige=float(data.get("prestige", 1.0)),
                            calque_rate=float(data.get("calqueRate", 0.0)),
                            adapt=bool(data.get("adapt", True)),
                            layer=str(data.get("layer", "folk")),
                            transfer_morphology=bool(data.get("transferMorphology", False)),
                            resolve_homophony=bool(data.get("resolveHomophony", False)),
                            construction_ids=[str(value) for value in data.get("constructionIds", [])],
                        )
                    )
                else:
                    pair = (edge["source"], edge["target"])
                    if pair not in vertical_pairs:
                        vertical_pairs.add(pair)
                        graph.vertical_edges.append(
                            VerticalEdge(
                                parent_id=edge["source"], child_id=edge["target"], rules=[]
                            )
                        )
    else:
        # Zpětná kompatibilita se starším klientem, který ještě posílal jen
        # jeden statický snímek.
        graph.node_configs = {
            node_id: cfg if "map" in cfg else {**cfg, "map": cfg}
            for node_id, cfg in req.topology_data.get("nodes", {}).items()
        }
        for edge in req.topology_data.get("edges", []):
            if edge.get("kind") == "contact":
                graph.contact_edges.append(
                    ContactEdge(
                        year=int(edge.get("year", req.years // 2)),
                        source_id=edge["source"],
                        target_id=edge["target"],
                        volume=int(edge.get("volume", 5)),
                        mutual=bool(edge.get("mutual", True)),
                        domain=edge.get("domain", "neighborhood"),
                        prestige=float(edge.get("prestige", 1.0)),
                        calque_rate=float(edge.get("calque_rate", 0.0)),
                        adapt=bool(edge.get("adapt", False)),
                        layer=str(edge.get("layer", "folk")),
                        transfer_morphology=bool(edge.get("transfer_morphology", False)),
                        resolve_homophony=bool(edge.get("resolve_homophony", False)),
                        construction_ids=[str(value) for value in edge.get("construction_ids", [])],
                    )
                )
            else:
                graph.vertical_edges.append(
                    VerticalEdge(parent_id=edge["source"], child_id=edge["target"], rules=[])
                )

    root_candidates = [node_id for node_id, cfg in graph.node_configs.items() if cfg.get("isProto")]
    root_id = (
        root_candidates[0]
        if root_candidates
        else "lang-1" if "lang-1" in graph.node_configs else "proto"
    )

    from cee.engine.graph_builder import GraphBuilder

    builder = GraphBuilder()

    cfg = _config(req, req.preset)
    cfg.root_id = root_id
    # Kořenový uzel je v UI skutečný jazyk na časové ose, ne jen statický
    # zdroj pro větvení. Musí tedy dostat vlastní historii zvukových změn.
    cfg.evolve_root = True

    final_states = run_simulation(lexicon, graph, mapper, cfg, builder)
    branches = build_branch_views(final_states, mapper, [word["id"] for word in req.proto_lexicon])
    sound_events = [event for event in builder.events if event.get("kind") == "sound_change"]
    innovation_events: dict[str, dict] = {}
    for index, event in enumerate(sound_events):
        # Fáze jedné šířící se změny nejsou nové inovace. Ruční pravidla,
        # která change_id nemají, zůstávají samostatné historické události.
        change_id = str(
            event.get(
                "change_id",
                f"manual:{event.get('language_id')}:{event.get('year')}:{event.get('rule')}:{index}",
            )
        )
        innovation_events.setdefault(change_id, event)
    schemas: dict[str, int] = {}
    environments: dict[str, int] = {"unclassified": len(innovation_events)}
    for event in innovation_events.values():
        schema_id = str(event.get("schema_id", "manual"))
        schemas[schema_id] = schemas.get(schema_id, 0) + 1
    builder.artifacts = {
        "grammars": {node_id: branch.grammar_md for node_id, branch in branches.items()},
        "metrics": {
            "sound_changes": len(innovation_events),
            "changes_per_millennium": len(innovation_events) * 1000 / max(1, req.years),
            "sound_change_phases": len(sound_events),
            "schemas": schemas,
            "environments": environments,
            "deleted_segments": sum(int(event.get("deleted_segments", 0) or 0) for event in sound_events),
        },
    }
    run_id = req.run_id or uuid.uuid4().hex
    store = get_genealogy_store()
    store.save(run_id, builder)
    return {
        "status": "success",
        "message": "Simulace byla uložena.",
        "run_id": run_id,
        "storage": store.backend_name,
    }


def start_server(port: int = DEFAULT_PORT, reload: bool = False):
    import uvicorn

    # reload=True spouští vlastní reloader proces; ten se pere s vláknem, které
    # `cee ui` používá k otevření prohlížeče, proto je ve výchozím stavu vypnutý.
    uvicorn.run("cee.api.server:app", host="127.0.0.1", port=port, reload=reload)
