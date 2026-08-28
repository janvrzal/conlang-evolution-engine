from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from cee.api.ports import DEFAULT_PORT, ENGINE_SIGNATURE

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

# Pokud by existovala složka build ze SvelteKitu, můžeme ji mountnout
# app.mount("/_app", StaticFiles(directory="ui/build/_app"), name="svelte_app")

@app.get("/api/health")
def health_check():
    # `engine` je podpis, podle kterého frontend při hledání portu pozná CEE
    # od jiné lokální aplikace, která taky odpovídá na /api/health.
    return {"status": "ok", "engine": ENGINE_SIGNATURE}

@app.get("/")
def read_root():
    return {"message": "API běží. Frontend spusťte přes 'npm run dev' ve složce 'ui'."}

class SimulateRequest(BaseModel):
    topology: str = "scenario_split.yaml"
    proto_csv: str = "fantasy_v1.csv"
    preset: str = "src/cee/data/presets/fantasy_preset.yaml"
    semantics: str = "src/cee/data/semantics_mock.yaml"

@app.post("/api/simulate")
def run_simulation(req: SimulateRequest):
    """
    Spustí evoluční engine s danou topologií a vrátí výsledek jako JSON.
    V reálné aplikaci by cesty byly nahrávané soubory nebo JSON stringy z FE, 
    ale prozatím natvrdo použijeme existující ukázkové soubory na disku.
    """
    from cee.engine.phonology import FeatureMapper
    from cee.engine.parser import YamlParser
    from cee.core.models import State, Inventory
    from cee.engine.semantics import SemanticEvaluator
    from cee.semantics.graph import SemanticGraph
    from cee.engine.simulator import EvolutionSimulator
    
    # 1. Načtení dat
    mapper = FeatureMapper()
    
    # Načtení proto lexikonu 
    from cee.cli.main import load_csv_lexicon
    lexicon = load_csv_lexicon(req.proto_csv, mapper)
    
    # Načtení topologie a presetu
    graph = YamlParser.parse_topology(req.topology)
    preset_data = YamlParser.parse_preset(req.preset) if req.preset else None
    
    # 2. Inicializace sémantiky
    semantic_evaluator = None
    if req.semantics:
        graph_sem = SemanticGraph(req.semantics)
        semantic_evaluator = SemanticEvaluator(graph_sem, shift_prob=0.3, forget_prob=0.05)
        
    # 3. Spuštění simulace
    root_state = State(node_id="proto", year=0, inventory=Inventory(), lexicon=lexicon)
    simulator = EvolutionSimulator(graph, mapper, preset=preset_data, semantic_evaluator=semantic_evaluator)
    
    final_states = simulator.simulate(root_state)
    
    # 4. Formátování výsledku pro frontend
    result_data = {}
    for branch_id, state in final_states.items():
        words = []
        for word in state.lexicon.words:
            words.append({
                "id": word.concept_id,
                "ipa": mapper.render_word(word),
                "polysemy": list(word.polysemy)
            })
            
        grammar_md = f"# Gramatika jazyka {branch_id}\n\n"
        grammar_md += f"## Fonologie\nInventář hlásek: {', '.join(sorted(list(state.inventory.segments)))}\n\n"
        grammar_md += f"## Morfologie\n- Strategie odvozování: {state.affixation_strategy}\n"
        grammar_md += f"- Tvorba složenin: head-{state.compound_head}\n"
        
        result_data[branch_id] = {
            "year": state.year,
            "words": words,
            "grammar_md": grammar_md
        }
        
    topology_data = {
        "nodes": [{"id": node_id} for node_id in graph.node_configs.keys()],
        "edges": [{"source": edge.parent_id, "target": edge.child_id} for edge in graph.vertical_edges]
    }
        
    return {
        "status": "success",
        "branches": result_data,
        "topology": topology_data
    }

def start_server(port: int = DEFAULT_PORT, reload: bool = False):
    import uvicorn

    # reload=True spouští vlastní reloader proces; ten se pere s vláknem, které
    # `cee ui` používá k otevření prohlížeče, proto je ve výchozím stavu vypnutý.
    uvicorn.run("cee.api.server:app", host="127.0.0.1", port=port, reload=reload)
