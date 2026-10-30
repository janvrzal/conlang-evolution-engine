#!/usr/bin/env python3
"""Build the reproducible WALS reference profile used by engine v2.

The source checkout is kept outside the repository. Example:
  python scripts/build_v2_typology.py --cldf-dir /tmp/cee-wals-typology/cldf
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

WALS_FEATURE_IDS = (
    "1A", "2A", "10A", "12A", "33A", "37A", "49A", "66A", "67A",
    "81A", "112A", "143A",
)

EXPECTED_SHA256 = {
    "values.csv": "47b85f2f9bc9f26d8c6037886cfa32bd45b7042e5ab8815d5a8bf7d933aaf9f4",
    "languages.csv": "1eaaf032d1d14bcd50c998f5452fde6ba4766043506568dab6e21c31a13d6189",
    "codes.csv": "fbcc50b8ab6a71cb38f64d65fd06f2ee7f1c0fe33fa33c4ae91debbe10980f6d",
    "parameters.csv": "c9bd5960007a0b342bd9cf4206c906f096ff44321a8fa5ba06cc7d57327462b5",
    "StructureDataset-metadata.json": "96f4881b6c29c3349e22f22e4058b6b5025595c03f8cbfb66fb203ba2a8b4307",
}

# Only mappings justified by an observable engine state are included here.
# A list of WALS categories can be coarsened to one engine state where the
# engine cannot represent the distinctions inside that group.
CROSSWALKS: dict[str, dict[str, str]] = {
    "33A": {
        **{f"33A-{number}": "plural_present" for number in range(1, 9)},
        "33A-9": "plural_absent",
    },
    "37A": {
        "37A-1": "definite_present",
        "37A-2": "definite_present",
        "37A-3": "definite_present",
        "37A-4": "definite_absent",
        "37A-5": "definite_absent",
    },
    "66A": {
        "66A-1": "past_present",
        "66A-2": "past_present",
        "66A-3": "past_present",
        "66A-4": "past_absent",
    },
    "67A": {
        # WALS 67A is specifically inflectional future. Periphrastic engine
        # constructions are intentionally not assigned to either side.
        "67A-1": "67A-1",
        "67A-2": "67A-2",
    },
    "143A": {
        "143A-1": "143A-1",
        "143A-2": "143A-2",
        "143A-14": "143A-14",
    },
    "81A": {
        "81A-1": "81A-1",
        "81A-2": "81A-2",
        "81A-3": "81A-3",
        "81A-4": "81A-4",
        "81A-5": "81A-5",
        "81A-6": "81A-6",
        # 81A-7 (no dominant order) is not equivalent to engine ORDER=free.
    },
}

UNSUPPORTED_REASONS = {
    "1A": "WALS measures phoneme inventory size; the engine exposes used surface segments, not a contrastive phoneme inventory.",
    "2A": "WALS measures phonemic vowel-quality inventory size; the engine does not expose that contrastive inventory as a typological state.",
    "10A": "Surface nasal vowels do not establish phonemic/contrastive nasalization or its absence.",
    "12A": "WALS syllable-structure complexity is not represented by an explicit engine grammar state.",
    "49A": "OBJ presence/absence does not determine the language's total morphological case inventory or WALS's case-count category.",
    "112A": "The engine NEG stage does not uniquely encode WALS negative-morpheme types (affix, particle, auxiliary, etc.).",
}

MAPPED_CATEGORY_UNSUPPORTED = {
    "33A": {},
    "37A": {},
    "66A": {},
    "67A": {},
    "143A": {
        **{
            f"143A-{number}": "WALS value does not map unambiguously to engine NEG pre/post/embraced state."
            for number in (*range(3, 14), 15, 16, 17)
        },
    },
    "81A": {"81A-7": "WALS 'no dominant order' is not the same as the engine's free order state."},
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def genus_key(language: dict[str, str]) -> str:
    genus = language.get("Genus", "").strip()
    if genus:
        return genus
    # WALS genera are absent for isolates. Treat each such language as its own
    # unit rather than pooling all isolates into one artificial genus.
    return f"__language__:{language['ID']}"


def weighted_distribution(
    observations: list[tuple[str, str]],
    languages: dict[str, dict[str, str]],
    categories: dict[str, str],
) -> tuple[dict[str, float], Counter[str]]:
    """Return normalized genus-weighted category frequencies and genus sizes."""
    genus_sizes: Counter[str] = Counter()
    for language_id, _ in observations:
        genus_sizes[genus_key(languages[language_id])] += 1
    weighted: defaultdict[str, float] = defaultdict(float)
    for language_id, category_id in observations:
        weighted[category_id] += 1.0 / genus_sizes[genus_key(languages[language_id])]
    total_weight = sum(weighted.values())
    distribution = {
        category_id: weighted[category_id] / total_weight if total_weight else 0.0
        for category_id in sorted(categories)
    }
    return distribution, genus_sizes


def build_reference(root: Path) -> dict[str, Any]:
    """Build A1 data from the verified pinned CLDF files."""
    for name, expected in EXPECTED_SHA256.items():
        actual = sha256(root / name)
        if actual != expected:
            raise ValueError(f"{name} checksum mismatch for pinned WALS v2020.6: {actual}")
    parameters = {row["ID"]: row["Name"] for row in read_csv(root / "parameters.csv")}
    wals_features = {feature_id: parameters[feature_id] for feature_id in WALS_FEATURE_IDS}
    metadata = json.loads((root / "StructureDataset-metadata.json").read_text(encoding="utf-8"))
    languages = {row["ID"]: row for row in read_csv(root / "languages.csv")}
    codes = read_csv(root / "codes.csv")
    all_codes: dict[str, dict[str, str]] = defaultdict(dict)
    for row in codes:
        feature_id = row["Parameter_ID"]
        if feature_id in wals_features:
            all_codes[feature_id][row["ID"]] = row["Name"]

    observations: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in read_csv(root / "values.csv"):
        feature_id = row["Parameter_ID"]
        if feature_id in wals_features and row["Language_ID"] in languages and row["Code_ID"]:
            observations[feature_id].append((row["Language_ID"], row["Code_ID"]))

    features: dict[str, Any] = {}
    for feature_id, feature_name in wals_features.items():
        crosswalk = CROSSWALKS.get(feature_id, {})
        category_labels = all_codes.get(feature_id, {})
        rows = observations.get(feature_id, [])
        distribution, genus_sizes = weighted_distribution(rows, languages, category_labels)
        # Recover unnormalized category weights from the normalized frequencies
        # and the corresponding sample denominator for mapped coverage.
        weighted: defaultdict[str, float] = defaultdict(float)
        if rows:
            for language_id, category_id in rows:
                weighted[category_id] += 1.0 / genus_sizes[genus_key(languages[language_id])]
        total_weight = sum(weighted.values())

        engine_weighted: defaultdict[str, float] = defaultdict(float)
        for category_id, value in weighted.items():
            engine_category = crosswalk.get(category_id)
            if engine_category is not None:
                engine_weighted[engine_category] += value
        mapped_weight = sum(engine_weighted.values())
        engine_distribution = {
            key: value / mapped_weight for key, value in sorted(engine_weighted.items())
        } if mapped_weight else {}

        unsupported = dict(MAPPED_CATEGORY_UNSUPPORTED.get(feature_id, {}))
        if feature_id not in CROSSWALKS:
            unsupported = {
                category_id: UNSUPPORTED_REASONS[feature_id]
                for category_id in sorted(category_labels)
            }
        else:
            for category_id in sorted(category_labels):
                if category_id not in crosswalk:
                    unsupported.setdefault(category_id, f"No unambiguous engine mapping defined for {feature_id}.")

        features[feature_id] = {
            "name": feature_name,
            "categories": {key: category_labels[key] for key in sorted(category_labels)},
            "distribution": distribution,
            "crosswalk": {key: crosswalk.get(key) for key in sorted(category_labels)},
            "engine_categories": sorted(set(crosswalk.values())),
            "engine_distribution": engine_distribution,
            "unsupported": unsupported,
            "coverage": {
                "languages_with_data": len(rows),
                "genera_with_data": len(genus_sizes),
                "mapped_weight_share": mapped_weight / total_weight if total_weight else 0.0,
                "mapped_languages": sum(1 for _, category_id in rows if category_id in crosswalk),
            },
        }

    input_hashes = {name: sha256(root / name) for name in EXPECTED_SHA256}
    source_ref = metadata.get("prov:wasDerivedFrom", [{}])[0]
    return {
        "schema_version": 1,
        "weighting": "Within each feature, each WALS genus contributes total weight 1 split evenly among languages with data; languages without genus are singleton units.",
        "source": {
            "dataset": "World Atlas of Language Structures Online (CLDF StructureDataset)",
            "release": "v2020.6",
            "git_commit": "81298aa26d01fdc11b769bcc7fa87ad9e43d7ccd",
            "repository": "https://github.com/cldf-datasets/wals",
            "release_url": "https://github.com/cldf-datasets/wals/tree/v2020.6",
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "citation": "Dryer, Matthew S. & Haspelmath, Martin (eds.) 2013. The World Atlas of Language Structures Online. Leipzig: Max Planck Institute for Evolutionary Anthropology. WALS Online v2020.6 [Data set]. Zenodo. https://doi.org/10.5281/zenodo.23010827",
            "release_doi": "https://doi.org/10.5281/zenodo.23010827",
            "cldf_metadata_upstream": source_ref,
            "sha256": input_hashes,
        },
        "features": features,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cldf-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("src/cee/data/v2_typology.json"))
    args = parser.parse_args()
    root = args.cldf_dir
    required = ["values.csv", "languages.csv", "codes.csv", "parameters.csv", "StructureDataset-metadata.json"]
    for name in required:
        if not (root / name).is_file():
            parser.error(f"missing CLDF input: {root / name}")

    output = build_reference(root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} ({len(output['features'])} WALS features)")


if __name__ == "__main__":
    main()
