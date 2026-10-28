"""Metriky realističnosti (specifikace, oddíl Metriky realističnosti)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
import numpy.typing as npt

from cee.v2.history import History
from cee.v2.world import World

FloatArray = npt.NDArray[np.float64]


def logistic_r2(points: Sequence[tuple[float, float]]) -> float | None:
    """Jak dobře průběh šíření sedí na logistickou křivku (metrika 7).

    Přímka se prokládá logitem frekvence v čase (Kroch 1989); R² se pak
    počítá na původní škále frekvencí. Vrací ``None``, pokud je na proložení
    málo bodů mezi 1 % a 99 %.
    """
    times = np.array([point[0] for point in points], dtype=np.float64)
    values = np.array([point[1] for point in points], dtype=np.float64)
    inner = (values > 0.01) & (values < 0.99)
    if inner.sum() < 4 or np.ptp(times[inner]) == 0:
        return None
    slope, intercept = np.polyfit(times[inner], np.log(values[inner] / (1 - values[inner])), 1)
    predicted = 1.0 / (1.0 + np.exp(-(slope * times + intercept)))
    total = float(((values - values.mean()) ** 2).sum())
    if total == 0:
        return None
    return 1.0 - float(((values - predicted) ** 2).sum()) / total


def establishment_fraction(history: History) -> float:
    """Podíl inovací, které se aspoň v jedné skupině ustálily (metrika 8)."""
    innovations = {event["variant"] for event in history.of_kind("innovation")}
    if not innovations:
        return 0.0
    established = {event["variant"] for event in history.of_kind("established")} & innovations
    return len(established) / len(innovations)


@dataclass(frozen=True)
class DistanceFit:
    """Souvislost jazykové a zeměpisné vzdálenosti (metrika 9, Séguyho zákon)."""

    correlation: float
    r2_linear: float
    r2_log: float

    @property
    def sublinear(self) -> bool:
        return self.r2_log >= self.r2_linear


def _r2(x: FloatArray, y: FloatArray) -> float:
    slope, intercept = np.polyfit(x, y, 1)
    total = float(((y - y.mean()) ** 2).sum())
    return 0.0 if total == 0 else 1.0 - float(((y - (slope * x + intercept)) ** 2).sum()) / total


def isolation_by_distance(
    distances: FloatArray, positions: Sequence[tuple[float, float]]
) -> DistanceFit:
    linguistic, geographic = [], []
    for first in range(len(positions)):
        for second in range(first + 1, len(positions)):
            linguistic.append(distances[first, second])
            geographic.append(math.dist(positions[first], positions[second]))
    y = np.array(linguistic, dtype=np.float64)
    x = np.array(geographic, dtype=np.float64)
    correlation = float(np.corrcoef(x, y)[0, 1]) if y.std() > 0 else 0.0
    return DistanceFit(correlation, _r2(x, y), _r2(np.log(x), y))


# --- zvuk (M2, metriky 3–6) ---------------------------------------------


@dataclass(frozen=True)
class LexiconProfile:
    """Povrchová podoba slovní zásoby jedné skupiny."""

    mean_length: float
    consonants: int
    vowels: int
    #: Podíl pojmů, jejichž dominantní slovo zní stejně jako slovo jiného pojmu.
    homophony: float


def lexicon_roots(world: World, group_id: str) -> dict[str, tuple[str, tuple[int, ...]]]:
    """Pojem → (dominantní kořen, povrchový tvar)."""
    from cee.v2.phonology import surface

    result = {}
    for variable_id, variable in sorted(world.variables.items()):
        if variable.kind != "lexical":
            continue
        distribution = world.distribution(group_id, variable_id)
        if distribution is None:
            continue
        morpheme = world.variants[distribution.dominant()[0]].payload.get("morpheme")
        if isinstance(morpheme, str):
            result[variable.key] = (morpheme, surface(world, group_id, morpheme))
    return result


def retention(world: World, group_id: str) -> float:
    """Podíl pojmů, které skupina pořád vyjadřuje zděděným slovem (metrika 1)."""
    kept = total = 0
    for variable_id, variable in world.variables.items():
        if variable.kind != "lexical":
            continue
        distribution = world.distribution(group_id, variable_id)
        if distribution is None:
            continue
        total += 1
        kept += world.variants[distribution.dominant()[0]].origin.change is None
    return kept / total if total else 0.0


def lexicon_profile(world: World, group_id: str) -> LexiconProfile:
    from cee.v2.phonology import lexicon

    table = world.table
    assert table is not None
    forms = list(lexicon(world, group_id).values())
    inventory = {segment for form in forms for segment in form}
    vowels = sum(1 for segment in inventory if table.is_vowel(segment))
    # Homofonie = stejný tvar *různých* kořenů; posun významu (jeden kořen
    # pro dva pojmy) je polysémie, ne homofonie.
    owners: dict[tuple[int, ...], set[str]] = {}
    for concept, (morpheme, form) in lexicon_roots(world, group_id).items():
        owners.setdefault(form, set()).add(morpheme)
    by_form: dict[tuple[int, ...], int] = {}
    for form in forms:
        by_form[form] = by_form.get(form, 0) + 1
    shared = sum(count for form, count in by_form.items() if len(owners.get(form, ())) > 1)
    return LexiconProfile(
        mean_length=float(np.mean([len(form) for form in forms])) if forms else 0.0,
        consonants=len(inventory) - vowels,
        vowels=vowels,
        homophony=shared / len(forms) if forms else 0.0,
    )


#: Pásma velikosti inventáře podle WALS 1A a 2A (Maddieson 2013): souhlásky
#: od „malého“ po „velký“ inventář, samohláskové kvality od 2 do 14. Užší
#: pásma podle PHOIBLE se použijí, až bude jeho cache dostupná v CI.
CONSONANT_BAND = (6, 40)
VOWEL_BAND = (2, 14)


def established_processes(history: History) -> set[str]:
    """Procesní proměnné, které se aspoň v jedné skupině ustálily."""
    return {
        event["variable"] for event in history.of_kind("established")
        if str(event["variable"]).startswith("process:")
    }


def hellinger(observed: dict[str, float], expected: dict[str, float]) -> float:
    """Hellingerova vzdálenost dvou rozdělení (0 = shodná, 1 = disjunktní)."""
    keys = sorted(set(observed) | set(expected))
    p = np.array([observed.get(key, 0.0) for key in keys], dtype=np.float64)
    q = np.array([expected.get(key, 0.0) for key in keys], dtype=np.float64)
    p, q = p / p.sum(), q / q.sum()
    return float(np.sqrt(0.5 * ((np.sqrt(p) - np.sqrt(q)) ** 2).sum()))


# --- morfologie (M3) ------------------------------------------------------


@dataclass(frozen=True)
class MorphologyProfile:
    """Stav paradigmat jedné skupiny."""

    #: Podíl buněk, jejichž kmen se liší od citačního tvaru (alternace).
    alternation: float
    #: Podíl buněk bez koncovky, které se od citačního tvaru liší jen kmenem.
    morphologized: float
    #: Podíl buněk, které zní stejně jako citační tvar (synkretismus).
    syncretism: float
    #: Průměrný podíl produktivní koncovky v buňkách tříd.
    productive_share: float
    #: Podíl buněk s menšinovou koncovkou u častých (≥ 0,5) a vzácných lexémů.
    irregular_frequent: float
    irregular_rare: float


def morphology_profile(world: World, group_id: str) -> MorphologyProfile:
    from cee.v2.morphology import citation_form, class_stats

    code = world.groups[group_id].main_code
    stats = class_stats(world, code)
    cells = alternating = morphologized = syncretic = 0
    irregular: dict[bool, list[bool]] = {True: [], False: []}
    for unit in sorted(code.phonology.vocabulary):
        morpheme = world.morphemes[unit]
        if morpheme.kind != "word" or morpheme.word_class is None or morpheme.cell is None:
            continue
        state = world.unit_of(code, unit)
        citation = citation_form(world, code, unit)
        cells += 1
        alternating += state.stem != citation
        syncretic += state.form == citation
        morphologized += not state.ending and state.form != citation
        frequent = world.morphemes[morpheme.lexeme_id].frequency >= 0.5
        irregular[frequent].append(state.exponent != stats.productive(morpheme.word_class, morpheme.cell))
    shares = [
        counts.most_common(1)[0][1] / sum(counts.values())
        for counts in stats.exponents.values() if counts
    ]
    return MorphologyProfile(
        alternation=alternating / cells if cells else 0.0,
        morphologized=morphologized / cells if cells else 0.0,
        syncretism=syncretic / cells if cells else 0.0,
        productive_share=float(np.mean(shares)) if shares else 0.0,
        irregular_frequent=float(np.mean(irregular[True])) if irregular[True] else 0.0,
        irregular_rare=float(np.mean(irregular[False])) if irregular[False] else 0.0,
    )


def morphological_complexity(world: World, group_id: str) -> float:
    """Podíl tvarů s menšinovou (nepravidelnou) koncovkou buňky (metrika 11).

    Analogie počtu vzorů a nepravidelností, které musí mluvčí znát; s ní
    pracují Lupyan & Dale 2010 a Trudgill 2011.
    """
    return 1.0 - morphology_profile(world, group_id).productive_share


def spearman(first: Sequence[float], second: Sequence[float]) -> float:
    """Spearmanova pořadová korelace (shody dostanou průměrné pořadí)."""

    def ranks(values: Sequence[float]) -> FloatArray:
        array = np.asarray(values, dtype=np.float64)
        order = np.argsort(array, kind="stable")
        result = np.empty(len(array))
        result[order] = np.arange(len(array), dtype=np.float64)
        for value in np.unique(array):
            tied = array == value
            result[tied] = result[tied].mean()
        return result

    a, b = ranks(first), ranks(second)
    if np.ptp(a) == 0 or np.ptp(b) == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def distinctive_variants(
    world: World, group_id: str, reference_id: str, kinds: Sequence[str] = ("lexical", "process", "construction")
) -> dict[str, tuple[str, str]]:
    """Proměnné, ve kterých má skupina jinou převládající variantu než reference.

    Vrací proměnná → (typ, převládající varianta skupiny). Slouží k měření
    stop jazyka po kontaktu (substrát, výpůjčky).
    """
    found: dict[str, tuple[str, str]] = {}
    for variable_id, variable in sorted(world.variables.items()):
        if variable.kind not in kinds:
            continue
        own, other = world.distribution(group_id, variable_id), world.distribution(reference_id, variable_id)
        if own is None or other is None:
            continue
        leader = own.dominant()[0]
        if leader != other.dominant()[0]:
            found[variable_id] = (variable.kind, leader)
    return found


def trace_shares(world: World, group_id: str, variants: dict[str, tuple[str, str]]) -> dict[str, float]:
    """Průměrný podíl daných variant ve skupině podle typu proměnné."""
    shares: dict[str, list[float]] = {}
    for variable_id, (kind, variant) in sorted(variants.items()):
        distribution = world.distribution(group_id, variable_id)
        share = 0.0
        if distribution is not None and variant in distribution.variants:
            share = float(distribution.freqs[distribution.variants.index(variant)])
        shares.setdefault(kind, []).append(share)
    return {kind: float(np.mean(values)) for kind, values in shares.items()}


def code_distance(
    world: World, first: str, second: str, kinds: Sequence[str] = ("lexical", "process", "construction")
) -> dict[str, float]:
    """Vzdálenost dvou kódů podle typu proměnné (scénář S4).

    Pro každou proměnnou je to variační vzdálenost ½ Σ |p − q|; součet za
    typ se dělí počtem lexikálních proměnných, aby typy byly srovnatelné a
    vzdálenost nezávisela na tom, kolik mrtvých inovací svět nasbíral.
    Proměnná, kterou jeden z kódů nemá, se vynechá.
    """
    lexical = sum(variable.kind == "lexical" for variable in world.variables.values())
    totals = {kind: 0.0 for kind in kinds}
    for variable_id, variable in sorted(world.variables.items()):
        if variable.kind not in totals:
            continue
        a, b = world.distribution(first, variable_id), world.distribution(second, variable_id)
        if a is None or b is None:
            continue
        variants = sorted(set(a.variants) | set(b.variants))
        totals[variable.kind] += 0.5 * sum(abs(a.frequency(v) - b.frequency(v)) for v in variants)
    return {kind: total / max(1, lexical) for kind, total in totals.items()}
