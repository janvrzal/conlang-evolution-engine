"""První reprodukovatelný kalibrační běh V2a nad lokální cache Index Diachronica.

Není to ještě románský korpus ani vědecká výstupní brána: měří, zda vážený
generátor produkuje podobnou distribuci *typů* změn jako jeho empirický zdroj.
Chybějící kontexty a chronologie Indexu se do výsledku výslovně zaznamenají.
"""
from __future__ import annotations

import argparse
import json

from cee.core.models import Inventory, Lexicon, State
from cee.engine.empirical import default_paths, load_diachronic_priors
from cee.engine.generator import SoundChangeGenerator
from cee.engine.inventory import InventoryView
from cee.engine.parser import YamlParser
from cee.engine.phonology import FeatureMapper
from cee.metrics.generator_validation import GeneratorProfile, compare_profiles, profile_rules


FORMS = ("pata", "tika", "kuma", "sapi", "moru", "lena", "ratu", "noka")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--rules", type=int, default=12, help="počet slotů na běh za tisíc let")
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--baseline", choices=("raw", "family-balanced"), default="family-balanced")
    args = parser.parse_args()
    if args.runs < 1 or args.rules < 1:
        parser.error("runs i rules musí být kladné")

    mapper = FeatureMapper()
    lexicon = Lexicon(words=[mapper.parse_word(str(i), form) for i, form in enumerate(FORMS)])
    inventory = InventoryView.from_lexicon(lexicon, mapper)
    paths = default_paths(args.cache_dir)
    priors = load_diachronic_priors(paths["diachronica_priors"])
    preset = YamlParser.parse_preset("src/cee/data/presets/fantasy_preset.yaml")

    rules = []
    for seed in range(args.runs):
        generator = SoundChangeGenerator(preset, seed=seed, empirical_priors=priors)
        state = State(node_id=f"v2a-{seed}", year=0, inventory=Inventory(), lexicon=lexicon)
        rules.extend(generator.generate_rules_for_edge(state, 0, 1000, args.rules, inventory))

    generated = profile_rules(rules, years=args.runs * 1000, broad=True)
    annotations = priors.balanced_annotations() if args.baseline == "family-balanced" else priors.annotations
    attested = GeneratorProfile(sum(annotations.values()), annotations, priors.environments, 0.0)
    comparison = compare_profiles(generated, attested)
    print(json.dumps({
        "generated": generated.__dict__,
        "attested": {"changes": sum(annotations.values()), "schemas": annotations, "baseline": args.baseline, "families": sorted(priors.family_annotations), "provenance": priors.provenance},
        "comparison": {
            "schema_hellinger": comparison["schema_hellinger"],
            "comparable_schema_hellinger": comparison["comparable_schema_hellinger"],
            "attested_schema_coverage": comparison["attested_schema_coverage"],
            "environment_hellinger": comparison["environment_hellinger"],
        },
        "limitations": [
            "Index records do not supply a common time denominator; rate comparison is intentionally unavailable.",
            "This is a generator calibration probe, not V2a completion or Romance-family validation.",
        ],
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
