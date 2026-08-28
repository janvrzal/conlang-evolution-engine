import csv
import typer
from pathlib import Path
from cee.engine.phonology import FeatureMapper
from cee.engine.parser import YamlParser
from cee.engine.fold import DerivationFold
from cee.core.models import Lexicon
from cee.metrics.validation import ValidationMetric
from cee.semantics.graph import SemanticGraph
from cee.engine.semantics import SemanticEvaluator

app = typer.Typer(help="Conlang Evolution Engine CLI", no_args_is_help=True)

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
    lexicon = Lexicon()
    with open(proto_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ipa_val = row.get('ipa_proto', row.get('ipa'))
            word = mapper.parse_word(concept_id=row['id'], ipa_string=ipa_val)
            lexicon.words.append(word)
            
    typer.echo(f"📜 Načítám pravidla z {rules_yaml}...")
    rules = YamlParser.parse_rules(str(rules_yaml))
    typer.echo(f"   Načteno {len(rules)} pravidel.")
    
    typer.echo("🚀 Spouštím derivační fold (fonologie)...")
    fold = DerivationFold(rules)
    fold.apply_to_lexicon(lexicon, mapper)
    
    if apply_semantics:
        graph_path = Path.home() / ".cee" / "semantics" / "graph.graphml"
        if not graph_path.exists():
            typer.echo(f"❌ Sémantický graf nebyl nalezen na {graph_path}. Spusťte builder.py.", err=True)
            raise typer.Exit(code=1)
            
        typer.echo("🧠 Načítám sémantický graf a spouštím sémantické posuny...")
        graph = SemanticGraph(str(graph_path))
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

if __name__ == "__main__":
    app()
