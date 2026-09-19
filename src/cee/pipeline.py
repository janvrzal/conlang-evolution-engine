"""
Servisní vrstva mezi enginem a jeho rozhraními.

CLI i HTTP API potřebují tutéž sekvenci: postav lexikon, poskládej graf, spusť
simulátor, serializuj výsledek. Držet ji na jednom místě znamená, že se obě
rozhraní chovají stejně — dřív existovala ve třech kopiích, které se lišily
(např. jen jedna z nich předávala seed).
"""

from __future__ import annotations

import csv
import json
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from cee.core.models import Inventory, Lexicon, State
from cee.engine.empirical import (
    PhoibleInventoryModel,
    load_phoible_model,
)
from cee.engine.empirical import (
    default_paths as default_empirical_paths,
)
from cee.engine.graph_builder import GraphBuilder
from cee.engine.inventory import InventoryView
from cee.engine.lexicon import annotate_basic_lexical_class
from cee.engine.phonology import FeatureMapper
from cee.engine.semantics import SemanticEvaluator
from cee.engine.simulator import EvolutionSimulator
from cee.engine.topology import EvolutionGraph
from cee.metrics.global_baseline import load_global_baseline
from cee.metrics.retention import LexicalRetention, RetentionResult
from cee.semantics.retention import ConceptRetentionModel, default_concepticon_retention_path
from cee.metrics.schema_profiles import load_local_schema_profile, load_schema_profile
from cee.semantics.builder import default_paths as default_semantics_paths
from cee.semantics.concepts import (
    ConcepticonIndex,
    annotate_concept_metadata,
)
from cee.semantics.concepts import (
    default_path as default_concepticon_path,
)
from cee.semantics.graph import SemanticGraph

DEFAULT_SEED = 42
DEFAULT_SHIFT_PROB = 0.3
DEFAULT_FORGET_PROB = 0.05


@dataclass
class SimulationConfig:
    """Vše, co odlišuje jeden běh od druhého. Stejná konfigurace = stejný výsledek."""

    preset: Optional[Dict[str, Any]] = None
    semantics_path: Optional[str] = None
    #: Benchmarky a specializované běhy mohou sémantickou vrstvu výslovně
    #: vypnout; běžná simulace ji nadále používá.
    enable_semantics: bool = True
    seed: int = DEFAULT_SEED
    shift_prob: float = DEFAULT_SHIFT_PROB
    forget_prob: float = DEFAULT_FORGET_PROB
    #: Explicitní mechanismy přesně zadaných hran, např.
    #: {"hand->eat": "metonymy"}. Neoznačené hrany se neklasifikují odhadem.
    semantic_mechanism_overrides: Dict[str, str] = field(default_factory=dict)
    #: Strukturální evidence pro ručně zadané mechanismy, např.
    #: {"hand->eat": {"bridge": "instrument_action"}}.
    semantic_relation_overrides: Dict[str, Dict[str, str]] = field(default_factory=dict)
    concepticon_path: Optional[str] = None
    #: Volitelná tabulka naměřené retence podle Concepticon ID/glosu.
    retention_prior_path: Optional[str] = None
    root_id: str = "proto"
    root_year: int = 0

    #: Časová hloubka simulace. Bez ní se generují pravidla jen na 200 let.
    years: Optional[int] = None
    #: UI může chtít sledovat i proměnu kořenového protojazyka, nejen větví.
    evolve_root: bool = False
    #: PHOIBLE je opt-in lokální kontrola inventáře; síť se při simulaci nepoužívá.
    use_empirical_phonology: bool = False
    phoible_model_path: Optional[str] = None
    #: Cesta k auditovatelné globální kalibraci. Bez ní zůstává čistý preset.
    global_baseline_path: Optional[str] = None
    schema_profile_id: str = "heuristic-default"
    local_schema_profile_path: Optional[str] = None
    #: Přímé ovladače UI; přebijí profil, ale ne konfiguraci konkrétní větve.
    macro_overrides: Dict[str, float] = field(default_factory=dict)
    lexical_overrides: Dict[str, float] = field(default_factory=dict)


@dataclass
class WordView:
    id: str
    ipa: str
    ipa_prosodic: str = ""
    polysemy: List[str] = field(default_factory=list)
    origin_year: int = 0
    source_id: Optional[str] = None
    frequency: float = 0.5
    active: bool = True
    origin_type: str = "inherited"
    stress_index: Optional[int] = None
    long_nuclei: List[int] = field(default_factory=list)
    morpheme_boundaries: List[int] = field(default_factory=list)
    paradigm: Optional[str] = None
    grammatical_features: Dict[str, str] = field(default_factory=dict)
    is_grammatical: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ipa": self.ipa,
            "ipa_prosodic": self.ipa_prosodic,
            "polysemy": self.polysemy,
            "origin_year": self.origin_year,
            "source_id": self.source_id,
            "frequency": self.frequency,
            "active": self.active,
            "origin_type": self.origin_type,
            "stress_index": self.stress_index,
            "long_nuclei": self.long_nuclei,
            "morpheme_boundaries": self.morpheme_boundaries,
            "paradigm": self.paradigm,
            "grammatical_features": self.grammatical_features,
            "is_grammatical": self.is_grammatical,
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


_concepticon_index_cache: Dict[str, Optional[ConcepticonIndex]] = {}
_retention_model_cache: Dict[str, Optional[ConceptRetentionModel]] = {}


def resolve_concepticon_index(path: Optional[str] = None) -> Optional[ConcepticonIndex]:
    """Načte lokální cache Concepticonu; absence nikdy nezastaví simulaci."""
    resolved = path or default_concepticon_path()
    if resolved not in _concepticon_index_cache:
        try:
            _concepticon_index_cache[resolved] = (
                ConcepticonIndex.from_tsv(resolved) if os.path.exists(resolved) else None
            )
        except (OSError, csv.Error, UnicodeError) as exc:
            warnings.warn(f"Concepticon se nepodařilo načíst ({exc}); používám fallback.", stacklevel=2)
            _concepticon_index_cache[resolved] = None
    return _concepticon_index_cache[resolved]


def resolve_retention_model(path: Optional[str] = None) -> Optional[ConceptRetentionModel]:
    """Načte volitelný retenční korpus; jeho absence nikdy nebortí běh."""
    default = default_concepticon_retention_path()
    resolved = path or os.environ.get("CEE_RETENTION_PRIORS_PATH", "") or (
        str(default) if default.is_file() else ""
    )
    if not resolved:
        return None
    if resolved not in _retention_model_cache:
        try:
            _retention_model_cache[resolved] = ConceptRetentionModel.from_table(resolved)
        except (OSError, ValueError, csv.Error, UnicodeError) as exc:
            warnings.warn(f"Retenční korpus se nepodařilo načíst ({exc}); používám heuristiku.", stacklevel=2)
            _retention_model_cache[resolved] = None
    return _retention_model_cache[resolved]


def load_lexicon_from_csv(
    path: str, mapper: FeatureMapper, *, concepticon_index: Optional[ConcepticonIndex] = None,
    retention_model: Optional[ConceptRetentionModel] = None,
) -> Lexicon:
    """Načte proto-lexikon z CSV se sloupci `id` a `ipa_proto` (nebo `ipa`)."""
    lexicon = Lexicon()
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ipa = row.get("ipa_proto") or row.get("ipa")
            if not ipa:
                warnings.warn(
                    f"Řádek {row.get('id')!r} v {path} nemá IPA, přeskakuji.", stacklevel=2
                )
                continue
            word = mapper.parse_word(concept_id=row["id"], ipa_string=ipa)
            for csv_column, feature_key in (
                ("part_of_speech", "lexical.pos"),
                ("semantic_domains", "lexical.domains"),
                ("register", "lexical.register"),
                ("lexical_class", "lexical.class"),
            ):
                if row.get(csv_column, "").strip():
                    word.grammatical_features[feature_key] = row[csv_column].strip()
            annotate_concept_metadata(word, concepticon_index or resolve_concepticon_index())
            annotate_basic_lexical_class(word)
            if row.get("frequency", "").strip():
                word.frequency = float(row["frequency"])
            lexicon.words.append(word)
    model = retention_model or resolve_retention_model()
    if model is not None:
        model.annotate(lexicon)
    return lexicon


def load_lexicon_from_records(
    records: Iterable[Dict[str, str]], mapper: FeatureMapper, *,
    concepticon_index: Optional[ConcepticonIndex] = None,
    retention_model: Optional[ConceptRetentionModel] = None,
) -> Lexicon:
    """Načte proto-lexikon z JSON záznamů, jak je posílá UI."""
    lexicon = Lexicon()
    for record in records:
        lexicon.words.append(
            mapper.parse_word(
                concept_id=record["id"],
                ipa_string=record["ipa"],
                is_grammatical=bool(record.get("is_grammatical", False)),
            )
        )
        word = lexicon.words[-1]
        word.polysemy = set(record.get("polysemy", []))
        word.grammatical_features = dict(record.get("grammatical_features", {}))
        if record.get("lexical_class"):
            word.grammatical_features["lexical.class"] = str(record["lexical_class"])
        annotate_concept_metadata(word, concepticon_index or resolve_concepticon_index())
        annotate_basic_lexical_class(word)
        if record.get("frequency") is not None:
            word.frequency = float(record["frequency"])
    model = retention_model or resolve_retention_model()
    if model is not None:
        model.annotate(lexicon)
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
    if not config.enable_semantics:
        return None
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
                f"Sémantický graf '{path}' se nepodařilo načíst ({type(exc).__name__}): {exc}",
                stacklevel=2,
            )
            return None

    return SemanticEvaluator(
        _semantic_graph_cache[path],
        shift_prob=config.shift_prob,
        forget_prob=config.forget_prob,
        seed=config.seed,
        mechanism_overrides=config.semantic_mechanism_overrides,
        relation_overrides=config.semantic_relation_overrides,
        concept_index=resolve_concepticon_index(config.concepticon_path),
    )


def build_empirical_phonology(
    config: SimulationConfig,
) -> Optional[PhoibleInventoryModel]:
    """Načte volitelný PHOIBLE validátor, nikdy nic nestahuje.

    Neúplná cache není chyba běhu: autorův preset zůstává platný fallback.
    Zároveň ale poškozený cache soubor nezamlčíme, aby byl výsledek dohledatelný.
    """
    if not config.use_empirical_phonology:
        return None

    locations = default_empirical_paths()
    model_path = (
        Path(config.phoible_model_path) if config.phoible_model_path else locations["phoible_model"]
    )
    model: Optional[PhoibleInventoryModel] = None
    if model_path.exists():
        try:
            model = load_phoible_model(model_path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            warnings.warn(f"PHOIBLE model '{model_path}' nelze načíst: {exc}", stacklevel=2)
    return model


def build_global_schema_multipliers(config: SimulationConfig) -> Dict[str, float]:
    """Načte už vytvořenou globální kalibraci, bez síťového I/O."""
    if not config.global_baseline_path:
        try:
            if config.local_schema_profile_path:
                return load_local_schema_profile(config.local_schema_profile_path).schema_multipliers
            return load_schema_profile(config.schema_profile_id).schema_multipliers
        except (OSError, ValueError, KeyError, FileNotFoundError) as exc:
            warnings.warn(f"Profil vah '{config.schema_profile_id}' nelze načíst: {exc}", stacklevel=2)
            return {}
    path = Path(config.global_baseline_path)
    if not path.exists():
        warnings.warn(
            f"Globální baseline '{path}' neexistuje; používám preset bez kalibrace.",
            stacklevel=2,
        )
        return {}
    try:
        return load_global_baseline(path).schema_multipliers
    except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError) as exc:
        warnings.warn(f"Globální baseline '{path}' nelze načíst: {exc}", stacklevel=2)
        return {}


def _load_configured_schema_profile(config: SimulationConfig):
    if config.local_schema_profile_path:
        return load_local_schema_profile(config.local_schema_profile_path)
    return load_schema_profile(config.schema_profile_id)


def build_profile_macro(config: SimulationConfig) -> Dict[str, float]:
    """Makro-prior vestavěného/uživatelského profilu, bez přebití uzlu."""
    if config.global_baseline_path:
        return {}
    try:
        return {**_load_configured_schema_profile(config).macro, **config.macro_overrides}
    except (OSError, ValueError, KeyError, FileNotFoundError) as exc:
        warnings.warn(f"Profil makra '{config.schema_profile_id}' nelze načíst: {exc}", stacklevel=2)
        return {}


def build_profile_lexical(config: SimulationConfig) -> Dict[str, float]:
    """Lexikální prior profilu; konfigurace konkrétního uzlu má vždy přednost."""
    if config.global_baseline_path:
        return {}
    try:
        return {**_load_configured_schema_profile(config).lexical, **config.lexical_overrides}
    except (OSError, ValueError, KeyError, FileNotFoundError) as exc:
        warnings.warn(f"Lexikální profil '{config.schema_profile_id}' nelze načíst: {exc}", stacklevel=2)
        return {}


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
    inventory_validator = build_empirical_phonology(config)
    schema_multipliers = build_global_schema_multipliers(config)
    profile_macro = build_profile_macro(config)
    profile_lexical = build_profile_lexical(config)

    simulator = EvolutionSimulator(
        graph,
        mapper,
        preset=config.preset or {},
        seed=config.seed,
        semantic_evaluator=build_semantic_evaluator(config),
        end_year=config.years,
        graph_builder=graph_builder,
        evolve_root=config.evolve_root,
        inventory_validator=inventory_validator,
        schema_multipliers=schema_multipliers,
        profile_macro=profile_macro,
        profile_lexical=profile_lexical,
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

    if state.social or state.population.size or state.communities:
        labels = {
            "prestige": "prestiž",
            "mobility": "mobilita",
            "literacy": "gramotnost",
            "standardization": "standardizace",
            "population": "populace",
        }
        social = ", ".join(
            f"{labels.get(key, key)} {value:.0%}" for key, value in sorted(state.social.items())
        )
        lines += ["", "## Společnost", "", f"- {social}" if social else "- bez globálních parametrů"]
        if state.population.size or state.population.area:
            lines.append(
                "- Populace: "
                f"{state.population.size or 'neurčena'}; rozloha {state.population.area or 'neurčena'}; "
                f"centra {state.population.centers}"
            )
        if state.communities:
            lines.append("- Komunity: " + ", ".join(sorted(state.communities)))

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
            ipa_prosodic=mapper.render_word_prosodic(word),
            polysemy=sorted(word.polysemy),
            origin_year=word.origin_year,
            source_id=word.source_id,
            frequency=word.frequency,
            active=word.active,
            origin_type=word.origin_type,
            stress_index=word.stress_index,
            long_nuclei=sorted(word.long_nuclei),
            morpheme_boundaries=sorted(word.morpheme_boundaries),
            paradigm=word.paradigm,
            grammatical_features=dict(word.grammatical_features),
            is_grammatical=word.is_grammatical,
        )
        for word in state.lexicon.words
    ]

    retention = (
        LexicalRetention.evaluate(state.lexicon, diagnostic) if diagnostic is not None else None
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
        node_id: build_branch_view(state, mapper, diagnostic) for node_id, state in states.items()
    }


def topology_payload(graph: EvolutionGraph) -> Dict[str, Any]:
    return {
        "nodes": [{"id": node_id} for node_id in graph.node_configs],
        "edges": [
            {"source": edge.parent_id, "target": edge.child_id} for edge in graph.vertical_edges
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
