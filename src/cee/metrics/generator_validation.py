"""V2a: profilové srovnání generovaných a doložených zvukových změn."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import sqrt
from typing import Iterable

from cee.engine.rules import Rule

_V2A_CLASS = {
    "apocope": "deletion", "coda_loss": "deletion", "syncope": "deletion",
    "vowel_shift": "vowel_change", "umlaut": "vowel_change", "nasalization": "vowel_change",
    "diphthongization": "vowel_change", "monophthongization": "vowel_change",
}


def _environment(rule: Rule) -> str:
    if rule.env_before or rule.env_after:
        if rule.env_after and rule.env_after.get("_boundary") == "+":
            return "word_final"
        if rule.env_before and rule.env_before.get("_boundary") == "+":
            return "word_initial"
        # Index Redux neodlišuje systematicky levé, pravé a oboustranné
        # segmentové podmínky; pro srovnatelnou osu je spojujeme.
        return "conditioned"
    return "unconditional"


@dataclass(frozen=True)
class GeneratorProfile:
    changes: int
    schemas: dict[str, int]
    environments: dict[str, int]
    changes_per_millennium: float


def profile_rules(rules: Iterable[Rule], years: int, broad: bool = False) -> GeneratorProfile:
    rules = list(rules)
    schema_counts = Counter(
        _V2A_CLASS.get(rule.schema_id or "manual", "consonant_change") if broad else rule.schema_id or "manual"
        for rule in rules
    )
    environment_counts = Counter(_environment(rule) for rule in rules)
    return GeneratorProfile(
        changes=len(rules),
        schemas=dict(sorted(schema_counts.items())),
        environments=dict(sorted(environment_counts.items())),
        changes_per_millennium=len(rules) * 1000 / max(1, years),
    )


def _distribution_distance(left: dict[str, int], right: dict[str, int]) -> float:
    """Hellingerova vzdálenost dvou kategoriálních distribucí (0 až 1)."""
    keys = set(left) | set(right)
    left_total, right_total = sum(left.values()), sum(right.values())
    if not keys or not left_total or not right_total:
        return 1.0
    return sqrt(sum((sqrt(left.get(key, 0) / left_total) - sqrt(right.get(key, 0) / right_total)) ** 2 for key in keys)) / sqrt(2)


def compare_profiles(generated: GeneratorProfile, attested: GeneratorProfile) -> dict[str, float]:
    """Metriky V2a; nižší vzdálenost znamená bližší profil."""
    rate_delta = abs(generated.changes_per_millennium - attested.changes_per_millennium)
    shared = set(generated.schemas) & set(attested.schemas)
    generated_shared = {key: generated.schemas[key] for key in shared}
    attested_shared = {key: attested.schemas[key] for key in shared}
    attested_coverage = sum(attested_shared.values()) / max(1, sum(attested.schemas.values()))
    return {
        "schema_hellinger": _distribution_distance(generated.schemas, attested.schemas),
        "comparable_schema_hellinger": _distribution_distance(generated_shared, attested_shared),
        "attested_schema_coverage": attested_coverage,
        "environment_hellinger": _distribution_distance(generated.environments, attested.environments),
        "rate_delta_per_millennium": rate_delta,
    }
