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
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from cee.core.models import Inventory, Lexicon, State
from cee.engine.generator import MacroParams, SoundChangeGenerator
from cee.engine.rng import derive_seed
from cee.engine.history import (
    RuleApplication,
    SimulationHistory,
    Snapshot,
    WordChange,
)
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

    #: Časová hloubka simulace. Bez ní se generují pravidla jen na 200 let.
    years: Optional[int] = None


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
        end_year=config.years,
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


def _snapshot(state: State, mapper: FeatureMapper, year: int, label: str) -> Snapshot:
    return Snapshot(
        year=year,
        node_id=state.node_id,
        label=label,
        words={w.concept_id: mapper.render_word(w) for w in state.lexicon.words},
        inventory=sorted(InventoryView.from_lexicon(state.lexicon, mapper)),
    )


def evolve_lineage(
    lexicon: Lexicon,
    mapper: FeatureMapper,
    config: Optional[LineageConfig] = None,
) -> tuple[State, SimulationHistory]:
    """
    Nechá jeden jazyk vyvíjet se v čase a zaznamená celý průběh.

    Vrací konečný stav a historii se snapshoty po epochách i se seznamem
    zvukových změn včetně toho, která slova každá z nich zasáhla.
    """
    config = config or LineageConfig()
    history = SimulationHistory()

    state = State(
        node_id=config.node_id,
        year=0,
        inventory=Inventory(),
        lexicon=lexicon,
        map={"biome": config.biome} if config.biome else {},
    )

    inventory = InventoryView.from_lexicon(lexicon, mapper)
    state.inventory = inventory.to_inventory()
    history.snapshot(_snapshot(state, mapper, 0, "Protojazyk"))

    # Seed se odvozuje z ID uzlu, aby dva jazyky se stejným nastavením
    # nedostaly identickou chronologii (CEE_master.md 5.5).
    generator = (
        SoundChangeGenerator(
            config.preset,
            seed=derive_seed(config.seed, config.node_id),
            macro=MacroParams.from_config(config.preset.get("macro"), config.macro),
        )
        if config.preset
        else None
    )
    if generator is None:
        warnings.warn(
            "Bez presetu se jazyk nemá podle čeho měnit — vývoj bude prázdný.",
            stacklevel=2,
        )

    base_slots = config.epochs * config.rules_per_epoch
    total_slots = generator.macro.slots_for(base_slots) if generator else base_slots

    def _would_change(rule) -> bool:
        """
        Poslední síto: má pravidlo na aktuálním lexikonu vůbec dopad?

        Inventář nezná pozici hlásky ve slově, takže z něj nelze vyčíst, že
        třeba fortice na začátku slova nemá co dělat. Zkusíme ji proto nanečisto
        na kopii — je to levné a ušetří to prázdné kroky v chronologii.
        """
        return any(rule.apply_to_word(copy.deepcopy(w)) for w in state.lexicon.words)

    previous_rule = None
    next_epoch = config.epoch_length
    epoch_index = 1

    for slot in range(total_slots):
        year = (
            generator.year_for_slot(0, config.years, slot, total_slots)
            if generator
            else int(config.years * (slot + 1) / (total_slots + 1))
        )

        while year > next_epoch <= config.years:
            state.year = next_epoch
            history.snapshot(_snapshot(state, mapper, next_epoch, f"Epocha {epoch_index}"))
            next_epoch += config.epoch_length
            epoch_index += 1

        if generator is None:
            continue

        # Inventář se čte ze skutečného lexikonu po každé změně — generátor tak
        # vidí přesně to, co v jazyce v daném okamžiku je (stavový fold, 4.3).
        inventory = InventoryView.from_lexicon(state.lexicon, mapper)
        rule = generator.generate_one(
            state, year, inventory, previous=previous_rule, accepts=_would_change
        )
        if rule is None:
            continue

        application = RuleApplication(
            year=year,
            node_id=state.node_id,
            rule_name=rule.name,
            target=dict(rule.target),
            action=dict(rule.action),
            env_before=dict(rule.env_before) if rule.env_before else None,
            env_after=dict(rule.env_after) if rule.env_after else None,
            generated=True,
        )

        for word in state.lexicon.words:
            before = mapper.render_word(word)
            if rule.apply_to_word(word):
                after = mapper.render_word(word)
                if after != before:
                    application.changes.append(
                        WordChange(concept_id=word.concept_id, before=before, after=after)
                    )

        history.record(application)
        previous_rule = rule
        state.inventory = InventoryView.from_lexicon(state.lexicon, mapper).to_inventory()

    # Doplnění zbylých epoch až do konce zadaného období.
    while next_epoch <= config.years:
        state.year = next_epoch
        history.snapshot(_snapshot(state, mapper, next_epoch, f"Epocha {epoch_index}"))
        next_epoch += config.epoch_length
        epoch_index += 1

    state.year = config.years
    if not history.snapshots or history.snapshots[-1].year != config.years:
        history.snapshot(_snapshot(state, mapper, config.years, "Současnost"))
    else:
        history.snapshots[-1].label = "Současnost"

    return state, history


def lineage_payload(
    state: State,
    history: SimulationHistory,
    mapper: FeatureMapper,
    diagnostic: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    Serializuje vývoj jedné linie pro drill-down v UI.

    Kromě epoch a seznamu změn nese i derivaci každého slova — tedy odpověď na
    otázku "čím tenhle tvar prošel a kdy".
    """
    node_id = state.node_id
    branch = build_branch_view(state, mapper, diagnostic)

    traces = {
        concept: [step.as_dict() for step in history.trace(node_id, concept)]
        for concept in sorted({w.concept_id for w in state.lexicon.words})
    }

    return {
        "status": "success",
        "node_id": node_id,
        "branch": branch.as_dict(),
        "epochs": [snap.as_dict() for snap in history.snapshots_for(node_id)],
        "events": [event.as_dict() for event in history.events],
        "traces": traces,
    }
