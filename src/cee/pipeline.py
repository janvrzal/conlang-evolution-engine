"""
Servisní vrstva mezi enginem a jeho rozhraními.

CLI i HTTP API potřebují tutéž sekvenci: postav lexikon, poskládej graf, spusť
simulátor, serializuj výsledek. Držet ji na jednom místě znamená, že se obě
rozhraní chovají stejně — dřív existovala ve třech kopiích, které se lišily
(např. jen jedna z nich předávala seed).
"""
from __future__ import annotations

import csv
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from cee.core.models import Inventory, Lexicon, State
from cee.engine.inventory import InventoryView
from cee.engine.phonology import FeatureMapper
from cee.engine.semantics import SemanticEvaluator
from cee.engine.simulator import EvolutionSimulator
from cee.engine.topology import EvolutionGraph
from cee.metrics.retention import LexicalRetention, RetentionResult
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


@dataclass
class WordView:
    id: str
    ipa: str
    polysemy: List[str] = field(default_factory=list)
    origin_year: int = 0
    source_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ipa": self.ipa,
            "polysemy": self.polysemy,
            "origin_year": self.origin_year,
            "source_id": self.source_id,
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
            mapper.parse_word(concept_id=record["id"], ipa_string=record["ipa"])
        )
    return lexicon


def build_semantic_evaluator(config: SimulationConfig) -> Optional[SemanticEvaluator]:
    """
    Sestaví sémantický evaluátor, nebo vrátí None. Chybějící graf běh nezastaví,
    ale nesmí zmizet potichu.
    """
    if not config.semantics_path:
        return None

    try:
        graph = SemanticGraph(config.semantics_path)
    except (OSError, ValueError) as exc:
        warnings.warn(
            f"Sémantický graf '{config.semantics_path}' se nepodařilo načíst: {exc}",
            stacklevel=2,
        )
        return None

    return SemanticEvaluator(
        graph,
        shift_prob=config.shift_prob,
        forget_prob=config.forget_prob,
        seed=config.seed,
    )


def run_simulation(
    lexicon: Lexicon,
    graph: EvolutionGraph,
    mapper: FeatureMapper,
    config: Optional[SimulationConfig] = None,
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
