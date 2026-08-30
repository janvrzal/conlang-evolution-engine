"""Měření vlastností současných jazyků pro outcome-calibration.

Vstupem jsou lokální CSV v běžném CLDF tvaru. Tato vrstva nemodeluje ani
neodhaduje historické změny: zjišťuje, jaké rozmezí vlastností má zvolený
pozorovaný vzorek jazyků.
"""

from __future__ import annotations

import csv
import hashlib
import math
import random
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping

from cee.core.models import State
from cee.engine.phonology import FeatureMapper

_LANGUAGE_ID = "Language_ID"
_FORM_COLUMNS = ("Segments", "Value", "Form")
_CONCEPT_COLUMNS = ("Parameter_ID", "Concept_ID", "Concept")


@dataclass(frozen=True)
class LanguageOutcome:
    language_id: str
    family_id: str
    macroarea: str
    forms: int
    metrics: dict[str, float]


@dataclass(frozen=True)
class MetricEstimate:
    mean: float
    median: float
    standard_deviation: float
    interval_95: tuple[float, float] | None
    observations: int

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["interval_95"] = list(self.interval_95) if self.interval_95 else None
        return payload


@dataclass(frozen=True)
class OutcomeGroup:
    kind: str
    id: str
    languages: int
    families: int
    metrics: dict[str, MetricEstimate]

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "id": self.id,
            "languages": self.languages,
            "families": self.families,
            "metrics": {name: metric.as_dict() for name, metric in self.metrics.items()},
        }


@dataclass(frozen=True)
class OutcomeProfile:
    source_checksums: dict[str, str]
    bootstrap_replicates: int
    bootstrap_seed: int
    excluded_forms: int
    groups: list[OutcomeGroup]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "source_checksums": self.source_checksums,
            "bootstrap_replicates": self.bootstrap_replicates,
            "bootstrap_seed": self.bootstrap_seed,
            "excluded_forms": self.excluded_forms,
            "groups": [group.as_dict() for group in self.groups],
        }


def _iter_csv(path: str | Path):
    source = Path(path)
    with source.open(encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def _first_present(row: Mapping[str, str], columns: Iterable[str]) -> str:
    return next((row.get(column, "").strip() for column in columns if row.get(column, "").strip()), "")


def _segments(
    value: str, mapper: FeatureMapper, cache: dict[str, tuple[dict[str, str], ...]]
) -> list[dict[str, str]]:
    """Přečte CLDF segmenty nebo IPA a zahodí formu bez interpretovatelných segmentů."""
    units = value.split() if " " in value.strip() else [value]
    result: list[dict[str, str]] = []
    for unit in units:
        if unit not in cache:
            cache[unit] = tuple(
                segment.features for segment in mapper.parse_word("outcome", unit).segments
            )
        result.extend(cache[unit])
    return result


def _mean(values: Iterable[float]) -> float:
    rows = list(values)
    return sum(rows) / len(rows) if rows else 0.0


def _word_metrics(
    forms: list[tuple[str, str]],
    mapper: FeatureMapper,
    segment_cache: dict[str, tuple[dict[str, str], ...]],
) -> tuple[dict[str, float], int]:
    """Metriky wordlistu; homofonie je bez frekvence pouze proxy."""
    parsed: list[tuple[str, str, list[dict[str, str]]]] = []
    excluded = 0
    for concept, value in forms:
        segments = _segments(value, mapper, segment_cache)
        if not segments:
            excluded += 1
            continue
        parsed.append((concept, value, segments))
    if not parsed:
        return {}, excluded

    lengths = [len(segments) for _, _, segments in parsed]
    inventories = {
        tuple(sorted(features.items())) for _, _, segments in parsed for features in segments
    }
    consonant_runs = []
    coda_segments = 0
    for _, _, segments in parsed:
        run = longest = 0
        for features in segments:
            if features.get("syl") == "+":
                run = 0
            else:
                run += 1
                longest = max(longest, run)
        consonant_runs.append(longest)
        last_vowel = max(
            (index for index, features in enumerate(segments) if features.get("syl") == "+"),
            default=len(segments) - 1,
        )
        coda_segments += max(0, len(segments) - last_vowel - 1)

    concepts_by_form: dict[str, set[str]] = defaultdict(set)
    for concept, value, _ in parsed:
        concepts_by_form[value].add(concept)
    colliding_concepts = sum(
        len(concepts) for concepts in concepts_by_form.values() if len(concepts) > 1
    )
    form_count = len(parsed)
    return {
        "mean_segment_length": _mean(lengths),
        "median_segment_length": float(statistics.median(lengths)),
        "inventory_size_from_wordlist": float(len(inventories)),
        "mean_max_consonant_run": _mean(consonant_runs),
        "coda_segment_rate": coda_segments / sum(lengths),
        "wordlist_homophony_rate": colliding_concepts / form_count,
    }, excluded


def _phoible_sizes(path: str | Path) -> dict[str, float]:
    """Vrátí medián velikosti nemarginálních inventářů pro glottocode."""
    inventories: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in _iter_csv(path):
        glottocode = row.get("Glottocode", "").strip()
        inventory_id = row.get("InventoryID", "").strip()
        phoneme = row.get("Phoneme", "").strip()
        if not glottocode or not inventory_id or not phoneme:
            continue
        if row.get("Marginal", "").strip().lower() in {"true", "1", "yes"}:
            continue
        inventories[glottocode, inventory_id].add(phoneme)
    per_language: dict[str, list[int]] = defaultdict(list)
    for (glottocode, _), phonemes in inventories.items():
        per_language[glottocode].append(len(phonemes))
    return {
        glottocode: float(statistics.median(sizes))
        for glottocode, sizes in per_language.items()
        if sizes
    }


def measure_language_outcomes(
    forms_path: str | Path,
    languages_path: str | Path,
    phoible_path: str | Path | None = None,
    include_proto: bool = False,
) -> tuple[list[LanguageOutcome], int]:
    """Vytvoří language-level metriky z CLDF-like forms a languages CSV."""
    language_rows = list(_iter_csv(languages_path))
    languages = {
        row.get("ID", "").strip(): {
            "family": row.get("Family", row.get("Family_ID", "")).strip(),
            "macroarea": row.get("Macroarea", row.get("Macroarea_ID", "")).strip(),
            "glottocode": row.get("Glottocode", row.get("glottocode", "")).strip(),
            "is_proto": row.get("Is_Proto", "").strip().lower() in {"true", "1", "yes"},
        }
        for row in language_rows
        if row.get("ID", "").strip()
    }
    if not languages:
        raise ValueError("languages.csv musí obsahovat sloupec ID.")

    per_language: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in _iter_csv(forms_path):
        language_id = row.get(_LANGUAGE_ID, "").strip()
        if language_id not in languages or (languages[language_id]["is_proto"] and not include_proto):
            continue
        value = _first_present(row, _FORM_COLUMNS)
        if value:
            per_language[language_id].append((_first_present(row, _CONCEPT_COLUMNS), value))
    if not per_language:
        raise ValueError("forms.csv neobsahuje žádné formy s Language_ID z languages.csv.")

    mapper = FeatureMapper()
    segment_cache: dict[str, tuple[dict[str, str], ...]] = {}
    phoible_sizes = _phoible_sizes(phoible_path) if phoible_path else {}
    outcomes: list[LanguageOutcome] = []
    excluded = 0
    for language_id, forms in sorted(per_language.items()):
        metrics, skipped = _word_metrics(forms, mapper, segment_cache)
        excluded += skipped
        if metrics:
            metadata = languages[language_id]
            if metadata["glottocode"] in phoible_sizes:
                metrics["phoible_inventory_size"] = phoible_sizes[metadata["glottocode"]]
            outcomes.append(
                LanguageOutcome(
                    language_id=language_id,
                    family_id=metadata["family"],
                    macroarea=metadata["macroarea"],
                    forms=len(forms),
                    metrics=metrics,
                )
            )
    if not outcomes:
        raise ValueError("Žádná forma nešla segmentovat jako IPA nebo CLDF segmenty.")
    return outcomes, excluded


def measure_state_outcome(state: State, mapper: FeatureMapper) -> dict[str, float]:
    """Změří simulovaný stav stejnými lexikálními proxy jako pozorovaný jazyk."""
    forms = [
        (word.concept_id, mapper.render_word(word))
        for word in state.lexicon.words
        if word.active
    ]
    metrics, _ = _word_metrics(forms, mapper, {})
    return metrics


def _percentile(values: list[float], proportion: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * proportion
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _bootstrap_mean(
    rows: list[LanguageOutcome],
    metric: str,
    cluster: Callable[[LanguageOutcome], str],
    replicates: int,
    rng: random.Random,
) -> tuple[float, float] | None:
    clusters: dict[str, list[LanguageOutcome]] = defaultdict(list)
    for row in rows:
        clusters[cluster(row)].append(row)
    keys = sorted(clusters)
    if len(keys) < 2:
        return None
    samples = []
    for _ in range(replicates):
        draw = [clusters[rng.choice(keys)] for _ in keys]
        samples.append(_mean(item.metrics[metric] for members in draw for item in members))
    return _percentile(samples, 0.025), _percentile(samples, 0.975)


def _estimate_group(
    kind: str,
    group_id: str,
    rows: list[LanguageOutcome],
    cluster: Callable[[LanguageOutcome], str],
    replicates: int,
    seed: int,
) -> OutcomeGroup:
    metric_names = sorted({metric for row in rows for metric in row.metrics})
    metrics = {}
    for offset, metric in enumerate(metric_names):
        metric_rows = [row for row in rows if metric in row.metrics]
        values = [row.metrics[metric] for row in metric_rows]
        metrics[metric] = MetricEstimate(
            mean=_mean(values),
            median=float(statistics.median(values)),
            standard_deviation=statistics.stdev(values) if len(values) > 1 else 0.0,
            interval_95=_bootstrap_mean(
                metric_rows, metric, cluster, replicates, random.Random(seed + offset)
            ),
            observations=len(values),
        )
    return OutcomeGroup(
        kind=kind,
        id=group_id,
        languages=len(rows),
        families=len({row.family_id for row in rows if row.family_id}),
        metrics=metrics,
    )


def build_outcome_profile(
    forms_path: str | Path,
    languages_path: str | Path,
    phoible_path: str | Path | None = None,
    bootstrap_replicates: int = 1_000,
    bootstrap_seed: int = 42,
    include_proto: bool = False,
) -> OutcomeProfile:
    """Agreguje outcome metriky s cluster bootstrapem podle genealogie."""
    if bootstrap_replicates < 100:
        raise ValueError("Pro interval 95 % použij alespoň 100 bootstrap opakování.")
    outcomes, excluded = measure_language_outcomes(
        forms_path, languages_path, phoible_path, include_proto
    )
    groups = [
        _estimate_group(
            "global",
            "global",
            outcomes,
            lambda row: row.family_id or f"language:{row.language_id}",
            bootstrap_replicates,
            bootstrap_seed,
        )
    ]
    by_macroarea: dict[str, list[LanguageOutcome]] = defaultdict(list)
    by_family: dict[str, list[LanguageOutcome]] = defaultdict(list)
    for outcome in outcomes:
        if outcome.macroarea:
            by_macroarea[outcome.macroarea].append(outcome)
        if outcome.family_id:
            by_family[outcome.family_id].append(outcome)
    groups.extend(
        _estimate_group(
            "macroarea",
            macroarea,
            rows,
            lambda row: row.family_id or f"language:{row.language_id}",
            bootstrap_replicates,
            bootstrap_seed,
        )
        for macroarea, rows in sorted(by_macroarea.items())
    )
    groups.extend(
        _estimate_group(
            "family", family, rows, lambda row: row.language_id,
            bootstrap_replicates, bootstrap_seed,
        )
        for family, rows in sorted(by_family.items())
    )
    sources = {"forms": Path(forms_path), "languages": Path(languages_path)}
    if phoible_path:
        sources["phoible"] = Path(phoible_path)
    return OutcomeProfile(
        source_checksums={
            name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in sources.items()
        },
        bootstrap_replicates=bootstrap_replicates,
        bootstrap_seed=bootstrap_seed,
        excluded_forms=excluded,
        groups=groups,
    )
