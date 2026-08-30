"""Reprodukovatelný benchmark simulátoru bez externích dat.

Měří pouze teplý běh enginu: FeatureMapper i syntetický protolexikon vzniknou
před měřením. Výsledek je JSON, aby šel uložit jako artefakt CI nebo porovnat
mezi commity, ale sám benchmark žádná data do repozitáře nezapisuje.
"""

from __future__ import annotations

import argparse
import copy
import json
import statistics
import time
import tracemalloc

from cee.core.models import Lexicon
from cee.engine.graph_builder import GraphBuilder
from cee.engine.parser import YamlParser
from cee.engine.phonology import FeatureMapper
from cee.engine.topology import EvolutionGraph
from cee.pipeline import SimulationConfig, run_simulation

FORMS = ("pata", "tika", "kuma", "sapi", "moru", "lena", "ratu", "noka")


def build_lexicon(mapper: FeatureMapper, size: int) -> Lexicon:
    """Deterministický slovník různých konceptů, bez závislosti na cache."""
    seed_words = [mapper.parse_word(f"concept-{index}", form) for index, form in enumerate(FORMS)]
    words = []
    for index in range(size):
        word = copy.deepcopy(seed_words[index % len(seed_words)])
        word.concept_id = f"concept-{index:04d}"
        words.append(word)
    return Lexicon(words=words)


def run_once(
    mapper: FeatureMapper, lexicon: Lexicon, years: int, genealogy: bool
) -> tuple[float, float, int]:
    graph = EvolutionGraph(node_configs={"proto": {"map": {"biome": "none"}}})
    config = SimulationConfig(
        preset=YamlParser.parse_preset("src/cee/data/presets/fantasy_preset.yaml"),
        root_id="proto",
        years=years,
        evolve_root=True,
        enable_semantics=False,
        use_empirical_phonology=False,
    )
    builder = GraphBuilder() if genealogy else None
    tracemalloc.start()
    started = time.perf_counter()
    run_simulation(copy.deepcopy(lexicon), graph, mapper, config, builder)
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    event_count = len(builder.events) if builder else 0
    return elapsed, peak / (1024 * 1024), event_count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lexemes", type=int, default=2000)
    parser.add_argument("--years", type=int, default=1000)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--genealogy", action="store_true")
    args = parser.parse_args()
    if args.lexemes < 1 or args.repetitions < 1 or args.years < 1:
        parser.error("lexemes, years i repetitions musí být kladné")

    mapper = FeatureMapper()
    lexicon = build_lexicon(mapper, args.lexemes)
    runs = [run_once(mapper, lexicon, args.years, args.genealogy) for _ in range(args.repetitions)]
    elapsed, memory, events = zip(*runs)
    print(
        json.dumps(
            {
                "lexemes": args.lexemes,
                "years": args.years,
                "repetitions": args.repetitions,
                "genealogy": args.genealogy,
                "median_seconds": round(statistics.median(elapsed), 4),
                "max_peak_mib": round(max(memory), 2),
                "event_count": max(events),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
