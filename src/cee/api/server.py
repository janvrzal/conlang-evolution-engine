"""
Lokální HTTP API pro grafické rozhraní.

Vlastní logika simulace žije v `cee.pipeline` — tenhle modul jen překládá
HTTP požadavky na volání služby a zpátky na JSON.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from pydantic import BaseModel

from cee import __version__
from cee.api.ports import API_REVISION, DEFAULT_PORT, ENGINE_SIGNATURE
from cee.engine.parser import YamlParser
from cee.engine.phonology import FeatureMapper
from cee.engine.topology import ContactEdge, EvolutionGraph, VerticalEdge
from cee import projects
from cee.metrics.retention import LexicalRetention
from cee.pipeline import (
    DEFAULT_SEED,
    LineageConfig,
    SimulationConfig,
    evolve_lineage,
    lineage_payload,
    build_branch_views,
    load_lexicon_from_csv,
    load_lexicon_from_records,
    run_simulation,
    topology_payload,
)

app = FastAPI(title="CEE Engine API")

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
    semantics: str = "src/cee/data/semantics_mock.yaml"
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
    semantics: str = "src/cee/data/semantics_mock.yaml"
    seed: int = DEFAULT_SEED
    #: Časová hloubka; slouží i jako výchozí rok kontaktu bez zadaného roku.
    years: int = 1000


def _config(req, preset_path: str) -> SimulationConfig:
    preset = YamlParser.parse_preset(preset_path) if preset_path else None
    return SimulationConfig(
        preset=preset,
        semantics_path=req.semantics or None,
        seed=req.seed,
        years=getattr(req, "years", None),
    )


def _respond(states, graph, mapper, diagnostic):
    branches = build_branch_views(states, mapper, diagnostic)
    return {
        "status": "success",
        "branches": {node_id: view.as_dict() for node_id, view in branches.items()},
        "topology": topology_payload(graph),
    }


@app.post("/api/protolang/generate")
def generate_protolang(req: ProtolangRequest):
    from cee.engine.protolang import ProtolangGenerator

    generator = ProtolangGenerator()
    words = generator.generate_lexicon(req.consonants, req.vowels, req.syllable_structure)
    return {"status": "success", "words": words}


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
    _project_or_404(project_id)
    projects.delete(project_id)
    return {"status": "success"}


class EvolveRequest(BaseModel):
    """Vývoj jednoho jazyka v čase — bez větvení a bez kontaktu."""

    proto_lexicon: list
    years: int = 1000
    epochs: int = 5
    rules_per_epoch: int = 2
    biome: Optional[str] = None
    preset: str = "src/cee/data/presets/fantasy_preset.yaml"
    seed: int = DEFAULT_SEED
    node_id: str = "proto"


@app.post("/api/evolve")
def evolve(req: EvolveRequest):
    """
    Nechá protojazyk vyvíjet se sám a vrátí celý průběh: epochy, seznam
    zvukových změn i derivaci každého slova.
    """
    mapper = FeatureMapper()
    lexicon = load_lexicon_from_records(req.proto_lexicon, mapper)
    diagnostic = LexicalRetention.diagnostic_from(lexicon)

    config = LineageConfig(
        years=req.years,
        epochs=req.epochs,
        rules_per_epoch=req.rules_per_epoch,
        node_id=req.node_id,
        seed=req.seed,
        preset=YamlParser.parse_preset(req.preset) if req.preset else None,
        biome=req.biome,
    )

    state, history = evolve_lineage(lexicon, mapper, config)
    return lineage_payload(state, history, mapper, diagnostic)


@app.post("/api/simulate")
def run_file_simulation(req: SimulateRequest):
    """Spustí simulaci nad topologií a lexikonem ze souborů na disku."""
    mapper = FeatureMapper()
    lexicon = load_lexicon_from_csv(req.proto_csv, mapper)
    graph = YamlParser.parse_topology(req.topology)

    diagnostic = LexicalRetention.diagnostic_from(lexicon)
    states = run_simulation(lexicon, graph, mapper, _config(req, req.preset))
    return _respond(states, graph, mapper, diagnostic)


@app.post("/api/simulate_dynamic")
def run_dynamic_simulation(req: DynamicSimulateRequest):
    """Spustí simulaci nad topologií, kterou uživatel sestavil v grafovém editoru."""
    mapper = FeatureMapper()
    lexicon = load_lexicon_from_records(req.proto_lexicon, mapper)

    graph = EvolutionGraph()

    # UI posílá konfiguraci uzlu naplocho ({"biome": "hory"}), zatímco topologie
    # z YAML má tytéž hodnoty pod klíčem `map` — a odtud je čte simulátor.
    # Bez normalizace by se biom nikdy nedostal ke generátoru a všechny větve
    # by vyšly stejně.
    graph.node_configs = {
        node_id: cfg if "map" in cfg else {**cfg, "map": cfg}
        for node_id, cfg in req.topology_data.get("nodes", {}).items()
    }

    # Hrana z editoru je buď dědičnost (rodič -> potomek), nebo kontakt
    # (sousedé, kteří se navzájem ovlivňují). Bez rozlišení se všechno bralo
    # jako dědičnost a propojené jazyky na sebe nikdy nepůsobily.
    for edge in req.topology_data.get("edges", []):
        if edge.get("kind") == "contact":
            graph.contact_edges.append(
                ContactEdge(
                    year=int(edge.get("year", req.years // 2)),
                    source_id=edge["source"],
                    target_id=edge["target"],
                    volume=int(edge.get("volume", 5)),
                    mutual=bool(edge.get("mutual", True)),
                )
            )
        else:
            graph.vertical_edges.append(
                VerticalEdge(parent_id=edge["source"], child_id=edge["target"], rules=[])
            )

    diagnostic = LexicalRetention.diagnostic_from(lexicon)
    states = run_simulation(lexicon, graph, mapper, _config(req, req.preset))
    return _respond(states, graph, mapper, diagnostic)


def start_server(port: int = DEFAULT_PORT, reload: bool = False):
    import uvicorn

    # reload=True spouští vlastní reloader proces; ten se pere s vláknem, které
    # `cee ui` používá k otevření prohlížeče, proto je ve výchozím stavu vypnutý.
    uvicorn.run("cee.api.server:app", host="127.0.0.1", port=port, reload=reload)
