"""Serial, reproducible typology audit; never changes simulation constants.

PYTHONPATH=src python scripts/v2_typology.py --output /tmp/cee-typology-results.json \
    --markdown /tmp/cee-typology-tables.md

The WALS start samples independent grammatical marginals, conditional on
representability. It is not a reconstruction of attested joint grammars.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from importlib.resources import files
from pathlib import Path
from typing import Any

from cee.v2 import metrics
from cee.v2.language.constructions import Construction
from cee.v2.observe import LineageTracker, observe
from cee.v2.rng import generator
from cee.v2.scenarios import SYNTAX_GRAMMAR, village_grid
from cee.v2.simulation import Simulation

YEARS = (0, 1000, 2000, 3000, 5000)
FEATURES = ("33A", "37A", "66A", "67A", "81A", "143A")
ORDERS = {f"81A-{index}": value for index, value in
          enumerate(("SOV", "SVO", "VSO", "VOS", "OVS", "OSV"), 1)}


def load_reference() -> dict[str, Any]:
    return json.loads(files("cee.data").joinpath("v2_typology.json").read_text(encoding="utf-8"))


def sample_grammar(seed: int, reference: dict[str, Any]) -> dict[str, Construction]:
    """One fixed, neutral RNG key per marginal; no outcome-dependent choices.

    OBJ retains its original state; WALS49A does not identify OBJ.
    The NEG double representative is pre+post, although WALS143A-14 also
    includes other obligatory double layouts.
    The absent/non-inflectional representatives are zero; this is explicit
    scenario initialization, not a claim to reconstruct WALS morphology.
    """
    grammar = dict(SYNTAX_GRAMMAR)
    for feature in FEATURES:
        distribution = reference["features"][feature]["engine_distribution"]
        values = sorted(distribution)
        rng = generator(seed, "typology-wals-start", feature)
        value = values[int(rng.choice(len(values), p=[distribution[key] for key in values]))]
        if feature == "33A":
            grammar["PL"] = Construction("PL", "synthetic" if value == "plural_present" else "zero")
        elif feature == "143A":
            kind = {"143A-1": "pre", "143A-2": "post", "143A-14": "embraced"}[value]
            grammar["NEG"] = Construction("NEG", kind, "not", reinforcer="thing" if kind == "embraced" else None)
        elif feature == "37A":
            grammar["DEFINITE"] = (
                Construction("DEFINITE", "periphrastic", "this", stage="free")
                if value == "definite_present" else Construction("DEFINITE", "zero")
            )
        elif feature == "66A":
            grammar["PAST"] = Construction("PAST", "synthetic" if value == "past_present" else "zero")
        elif feature == "67A":
            grammar["FUTURE"] = Construction("FUTURE", "synthetic" if value == "67A-1" else "zero")
        else:
            grammar["ORDER"] = Construction("ORDER", "fixed", order=ORDERS[value])
    return grammar


def projected_reference(feature: dict[str, Any]) -> dict[str, float]:
    """Preserve unsupported WALS mass as its original category, never discard it."""
    result: Counter[str] = Counter()
    for category, probability in feature["distribution"].items():
        result[feature["crosswalk"][category] or category] += probability
    return dict(result)


def capture(simulation: Simulation) -> dict[str, Any]:
    if simulation.year == 0:
        config = simulation.config
        # A separate observer leaves the simulation's lineage tracker untouched.
        snapshot, _ = observe(simulation.world, 0, 0, LineageTracker(),
                              dialect_threshold=config.dialect_threshold,
                              language_threshold=config.language_threshold)
    else:
        snapshot = simulation.snapshots[-1]
        if snapshot.year != simulation.year:
            raise ValueError("A requested measurement must coincide with an observation tick.")
    profiles, surface_profiles, inventories, contrasts = [], [], [], []
    for _, groups in sorted(snapshot.languages.items()):
        profiles.append(metrics.typology_profile(simulation.world, groups))
        surface_profiles.append(metrics.typology_profile(simulation.world, groups, weakness_threshold=0.5))
        inventories.append(metrics.underlying_inventory_proxy(simulation.world, groups))
        witnesses = {group: metrics.nasal_contrast_witness(simulation.world, group) for group in sorted(groups)}
        total = sum(simulation.world.groups[group].population for group in groups)
        witnessed = sum(simulation.world.groups[group].population for group, pair in witnesses.items() if pair is not None)
        contrasts.append({"witness_population_share": witnessed / total if total else 0.0,
                          "majority_witness": witnessed > total / 2 if total else False,
                          "witnesses": {group: pair for group, pair in witnesses.items() if pair is not None}})
    return {
        "year": int(simulation.year),
        "profiles": profiles,
        "surface_profiles": surface_profiles,
        "inventory_proxies": inventories,
        "nasal_contrast_witnesses": contrasts,
    }


def summarize(runs: list[dict[str, Any]], reference: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    readings = ("construction", "surface_contrast")
    for reading in readings:
        profile_key = "profiles" if reading == "construction" else "surface_profiles"
        for experiment in ("same", "wals"):
            selected = [run for run in runs if run["experiment"] == experiment]
            for year in YEARS:
                frames = [frame for run in selected for frame in run["frames"] if frame["year"] == year]
                profiles = [profile for frame in frames for profile in frame.get(profile_key, frame["profiles"])]
                for feature in FEATURES:
                    counts = Counter(profile[feature] for profile in profiles if profile[feature] is not None)
                    known = sum(counts.values())
                    observed = {key: count / known for key, count in sorted(counts.items())} if known else {}
                    expected = projected_reference(reference["features"][feature])
                    rows.append({
                        "reading": reading,
                        "experiment": experiment, "year": year, "feature": feature,
                        "runs": len(selected), "languages": len(profiles), "known": known,
                        "coverage": known / len(profiles) if profiles else 0.0,
                        "counts": dict(sorted(counts.items())), "distribution": observed,
                        "hellinger": metrics.hellinger(observed, expected) if known else None,
                        "entropy": metrics.normalized_entropy(observed, tuple(reference["features"][feature]["engine_categories"])) if known else None,
                    })
    return rows


def markdown_report(rows: list[dict[str, Any]], reference: dict[str, Any]) -> str:
    lines = ["## Naměřená rozložení", "", "H = Hellinger od celé projekce WALS; E = normovaná entropie.",
             "N je počet jazyků, n počet jednoznačně zařazených. Rozložení je podmíněné na n.",
             "Čtení: formální = přítomnost syntetické/opisné konstrukce; povrchové = syntetická kategorie vyžaduje weakness < 0,5.",
             "Nenamapovaná referenční hmotnost zůstává v H; E je normalizována pevně počtem kategorií, které měřidlo umí rozlišit.", ""]
    for experiment in ("same", "wals"):
        for feature in FEATURES:
            expected = projected_reference(reference["features"][feature])
            lines.extend([f"### {experiment}: {feature}", "",
                          "WALS (genusově vážené): " + "; ".join(f"{key}={value:.3f}" for key, value in expected.items()), "",
                          "| Rok | Čtení | N | n | Pokrytí | Rozložení | H | E |",
                          "|---:|---|---:|---:|---:|---|---:|---:|"])
            for year in YEARS:
                matching = [row for row in rows if row["experiment"] == experiment and row["feature"] == feature and row["year"] == year]
                for row in matching:
                    r_label = "formální" if row.get("reading") == "construction" else "povrchové"
                    distribution = "; ".join(f"{key}={value:.3f}" for key, value in row["distribution"].items()) or "neznámé"
                    h = "—" if row["hellinger"] is None else f"{row['hellinger']:.3f}"
                    e = "—" if row["entropy"] is None else f"{row['entropy']:.3f}"
                    lines.append(f"| {row['year']} | {r_label} | {row['languages']} | {row['known']} | {row['coverage']:.3f} | {distribution} | {h} | {e} |")
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--label", default="working-tree", help="model label stored in the result metadata")
    parser.add_argument("--seeds", type=int, default=20, help="consecutive seeds 1..N; audit requires N>=20")
    parser.add_argument("--columns", type=int, default=6)
    args = parser.parse_args()
    if args.seeds < 1 or args.columns < 1:
        parser.error("seeds and columns must be positive")
    reference = load_reference()
    runs: list[dict[str, Any]] = []
    source_root = Path(__file__).resolve().parents[1] / "src" / "cee" / "v2"
    source_digest = hashlib.sha256()
    for source_file in sorted(source_root.rglob("*.py")):
        source_digest.update(str(source_file.relative_to(source_root)).encode("utf-8"))
        source_digest.update(b"\0")
        source_digest.update(source_file.read_bytes())
    metadata = {"model_base": "68d4e54", "model_label": args.label,
                "engine_source_sha256": source_digest.hexdigest(), "seeds": list(range(1, args.seeds + 1)),
                "columns": args.columns, "years": list(YEARS),
                "reference_sha256": hashlib.sha256(files("cee.data").joinpath("v2_typology.json").read_bytes()).hexdigest(),
                "protocol": "serial; pooled observed languages each weight 1; grammatical marginal sampling conditional on support"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for experiment in ("same", "wals"):
        for seed in metadata["seeds"]:
            grammar = dict(SYNTAX_GRAMMAR) if experiment == "same" else sample_grammar(seed, reference)
            started = time.perf_counter()
            world = village_grid(args.columns, seed=seed, syntax=True, semantics=True,
                                 phonology=True, morphology=True, grammar=grammar)
            simulation = Simulation(world)
            frames = [capture(simulation)]
            for year in YEARS[1:]:
                simulation.run(year)
                frames.append(capture(simulation))
            elapsed = time.perf_counter() - started
            run = {"experiment": experiment, "seed": seed, "seconds": elapsed,
                   "grammar": {name: construction.key for name, construction in grammar.items()},
                   "frames": frames, "digest": simulation.history.digest()}
            runs.append(run)
            rows = summarize(runs, reference)
            args.output.write_text(json.dumps({"metadata": metadata, "runs": runs, "summary": rows},
                                             ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"{experiment} seed={seed} {elapsed:.1f}s N={[len(frame['profiles']) for frame in frames]}", flush=True)
    if args.markdown:
        args.markdown.write_text(markdown_report(rows, reference), encoding="utf-8")


if __name__ == "__main__":
    main()
