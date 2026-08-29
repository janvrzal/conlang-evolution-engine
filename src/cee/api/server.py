"""
Lokální HTTP API pro grafické rozhraní.

Vlastní logika simulace žije v `cee.pipeline` — tenhle modul jen překládá
HTTP požadavky na volání služby a zpátky na JSON.
"""
import uuid
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from pydantic import BaseModel

from cee import __version__
from cee.api.ports import API_REVISION, DEFAULT_PORT, ENGINE_SIGNATURE
from cee.engine.parser import YamlParser
from cee.engine.topology import ContactEdge, EvolutionGraph, VerticalEdge
from cee import projects
from cee.pipeline import (
    DEFAULT_SEED,
    SimulationConfig,
    load_lexicon_from_records,
    resolve_semantics_path,
    run_simulation,
)
from cee.semantics.graph import SemanticGraph
from cee.storage.genealogy import get_genealogy_store
from cee.storage.legacy_neo4j import import_legacy_graph
from cee.api.runs import router as run_router

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
    #: Prázdné ID založí nový běh; opakování se stejným ID nahradí jen jeho data.
    run_id: Optional[str] = None


def _config(req, preset_path: str) -> SimulationConfig:
    preset = YamlParser.parse_preset(preset_path) if preset_path else None
    return SimulationConfig(
        preset=preset,
        semantics_path=req.semantics or None,
        seed=req.seed,
        years=getattr(req, "years", None),
    )


@app.post("/api/protolang/generate")
def generate_protolang(req: ProtolangRequest):
    from cee.engine.protolang import ProtolangGenerator

    generator = ProtolangGenerator()
    graph_path = resolve_semantics_path(None)
    graph = SemanticGraph(graph_path) if graph_path else None
    concepts = graph.lexical_entries() if graph else None
    words = generator.generate_lexicon(req.consonants, req.vowels, req.syllable_structure, concepts)
    return {
        "status": "success",
        "words": words,
        "concept_count": sum(1 + len(word["polysemy"]) for word in words),
        "source": "CLICS4 + DatSemShift" if graph_path and graph_path.endswith(".graphml") else "zabalený sémantický mock",
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
    projects.save(project)
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
    mapper = get_feature_mapper()
    lexicon = load_lexicon_from_records(req.proto_lexicon, mapper)

    graph = EvolutionGraph()

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
                    graph.node_configs[node_id] = {**data, "map": data}

            for edge in snapshot.get("edges", []):
                if edge.get("type") == "contact":
                    data = edge.get("data", {})
                    direction = data.get("direction", "both")
                    source_id, target_id = edge["source"], edge["target"]
                    if direction == "ba":
                        source_id, target_id = target_id, source_id
                    graph.contact_edges.append(ContactEdge(
                        year=epoch_year,
                        source_id=source_id,
                        target_id=target_id,
                        volume=max(1, round(int(data.get("volume", 5)) * float(data.get("intensity", 50)) / 50)),
                        mutual=direction == "both" or bool(data.get("mutual", False)),
                        domain=data.get("contactType", "neighborhood"),
                        prestige=float(data.get("prestige", 1.0)),
                        calque_rate=float(data.get("calqueRate", 0.0)),
                        adapt=bool(data.get("adapt", True)),
                    ))
                else:
                    pair = (edge["source"], edge["target"])
                    if pair not in vertical_pairs:
                        vertical_pairs.add(pair)
                        graph.vertical_edges.append(VerticalEdge(
                            parent_id=edge["source"], child_id=edge["target"], rules=[]
                        ))
    else:
        # Zpětná kompatibilita se starším klientem, který ještě posílal jen
        # jeden statický snímek.
        graph.node_configs = {
            node_id: cfg if "map" in cfg else {**cfg, "map": cfg}
            for node_id, cfg in req.topology_data.get("nodes", {}).items()
        }
        for edge in req.topology_data.get("edges", []):
            if edge.get("kind") == "contact":
                graph.contact_edges.append(ContactEdge(
                    year=int(edge.get("year", req.years // 2)),
                    source_id=edge["source"], target_id=edge["target"],
                    volume=int(edge.get("volume", 5)), mutual=bool(edge.get("mutual", True)),
                    domain=edge.get("domain", "neighborhood"),
                    prestige=float(edge.get("prestige", 1.0)),
                    calque_rate=float(edge.get("calque_rate", 0.0)),
                    adapt=bool(edge.get("adapt", False)),
                ))
            else:
                graph.vertical_edges.append(VerticalEdge(
                    parent_id=edge["source"], child_id=edge["target"], rules=[]
                ))

    root_candidates = [node_id for node_id, cfg in graph.node_configs.items() if cfg.get("isProto")]
    root_id = root_candidates[0] if root_candidates else "lang-1" if "lang-1" in graph.node_configs else "proto"

    from cee.engine.graph_builder import GraphBuilder
    builder = GraphBuilder()

    cfg = _config(req, req.preset)
    cfg.root_id = root_id
    # Kořenový uzel je v UI skutečný jazyk na časové ose, ne jen statický
    # zdroj pro větvení. Musí tedy dostat vlastní historii zvukových změn.
    cfg.evolve_root = True

    run_simulation(lexicon, graph, mapper, cfg, builder)
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
