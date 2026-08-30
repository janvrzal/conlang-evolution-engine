import csv
import copy
import datetime
import hashlib
import json
import subprocess
import threading
import time
import warnings
import webbrowser
from pathlib import Path

import typer

from cee.core.models import Inventory, Lexicon, State
from cee.engine.empirical import PhoibleInventoryModel, save_phoible_model
from cee.engine.empirical import default_paths as default_empirical_paths
from cee.engine.fold import DerivationFold
from cee.engine.generator import SoundChangeGenerator
from cee.engine.inventory import InventoryView
from cee.engine.parser import YamlParser
from cee.engine.phonology import FeatureMapper
from cee.engine.protolang import ProtolangGenerator
from cee.engine.schemas import SCHEMA_REGISTRY
from cee.engine.semantics import SemanticEvaluator
from cee.metrics.generator_validation import compare_to_global_distribution, profile_rules
from cee.metrics.global_baseline import (
    load_global_baseline,
    save_global_baseline,
    train_from_manifest,
)
from cee.metrics.correspondence import build_gled_correspondence_profile
from cee.metrics.correspondence import profile_simulated_word_pairs
from cee.metrics.macro_calibration import calibrate_macro_grid
from cee.metrics.macro_calibration import deletion_diagnostics
from cee.metrics.retention import LexicalRetention
from cee.metrics.validation import ValidationMetric
from cee.pipeline import (
    SimulationConfig,
    build_branch_views,
    load_lexicon_from_csv,
    load_lexicon_from_records,
    run_simulation,
)
from cee.semantics.graph import SemanticGraph

app = typer.Typer(help="Conlang Evolution Engine CLI", no_args_is_help=True)
phonology_app = typer.Typer(help="Správa volitelných empirických fonologických dat.")
calibration_app = typer.Typer(help="Tvorba auditovatelných kalibrací generátoru.")
app.add_typer(phonology_app, name="phonology")
app.add_typer(calibration_app, name="calibrate")

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
    """Stáhne PHOIBLE a zafixuje jeho offline cache.

    Tento příkaz je jediná síťová cesta empirické vrstvy. Simulace samotná
    používá jen hotové JSON cache soubory, takže je reprodukovatelná offline.
    """
    paths = default_empirical_paths(cache_dir)
    paths["root"].mkdir(parents=True, exist_ok=True)
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
    model = PhoibleInventoryModel.from_csv(paths["phoible_raw"])
    save_phoible_model(model, paths["phoible_model"])
    typer.echo(
        f"Hotovo: {len(model.inventories)} inventářů PHOIBLE.\n"
        f"PHOIBLE SHA-256: {model.provenance['sha256']}"
    )


@calibration_app.command("global")
def train_global_calibration(
    manifest: Path = typer.Option(..., exists=True, help="Manifest otevřených anotovaných pozorování."),
    out: Path = typer.Option(..., help="Cílová JSON baseline; je bezpečné ji verzovat."),
):
    """Natrénuje rodinně vyvážené váhy globálních schémat.

    Vstupní data se neukládají do repozitáře. Výstup nese jejich SHA-256,
    verzi, licenci a citaci, takže je vždy auditovatelný a reprodukovatelný.
    """
    baseline = train_from_manifest(manifest, SCHEMA_REGISTRY)
    out.parent.mkdir(parents=True, exist_ok=True)
    save_global_baseline(baseline, out)
    typer.echo(
        f"Hotovo: {baseline.observations} pozorování z {baseline.families} rodin.\n"
        f"Baseline: {out}\n"
        f"Nejsilnější váhy: "
        + ", ".join(
            f"{schema}={weight:.2f}"
            for schema, weight in sorted(
                baseline.schema_multipliers.items(), key=lambda item: item[1], reverse=True
            )[:5]
        )
    )


@calibration_app.command("measure")
def measure_global_calibration(
    baseline: Path = typer.Option(..., exists=True, help="Baseline vytvořená příkazem 'calibrate global'."),
    preset: Path = typer.Option(..., exists=True, help="Preset, který se má měřit."),
    runs: int = typer.Option(50, min=1, help="Počet deterministických vzorků generátoru."),
    years: int = typer.Option(1000, min=1, help="Délka každého vzorku."),
    rules_per_run: int = typer.Option(12, min=1, help="Počet slotů pravidel na vzorek."),
    seed: int = typer.Option(42, help="Počáteční seed vzorkování."),
):
    """Změří V2a distribuci aktuálního generátoru proti globální baseline."""
    learned = load_global_baseline(baseline)
    preset_data = YamlParser.parse_preset(str(preset))
    mapper = FeatureMapper()
    # Široký referenční inventář měří volbu schémat, ne specifičnost jedné
    # konkrétní fonologie. Vlastní simulace dále filtruje neproveditelné změny.
    inventory = InventoryView(mapper, set("aeiouptkbdɡfvszʃxhmnŋlrjw"))
    generated = []
    for index in range(runs):
        generator = SoundChangeGenerator(
            preset_data,
            seed=seed + index,
            schema_multipliers=learned.schema_multipliers,
        )
        generated.extend(
            generator.generate_rules_for_edge(
                State(
                    node_id=f"calibration-{index}",
                    inventory=Inventory(),
                    lexicon=Lexicon(),
                    map={},
                ),
                0,
                years,
                num_rules=rules_per_run,
                inventory=inventory,
            )
        )
    profile = profile_rules(generated, years=years * runs)
    metrics = compare_to_global_distribution(
        profile, learned.schema_distribution, learned.environment_distribution
    )
    typer.echo(f"Vygenerováno pravidel: {profile.changes}")
    typer.echo(f"Hellinger (typ změny): {metrics['schema_hellinger']:.3f}")
    typer.echo(f"Hellinger (prostředí): {metrics['environment_hellinger']:.3f}")
    typer.echo(f"Pokrytí baseline schémat: {metrics['attested_schema_coverage']:.1%}")
    typer.echo("Rychlost změn/tisíciletí se neuvádí: vstup neobsahuje datované intervaly.")


@calibration_app.command("correspondences")
def measure_global_correspondences(
    gled_tsv: Path = typer.Option(..., exists=True, help="Cesta k release TSV databáze GLED."),
    out: Path = typer.Option(..., help="Cílový JSON profil korespondencí."),
):
    """Sestaví globální profil nesměrovaných korespondencí z GLED."""
    profile = build_gled_correspondence_profile(gled_tsv)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(profile.as_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    typer.echo(
        f"Hotovo: {profile.forms} forem, {profile.cognate_sets} kognátních sad, "
        f"{profile.families} rodin.\n"
        f"Rodinně vyvážený profil: "
        + ", ".join(f"{key}={value:.1%}" for key, value in profile.family_distribution.items())
    )


@calibration_app.command("macro")
def calibrate_global_macro(
    target: Path = typer.Option(..., exists=True, help="GLED profil z 'calibrate correspondences'."),
    preset: Path = typer.Option(..., exists=True, help="Preset určený ke kalibraci."),
    out: Path = typer.Option(..., help="Cílový JSON report grid-search."),
    lexicon_size: int = typer.Option(400, min=50, max=2000, help="Počet syntetických protolexémů."),
    years: int = typer.Option(1500, min=100, help="Časová hloubka dvou sesterských větví."),
    seed: int = typer.Option(42, help="Seed syntetického benchmarku."),
    repeats: int = typer.Option(3, min=1, max=20, help="Počet nezávislých deterministických opakování."),
):
    """Kalibruje makro-divergenci simulovaných sester proti GLED.

    Jde o reprodukovatelný syntetický benchmark, nikoli o důkaz, že jedna
    konkrétní simulovaná rodina reprezentuje všechny reálné rodiny.
    """
    target_data = json.loads(target.read_text(encoding="utf-8"))
    target_profile = target_data["family_distribution"]
    preset_data = YamlParser.parse_preset(str(preset))
    mapper = FeatureMapper()
    concepts = [{"id": f"benchmark-{index}"} for index in range(lexicon_size)]
    diagnostics = {}

    def measure(candidate):
        from cee.engine.topology import EvolutionGraph, VerticalEdge
        from cee.engine.graph_builder import GraphBuilder

        profiles = []
        deleted = {}
        for offset in range(repeats):
            run_seed = seed + offset
            records = ProtolangGenerator(seed=run_seed).generate_lexicon(
                "p t k b d ɡ f s m n l r j w", "a e i o u", "CVC", concepts
            )
            graph = EvolutionGraph(
                node_configs={
                    "proto": {},
                    "left": {"map": {"macro": dict(candidate)}},
                    "right": {"map": {"macro": dict(candidate)}},
                },
                vertical_edges=[VerticalEdge("proto", "left"), VerticalEdge("proto", "right")],
            )
            builder = GraphBuilder()
            states = run_simulation(
                load_lexicon_from_records(copy.deepcopy(records), mapper),
                graph,
                mapper,
                SimulationConfig(
                    preset=preset_data,
                    seed=run_seed,
                    years=years,
                    root_id="proto",
                    enable_semantics=False,
                ),
                graph_builder=builder,
            )
            for schema_id, count in deletion_diagnostics(builder.events).items():
                deleted[schema_id] = deleted.get(schema_id, 0) + count
            left = {word.concept_id: word for word in states["left"].lexicon.words if word.active}
            right = {word.concept_id: word for word in states["right"].lexicon.words if word.active}
            profiles.append(profile_simulated_word_pairs(
                [(left[key], right[key]) for key in sorted(set(left) & set(right))], mapper
            ))

        diagnostics[tuple(sorted(candidate.items()))] = deleted
        keys = set().union(*profiles)
        return {key: sum(profile.get(key, 0.0) for profile in profiles) / repeats for key in keys}

    # Osm kandidátů drží interaktivní běh pod rozumnou dobou. V první iteraci
    # ladíme celkovou rychlost a podíl deletivních změn; eroze kody zůstává
    # neutrální, aby se dva překrývající regulátory nemíchaly dohromady.
    candidates = [
        {"change_rate": rate, "deletion_rate": deletion, "conservatism": conservatism}
        for rate in (0.75, 1.5)
        for deletion in (0.2, 0.5)
        for conservatism in (0.0, 0.2)
    ]
    results = calibrate_macro_grid(candidates, target_profile, measure)
    payload = {
        "target": str(target),
        "target_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "lexicon_size": lexicon_size,
        "years": years,
        "seed": seed,
        "repeats": repeats,
        "results": [
            {
                "parameters": result.parameters,
                "profile": result.profile,
                "distance": result.distance,
                "deleted_segments_by_schema": diagnostics[tuple(sorted(result.parameters.items()))],
            }
            for result in results
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    best = results[0]
    typer.echo(
        f"Nejbližší kandidát: {best.parameters}; Hellinger={best.distance:.3f}.\n"
        f"Profil: " + ", ".join(f"{key}={value:.1%}" for key, value in best.profile.items())
    )
    if deleted := diagnostics[tuple(sorted(best.parameters.items()))]:
        typer.echo("Mazání podle schématu: " + ", ".join(f"{key}={value}" for key, value in deleted.items()))

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
        help="Použít lokální PHOIBLE kontrolu inventáře (nejdřív cee phonology update-data).",
    ),
    global_baseline: Path = typer.Option(
        None,
        help="Volitelná auditovatelná baseline z 'cee calibrate global'.",
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
        global_baseline_path=str(global_baseline) if global_baseline else None,
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
    typer.echo("   Frontend spusť zvlášť: cd ui && npm run dev")

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
