import csv
import subprocess
import typer
import datetime
import threading
import time
import warnings
import webbrowser
from pathlib import Path
from cee.engine.phonology import FeatureMapper
from cee.engine.parser import YamlParser
from cee.engine.fold import DerivationFold
from cee.core.models import Lexicon, State, Inventory
from cee.metrics.validation import ValidationMetric
from cee.semantics.graph import SemanticGraph
from cee.engine.semantics import SemanticEvaluator
from cee.metrics.retention import LexicalRetention
from cee.pipeline import (
    LineageConfig,
    SimulationConfig,
    
    build_branch_views,
    load_lexicon_from_csv,
    run_simulation,
)
from cee.engine.empirical import build_empirical_cache, default_paths as default_empirical_paths

app = typer.Typer(help="Conlang Evolution Engine CLI", no_args_is_help=True)
phonology_app = typer.Typer(help="Správa volitelných empirických fonologických dat.")
app.add_typer(phonology_app, name="phonology")

INDEX_DIACHRONICA_REDUX_URL = "https://github.com/bradrn/index-diachronica-redux.git"
PHOIBLE_REPOSITORY_URL = "https://github.com/phoible/dev.git"


@app.callback()
def _main() -> None:
    """Varování z enginu vypisujeme jako čitelnou hlášku, ne jako Python traceback."""
    warnings.simplefilter("always")
    warnings.showwarning = lambda message, *_args, **_kwargs: typer.echo(f"⚠️  {message}", err=True)


@phonology_app.command("update-data")
def update_phonology_data(
    cache_dir: Path = typer.Option(None, help="Lokální cache (default: ~/.cee/phonology)."),
):
    """Stáhne Index Diachronica Redux a PHOIBLE a zafixuje jejich offline cache.

    Tento příkaz je jediná síťová cesta empirické vrstvy. Simulace samotná
    používá jen hotové JSON cache soubory, takže je reprodukovatelná offline.
    """
    paths = default_empirical_paths(cache_dir)
    paths["root"].mkdir(parents=True, exist_ok=True)
    repository = paths["diachronica_raw"]
    if (repository / ".git").is_dir():
        typer.echo("Aktualizuji lokální kopii Index Diachronica Redux…")
        subprocess.run(["git", "-C", str(repository), "pull", "--ff-only"], check=True)
    else:
        typer.echo("Stahuji Index Diachronica Redux…")
        subprocess.run(["git", "clone", "--depth", "1", INDEX_DIACHRONICA_REDUX_URL, str(repository)], check=True)

    phoible_repository = paths["phoible_repository"]
    if (phoible_repository / ".git").is_dir():
        typer.echo("Aktualizuji lokální kopii PHOIBLE…")
        subprocess.run(["git", "-C", str(phoible_repository), "pull", "--ff-only"], check=True)
    else:
        # Git v desktopovém runtime používá systémový trust store správně i
        # tam, kde Python urllib nemá k dispozici CA bundle. Zároveň získáme
        # přesný zdrojový commit, z nějž lokální cache vznikla.
        typer.echo("Stahuji aktuální PHOIBLE…")
        subprocess.run(["git", "clone", "--depth", "1", PHOIBLE_REPOSITORY_URL, str(phoible_repository)], check=True)
    report = build_empirical_cache(paths["root"])
    typer.echo(
        "Hotovo: "
        f"{report['observations']} změn Indexu, {report['inventories']} inventářů PHOIBLE.\n"
        f"Index commit: {report['diachronica_revision']}\n"
        f"PHOIBLE commit: {report['phoible_revision']}\n"
        f"Index SHA-256: {report['diachronica_sha256']}\n"
        f"PHOIBLE SHA-256: {report['phoible_sha256']}"
    )

def load_csv_lexicon(proto_csv: str, mapper: FeatureMapper) -> Lexicon:
    """Zpětně kompatibilní alias, kanonická implementace je v cee.pipeline."""
    return load_lexicon_from_csv(proto_csv, mapper)

@app.command("apply")
def apply(
    proto_csv: Path = typer.Option(..., help="Cesta k CSV s proto-lexikonem (sloupce 'id', 'ipa')"),
    rules_yaml: Path = typer.Option(..., help="Cesta k YAML s pravidly"),
    out_csv: Path = typer.Option(..., help="Cesta, kam se uloží vygenerovaný lexikon"),
    ground_truth_csv: str = typer.Option(None, help="Volitelné: Cesta k Ground Truth CSV (pro V1 validaci)"),
    apply_semantics: bool = typer.Option(False, "--apply-semantics", help="Zapnout sémantické posuny"),
    semantic_seed: int = typer.Option(42, help="Seed pro deterministické sémantické posuny")
):
    """
    Vygeneruje nový jazyk aplikací pravidel na proto-lexikon.
    """
    typer.echo("⚙️  Inicializuji FeatureMapper (toto může chvíli trvat)...")
    mapper = FeatureMapper()
    
    typer.echo(f"📖 Načítám lexikon z {proto_csv}...")
    lexicon = load_csv_lexicon(str(proto_csv), mapper)
            
    typer.echo(f"📜 Načítám pravidla z {rules_yaml}...")
    rules = YamlParser.parse_rules(str(rules_yaml))
    typer.echo(f"   Načteno {len(rules)} pravidel.")
    
    typer.echo("🚀 Spouštím derivační fold (fonologie)...")
    state = State(node_id="derived", year=0, inventory=Inventory(), lexicon=lexicon)
    fold = DerivationFold(rules)
    fold.apply_to_lexicon(lexicon, mapper, state)
    typer.echo(f"   Inventář po derivaci ({len(state.inventory.segments)}): "
               f"{' '.join(sorted(state.inventory.segments))}")
    
    if apply_semantics:
        graph_path = Path.home() / ".cee" / "semantics" / "graph.graphml"
        if not graph_path.exists():
            typer.echo(f"❌ Sémantický graf nebyl nalezen na {graph_path}. Spusťte builder.py.", err=True)
            raise typer.Exit(code=1)
            
        typer.echo("🧠 Načítám sémantický graf a spouštím sémantické posuny...")
        try:
            graph = SemanticGraph(str(graph_path))
        except Exception as exc:
            # Externí soubor (viz builder.py) — poškozený obsah selže různým
            # typem výjimky podle formátu (ElementTree.ParseError pro
            # GraphML, yaml.YAMLError pro YAML mock), ne jen OSError/ValueError.
            typer.echo(f"❌ Sémantický graf na {graph_path} se nepodařilo načíst "
                       f"({type(exc).__name__}): {exc}", err=True)
            raise typer.Exit(code=1)
        # Pro demonstraci použijeme vysokou pravděpodobnost 100% posunu, pokud to chceme vidět
        # v reálu by to bylo např. 0.05
        evaluator = SemanticEvaluator(graph, shift_prob=0.15, forget_prob=0.05, seed=semantic_seed)
        evaluator.evaluate(lexicon)
        
        # Výpis posunů
        shifted_count = sum(1 for w in lexicon.words if len(w.polysemy) > 0)
        typer.echo(f"   Sémantickým posunem (nový význam) prošlo {shifted_count} slov.")
    
    typer.echo(f"💾 Zapisuji výsledek do {out_csv}...")
    with open(out_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'ipa', 'polysemy'])
        writer.writeheader()
        for word in lexicon.words:
            writer.writerow({
                'id': word.concept_id,
                'ipa': mapper.render_word(word),
                'polysemy': '|'.join(word.polysemy) if hasattr(word, 'polysemy') else ''
            })
            
    typer.echo("✅ Hotovo! CEE dokončilo derivaci.")
    
    if ground_truth_csv:
        typer.echo(f"\n📊 Běžím V1 Validaci proti {ground_truth_csv}...")
        metrics = ValidationMetric.evaluate(lexicon, ground_truth_csv, mapper)
        typer.echo(f"   Porovnáno slov: {metrics['comparisons']}")
        typer.echo(f"   Přesná shoda: {metrics['exact_match_ratio'] * 100:.1f}%")
        typer.echo(f"   Průměrná fonetická editační vzdálenost (LingPy): {metrics['avg_edit_distance']:.3f} (blíže k 0.0 je lepší)")


@app.command()
@app.command()
def simulate(
    topology_yaml: Path = typer.Option(..., help="Cesta k YAML definici evoluční sítě"),
    proto_csv: Path = typer.Option(..., help="Cesta k počátečnímu proto-lexikonu"),
    out_dir: Path = typer.Option(None, help="Cílová složka (defaultně: runs/run_YYYYMMDD_HHMMSS)"),
    preset_yaml: Path = typer.Option(None, help="Volitelná cesta k presetu pro generátor zvukových změn"),
    semantics_yaml: Path = typer.Option(None, help="Volitelná cesta k YAML sémantickému grafu pro posuny významů"),
    seed: int = typer.Option(42, help="Seed pro deterministický běh (výpůjčky, generátor, sémantika)"),
    empirical_phonology: bool = typer.Option(
        False,
        "--empirical-phonology",
        help="Použít lokální Index Diachronica/PHOIBLE cache (nejdřív cee phonology update-data).",
    ),
):
    """
    Spustí globální lockstep simulaci celé rodiny na základě topologie a výpůjček.
    """
    typer.echo("⚙️  Inicializuji FeatureMapper (toto může chvíli trvat)...")
    mapper = FeatureMapper()
    
    typer.echo(f"📖 Načítám proto-lexikon z {proto_csv}...")
    lexicon = load_csv_lexicon(str(proto_csv), mapper)
    
    typer.echo(f"📜 Načítám topologii z {topology_yaml}...")
    graph = YamlParser.parse_topology(str(topology_yaml))
    
    preset_data = None
    if preset_yaml:
        typer.echo(f"🎨 Načítám preset z {preset_yaml}...")
        preset_data = YamlParser.parse_preset(str(preset_yaml))
        typer.echo(f"   -> Používá se preset: {preset_data.get('name')}")
    
    if semantics_yaml:
        typer.echo(f"🧠 Načítám sémantický graf z {semantics_yaml}...")

    config = SimulationConfig(
        preset=preset_data,
        semantics_path=str(semantics_yaml) if semantics_yaml else None,
        seed=seed,
        use_empirical_phonology=empirical_phonology,
    )

    # Diagnostický seznam se bere z protojazyka PŘED simulací a je pro všechny
    # větve stejný — je to měřicí přístroj, ne vlastnost jazyka (5.1).
    diagnostic = LexicalRetention.diagnostic_from(lexicon)

    typer.echo("🚀 Spouštím evoluční simulátor v globálním lockstepu...")
    final_states = run_simulation(lexicon, graph, mapper, config)
    branches = build_branch_views(final_states, mapper, diagnostic)

    if not out_dir:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(f"runs/run_{timestamp}")
    
    out_dir.mkdir(parents=True, exist_ok=True)
    typer.echo(f"💾 Zapisuji výsledky do složky {out_dir}...")
    for branch_id, branch in branches.items():
        branch_csv = out_dir / f"{branch_id}.csv"
        with open(branch_csv, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(
                f, fieldnames=['id', 'ipa', 'polysemy', 'origin_year', 'source_id']
            )
            writer.writeheader()
            for word in branch.words:
                writer.writerow({
                    'id': word.id,
                    'ipa': word.ipa,
                    'polysemy': '|'.join(word.polysemy),
                    'origin_year': word.origin_year,
                    'source_id': word.source_id or ''
                })

        # Gramatický náčrt je podle 4.x součástí exportu, ne jen věc UI.
        (out_dir / f"{branch_id}.md").write_text(branch.grammar_md, encoding='utf-8')

        typer.echo(
            f"   -> '{branch_id}' (rok {branch.year}, {len(branch.inventory)} fonémů) "
            f"-> {branch_csv.name} + {branch_id}.md"
        )

    typer.echo("\n📊 Lexikální retence proti protojazyku "
               f"({len(diagnostic)} konceptů, metrika A dle 5.1):")
    for branch_id, branch in branches.items():
        r = branch.retention
        band = r.in_plausible_band(branch.year)
        znacka = {True: "v pásmu", False: "MIMO pásmo 75–95 %/tis. let", None: ""}[band]
        typer.echo(
            f"   {branch_id:16} {r.ratio:6.1%}  "
            f"(drží {len(r.retained)}, výpůjčka {len(r.borrowed)}, ztraceno {len(r.lost)})"
            + (f"  {znacka}" if znacka else "")
        )

    typer.echo("\n✅ Hotovo! Síť je vygenerována.")

@app.command()
def ui(
    port: int = typer.Option(None, help="Pevný port. Bez něj se vybere první volný od 8000 nahoru."),
    open_browser_flag: bool = typer.Option(True, "--open-browser/--no-open-browser",
                                           help="Otevřít po startu prohlížeč."),
    reload: bool = typer.Option(False, "--reload", help="Automaticky reloadovat server při změně kódu."),
):
    """
    Spustí backend pro grafické rozhraní (lokální FastAPI server).

    Port se volí automaticky, aby si CEE nekolidovalo s jinou aplikací běžící
    na 8000. Zvolená adresa se zapíše do `ui/.env.local`, odkud si ji vezme
    Vite; frontend si ji navíc umí za běhu najít sám.
    """
    from cee.api.ports import DEFAULT_PORT, find_free_port, is_port_free
    from cee.api.server import start_server

    if port is None:
        port = find_free_port(DEFAULT_PORT)
        if port != DEFAULT_PORT:
            typer.echo(f"⚠️  Port {DEFAULT_PORT} je obsazený, používám {port}.", err=True)
    elif not is_port_free(port):
        typer.echo(f"❌ Port {port} je obsazený. Spusť příkaz bez --port pro automatickou volbu.",
                   err=True)
        raise typer.Exit(code=1)

    api_url = f"http://127.0.0.1:{port}"
    _write_api_url(api_url)

    typer.echo(f"🌐 CEE API běží na {api_url}")
    typer.echo(f"   Frontend spusť zvlášť: cd ui && npm run dev")

    if open_browser_flag:
        def open_browser():
            time.sleep(1)  # Počkáme sekundu na náběh uvicornu
            webbrowser.open(api_url)

        threading.Thread(target=open_browser, daemon=True).start()

    # Blokující volání uvicornu
    start_server(port=port, reload=reload)


def _write_api_url(api_url: str) -> None:
    """
    Zapíše adresu API do `ui/.env.local`, aby ji Vite předal frontendu jako
    `VITE_CEE_API_URL`. Soubor je generovaný a patří do .gitignore.
    """
    ui_dir = Path(__file__).resolve().parents[3] / "ui"
    if not ui_dir.is_dir():
        return

    env_file = ui_dir / ".env.local"
    try:
        env_file.write_text(
            "# Generováno příkazem `cee ui` — needituj ručně.\n"
            f"VITE_CEE_API_URL={api_url}\n",
            encoding="utf-8",
        )
    except OSError as exc:
        typer.echo(f"⚠️  Nepodařilo se zapsat {env_file}: {exc}", err=True)

if __name__ == "__main__":
    app()
