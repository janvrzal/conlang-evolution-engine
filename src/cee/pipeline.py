"""
Servisní vrstva mezi enginem a jeho rozhraními.

CLI i HTTP API potřebují tutéž sekvenci: postav lexikon, poskládej graf, spusť
simulátor, serializuj výsledek. Držet ji na jednom místě znamená, že se obě
rozhraní chovají stejně — dřív existovala ve třech kopiích, které se lišily
(např. jen jedna z nich předávala seed).
"""
from __future__ import annotations

import copy
import csv
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from cee.core.models import Inventory, Lexicon, State
from cee.engine.generator import MacroParams, SoundChangeGenerator
from cee.engine.graph_builder import GraphBuilder
from cee.engine.rng import derive_seed

from cee.engine.inventory import InventoryView
from cee.engine.phonology import FeatureMapper
from cee.engine.semantics import SemanticEvaluator
from cee.engine.simulator import EvolutionSimulator
from cee.engine.topology import EvolutionGraph
from cee.metrics.retention import LexicalRetention, RetentionResult
from cee.semantics.builder import default_paths as default_semantics_paths
from cee.semantics.graph import SemanticGraph

DEFAULT_SEED = 42
DEFAULT_SHIFT_PROB = 0.3
DEFAULT_FORGET_PROB = 0.05


@dataclass
class SimulationConfig:
    """Vše, co odlišuje jeden běh od druhého. Stejná konfigurace = stejný výsledek."""

    preset: Optional[Dict[str, Any]] = None
    semantics_path: Optional[str] = None
    seed: int = DEFAULT_SEED
    shift_prob: float = DEFAULT_SHIFT_PROB
    forget_prob: float = DEFAULT_FORGET_PROB
    root_id: str = "proto"
    root_year: int = 0

    #: Časová hloubka simulace. Bez ní se generují pravidla jen na 200 let.
    years: Optional[int] = None
    #: UI může chtít sledovat i proměnu kořenového protojazyka, nejen větví.
    evolve_root: bool = False


@dataclass
class WordView:
    id: str
    ipa: str
    polysemy: List[str] = field(default_factory=list)
    origin_year: int = 0
    source_id: Optional[str] = None
    frequency: float = 0.5
    active: bool = True
    origin_type: str = "inherited"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ipa": self.ipa,
            "polysemy": self.polysemy,
            "origin_year": self.origin_year,
            "source_id": self.source_id,
            "frequency": self.frequency,
            "active": self.active,
            "origin_type": self.origin_type,
        }


@dataclass
class BranchView:
    """Jeden vygenerovaný jazyk připravený k serializaci."""

    id: str
    year: int
    words: List[WordView]
    inventory: List[str]
    grammar_md: str
    retention: Optional[RetentionResult] = None

    def as_dict(self) -> Dict[str, Any]:
        payload = {
            "year": self.year,
            "words": [w.as_dict() for w in self.words],
            "inventory": self.inventory,
            "grammar_md": self.grammar_md,
        }
        if self.retention is not None:
            payload["retention"] = self.retention.as_dict()
        return payload


def load_lexicon_from_csv(path: str, mapper: FeatureMapper) -> Lexicon:
    """Načte proto-lexikon z CSV se sloupci `id` a `ipa_proto` (nebo `ipa`)."""
    lexicon = Lexicon()
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ipa = row.get("ipa_proto") or row.get("ipa")
            if not ipa:
                warnings.warn(f"Řádek {row.get('id')!r} v {path} nemá IPA, přeskakuji.",
                              stacklevel=2)
                continue
            lexicon.words.append(mapper.parse_word(concept_id=row["id"], ipa_string=ipa))
    return lexicon


def load_lexicon_from_records(records: Iterable[Dict[str, str]], mapper: FeatureMapper) -> Lexicon:
    """Načte proto-lexikon z JSON záznamů, jak je posílá UI."""
    lexicon = Lexicon()
    for record in records:
        lexicon.words.append(
            mapper.parse_word(
                concept_id=record["id"],
                ipa_string=record["ipa"],
                is_grammatical=record.get("is_grammatical", False)
            )
        )
        lexicon.words[-1].polysemy = set(record.get("polysemy", []))
    return lexicon


def resolve_semantics_path(preferred: Optional[str]) -> Optional[str]:
    """
    Rozhodne, který sémantický graf se má použít.

    - Je-li `preferred` zadané a existuje, použije se přímo (explicitní volba
      volajícího má přednost).
    - Jinak zkusí skutečný graf sestavený z CLICS4 + DatSemShift
      (`~/.cee/semantics/graph.graphml` — viz `cee/semantics/builder.py`).
      Podle AGENT.md se tahle data NIKDY necommitují, takže na čerstvém
      klonu / v CI nemusí existovat.
    - Bez něj spadne na malý YAML mock zabalený v repu, aby simulace vůbec
      měla s čím pracovat — vždycky dostupný, ale jen 14 dvojic pojmů.
    """
    if preferred and os.path.exists(preferred):
        return preferred

    real_graph = default_semantics_paths()["out_path"]
    if os.path.exists(real_graph):
        return real_graph

    mock = Path(__file__).resolve().parent / "data" / "semantics_mock.yaml"
    return str(mock) if mock.exists() else None


# Cache klíčovaná cestou ke grafu, ne jediná globální proměnná — jinak by po
# prvním načtení `semantics_mock.yaml` zůstal navěky použitý i pro požadavky,
# které výslovně chtěly jiný (třeba skutečný CLICS4/DatSemShift) graf.
_semantic_graph_cache: Dict[str, SemanticGraph] = {}

# Načítání FeatureMapper (PanPhon tabulek) trvá 1.25s, chceme to jen jednou.
_global_feature_mapper: Optional[FeatureMapper] = None


def get_feature_mapper() -> FeatureMapper:
    """Vrátí globální instanci FeatureMapperu (vytvoří, pokud neexistuje)."""
    global _global_feature_mapper
    if _global_feature_mapper is None:
        _global_feature_mapper = FeatureMapper()
    return _global_feature_mapper


def build_semantic_evaluator(config: SimulationConfig) -> Optional[SemanticEvaluator]:
    """
    Sestaví sémantický evaluátor, nebo vrátí None. Chybějící graf běh nezastaví,
    ale nesmí zmizet potichu.
    """
    path = resolve_semantics_path(config.semantics_path)
    if not path:
        return None

    if path not in _semantic_graph_cache:
        try:
            _semantic_graph_cache[path] = SemanticGraph(path)
        except Exception as exc:  # noqa: BLE001 — viz komentář níže
            # Záměrně široký záchyt. Soubor je externí (stažená/sestavená
            # cache mimo repo, viz AGENT.md), takže poškozený obsah selže
            # jiným výjimkovým typem podle formátu:
            # `xml.etree.ElementTree.ParseError` (dědí ze SyntaxError, ne
            # z OSError/ValueError) pro poškozený GraphML, `yaml.YAMLError`
            # pro poškozený YAML mock. Užší výčet by je propustil jako
            # tvrdý pád místo hlášky a pádu zpět na jiný zdroj — a to je
            # přesně to, co má tahle funkce podle jména dělat.
            warnings.warn(
                f"Sémantický graf '{path}' se nepodařilo načíst "
                f"({type(exc).__name__}): {exc}",
                stacklevel=2,
            )
            return None

    return SemanticEvaluator(
        _semantic_graph_cache[path],
        shift_prob=config.shift_prob,
        forget_prob=config.forget_prob,
        seed=config.seed,
    )


def run_simulation(
    lexicon: Lexicon,
    graph: EvolutionGraph,
    mapper: FeatureMapper,
    config: Optional[SimulationConfig] = None,
    graph_builder: Optional[GraphBuilder] = None,
) -> Dict[str, State]:
    """Spustí lockstep simulaci nad daným grafem a vrátí finální stavy uzlů."""
    config = config or SimulationConfig()

    root_state = State(
        node_id=config.root_id,
        year=config.root_year,
        inventory=Inventory(),
        lexicon=lexicon,
    )

    simulator = EvolutionSimulator(
        graph,
        mapper,
        preset=config.preset,
        seed=config.seed,
        semantic_evaluator=build_semantic_evaluator(config),
        end_year=config.years,
        graph_builder=graph_builder,
        evolve_root=config.evolve_root,
    )
    return simulator.simulate(root_state)


def grammar_sketch(
    state: State,
    inventory: List[str],
    retention: Optional[RetentionResult] = None,
) -> str:
    """Lidsky čitelný náčrt gramatiky uzlu (export dle CEE_master.md 4.x)."""
    lines = [
        f"# Gramatika jazyka {state.node_id}",
        "",
        f"*Rok {state.year}*" + (f", z uzlu `{state.parent_id}`" if state.parent_id else ""),
        "",
        "## Fonologie",
        "",
        f"Inventář ({len(inventory)} fonémů): {' '.join(inventory) if inventory else '—'}",
        "",
        "## Morfologie",
        "",
        f"- Strategie odvozování: {state.affixation_strategy}",
        f"- Tvorba složenin: head-{state.compound_head}",
    ]

    loans = sorted({w.source_id for w in state.lexicon.words if w.source_id})
    if loans:
        lines += ["", "## Kontakt", "", f"- Výpůjčky z: {', '.join(loans)}"]

    if state.social:
        labels = {
            "prestige": "prestiž", "mobility": "mobilita", "literacy": "gramotnost",
            "standardization": "standardizace", "population": "populace",
        }
        social = ", ".join(f"{labels.get(key, key)} {value:.0%}" for key, value in sorted(state.social.items()))
        lines += ["", "## Společnost", "", f"- {social}"]

    if retention is not None and retention.total:
        lines += [
            "",
            "## Lexikální retence",
            "",
            f"- Drží původní kořen: {len(retention.retained)}/{retention.total} "
            f"({retention.ratio:.0%})",
            f"- Nahrazeno výpůjčkou: {len(retention.borrowed)}",
            f"- Slot neobsazen: {len(retention.lost)}",
        ]

    return "\n".join(lines) + "\n"


def build_branch_view(
    state: State,
    mapper: FeatureMapper,
    diagnostic: Optional[Sequence[str]] = None,
) -> BranchView:
    """
    Převede stav uzlu na serializovatelný pohled.

    `diagnostic` je fixní seznam konceptů pro měření lexikální retence.
    Musí být stejný pro všechny porovnávané uzly, jinak jsou hodnoty
    nesrovnatelné (CEE_master.md 5.1).
    """
    inventory = sorted(InventoryView.from_lexicon(state.lexicon, mapper))

    words = [
        WordView(
            id=word.concept_id,
            ipa=mapper.render_word(word),
            polysemy=sorted(word.polysemy),
            origin_year=word.origin_year,
            source_id=word.source_id,
            frequency=word.frequency,
            active=word.active,
            origin_type=word.origin_type,
        )
        for word in state.lexicon.words
    ]

    retention = (
        LexicalRetention.evaluate(state.lexicon, diagnostic)
        if diagnostic is not None
        else None
    )

    return BranchView(
        id=state.node_id,
        year=state.year,
        words=words,
        inventory=inventory,
        grammar_md=grammar_sketch(state, inventory, retention),
        retention=retention,
    )


def build_branch_views(
    states: Dict[str, State],
    mapper: FeatureMapper,
    diagnostic: Optional[Sequence[str]] = None,
) -> Dict[str, BranchView]:
    return {
        node_id: build_branch_view(state, mapper, diagnostic)
        for node_id, state in states.items()
    }


def topology_payload(graph: EvolutionGraph) -> Dict[str, Any]:
    return {
        "nodes": [{"id": node_id} for node_id in graph.node_configs],
        "edges": [
            {"source": edge.parent_id, "target": edge.child_id}
            for edge in graph.vertical_edges
        ],
    }


# --- Vývoj jedné linie (bez větvení) ------------------------------------------


@dataclass
class LineageConfig:
    """
    Nastavení vývoje jednoho jazyka v čase.

    Tohle je nejjednodušší smysluplný běh CEE: žádné větvení, žádný kontakt —
    jen protojazyk, který se sám mění, a záznam toho, čím prošel.
    """

    years: int = 1000
    epochs: int = 5
    rules_per_epoch: int = 2
    node_id: str = "proto"
    seed: int = DEFAULT_SEED
    preset: Optional[Dict[str, Any]] = None
    biome: Optional[str] = None

    #: Makro-parametry generátoru (rychlost změny, konzervativnost, eroze konců).
    macro: Optional[Dict[str, Any]] = None

    @property
    def epoch_length(self) -> int:
        return max(1, self.years // max(1, self.epochs))
