"""Globální, nesměrované statistiky kognátních korespondencí.

Tato vrstva je oddělená od vah historických schémat: párové formy potomků
neříkají, kterým směrem změna proběhla. Jsou ale silným, globálně dostupným
kontrolním profilem míry shody, substitucí a mezer v kognátech.
"""
from __future__ import annotations

import csv
import hashlib
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from math import sqrt
from pathlib import Path
from typing import Iterable, Iterator, Mapping

from cee.core.models import Word
from cee.engine.phonology import FeatureMapper


@dataclass(frozen=True)
class CorrespondenceProfile:
    source: str
    sha256: str
    forms: int
    cognate_sets: int
    families: int
    compared_pairs: int
    aligned_columns: int
    family_distribution: dict[str, float]
    global_distribution: dict[str, float]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _normalise(counts: Mapping[str, float]) -> dict[str, float]:
    total = sum(counts.values())
    return {name: value / total for name, value in sorted(counts.items())} if total else {}


def _pair_columns(left: str, right: str) -> Iterator[str]:
    """Klasifikuje sloupec dvou předem zarovnaných forem bez směru změny."""
    for left_phone, right_phone in zip(left.split(), right.split()):
        if left_phone == right_phone:
            yield "identity"
        elif left_phone == "-" or right_phone == "-":
            yield "gap"
        else:
            yield "substitution"


def _align_segments(left: list[str], right: list[str]) -> list[tuple[str, str]]:
    """Globální zarovnání pro dvě simulované příbuzné formy."""
    costs = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for index in range(1, len(left) + 1):
        costs[index][0] = index
    for index in range(1, len(right) + 1):
        costs[0][index] = index
    for left_index, left_phone in enumerate(left, 1):
        for right_index, right_phone in enumerate(right, 1):
            substitute = costs[left_index - 1][right_index - 1] + (left_phone != right_phone)
            costs[left_index][right_index] = min(
                substitute,
                costs[left_index - 1][right_index] + 1,
                costs[left_index][right_index - 1] + 1,
            )

    pairs: list[tuple[str, str]] = []
    left_index, right_index = len(left), len(right)
    while left_index or right_index:
        if (
            left_index
            and right_index
            and costs[left_index][right_index]
            == costs[left_index - 1][right_index - 1]
            + (left[left_index - 1] != right[right_index - 1])
        ):
            pairs.append((left[left_index - 1], right[right_index - 1]))
            left_index, right_index = left_index - 1, right_index - 1
        elif (
            left_index
            and costs[left_index][right_index] == costs[left_index - 1][right_index] + 1
        ):
            pairs.append((left[left_index - 1], "-"))
            left_index -= 1
        else:
            pairs.append(("-", right[right_index - 1]))
            right_index -= 1
    return list(reversed(pairs))


def profile_simulated_word_pairs(
    pairs: Iterable[tuple[Word, Word]], mapper: FeatureMapper
) -> dict[str, float]:
    """Profiluje potomky stejného kořene bez vydávání rozdílu za směr změny."""
    counts: Counter[str] = Counter()
    for left_word, right_word in pairs:
        left = [mapper.segment_to_ipa(segment) for segment in left_word.segments]
        right = [mapper.segment_to_ipa(segment) for segment in right_word.segments]
        for left_phone, right_phone in _align_segments(left, right):
            if left_phone == right_phone:
                counts["identity"] += 1
            elif left_phone == "-" or right_phone == "-":
                counts["gap"] += 1
            else:
                counts["substitution"] += 1
    return _normalise(counts)


def correspondence_hellinger(
    observed: Mapping[str, float], target: Mapping[str, float]
) -> float:
    """Vzdálenost simulované a referenční korespondence (0 = shoda)."""
    keys = set(observed) | set(target)
    squared = sum(
        (sqrt(observed.get(key, 0.0)) - sqrt(target.get(key, 0.0))) ** 2 for key in keys
    )
    return sqrt(squared) / sqrt(2)


def build_gled_correspondence_profile(path: str | Path) -> CorrespondenceProfile:
    """Sestaví rodinně vyvážený profil z release TSV databáze GLED.

    GLED je řazený podle ``FAMILY, COGSET, ID``. U každé kognátní sady proto
    porovnáme sousední formy podle ID: jde o lineární, deterministický vzorek
    bez kvadratické převahy velkých kognátních sad a bez privilegované kotvy.
    """
    source = Path(path)
    required = {"FAMILY", "COGSET", "ID", "ALIGNMENT"}
    per_family: dict[str, Counter[str]] = defaultdict(Counter)
    global_counts: Counter[str] = Counter()
    forms = cognate_sets = compared_pairs = aligned_columns = 0
    previous_key: tuple[str, str] | None = None
    previous_alignment: str | None = None

    with source.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"{source} nemá hlavičku TSV.")
        if missing := required - set(reader.fieldnames):
            raise ValueError(f"{source} nemá povinné sloupce: {sorted(missing)}")
        for row in reader:
            forms += 1
            family, cognate_set = row["FAMILY"].strip(), row["COGSET"].strip()
            alignment = row["ALIGNMENT"].strip()
            if not family or not cognate_set or not alignment:
                continue
            key = family, cognate_set
            if key != previous_key:
                cognate_sets += 1
                previous_key, previous_alignment = key, alignment
                continue
            assert previous_alignment is not None
            # Chybné alignmenty nevyrovnáváme za dataset: transparentně je
            # ignorujeme, protože jinak bychom zaváděli vlastní korespondence.
            if len(previous_alignment.split()) == len(alignment.split()):
                categories = list(_pair_columns(previous_alignment, alignment))
                per_family[family].update(categories)
                global_counts.update(categories)
                compared_pairs += 1
                aligned_columns += len(categories)
            previous_alignment = alignment

    family_average: Counter[str] = Counter()
    for counts in per_family.values():
        for category, share in _normalise(counts).items():
            family_average[category] += share
    return CorrespondenceProfile(
        source=str(source),
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        forms=forms,
        cognate_sets=cognate_sets,
        families=len(per_family),
        compared_pairs=compared_pairs,
        aligned_columns=aligned_columns,
        family_distribution=_normalise(family_average),
        global_distribution=_normalise(global_counts),
    )
