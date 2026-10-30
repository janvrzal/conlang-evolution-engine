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


def normalized_entropy(distribution: dict[str, float], categories: Sequence[str]) -> float:
    """Shannonova entropie dělená logaritmem počtu možných kategorií.

    Prázdný vzorek nemá definovanou entropii a vyvolá ValueError. Nulové
    kategorie se započítávají do normalizace, nikoli do logaritmu podílu.
    """
    if len(set(categories)) != len(categories) or not categories:
        raise ValueError("Kategorie musí být neprázdné a jedinečné.")
    if any(value < 0 or not math.isfinite(value) for value in distribution.values()):
        raise ValueError("Četnosti musí být konečné a nezáporné.")
    if set(distribution) - set(categories):
        raise ValueError("Rozdělení obsahuje neznámou kategorii.")
    total = sum(distribution.values())
    if total <= 0:
        raise ValueError("Prázdné rozdělení nemá entropii.")
    if len(categories) == 1:
        return 0.0
    return -sum((value / total) * math.log(value / total)
                for value in distribution.values() if value > 0) / math.log(len(categories))


def typology_profile(world: World, language: Sequence[str]) -> dict[str, str | None]:
    """Převládající typologické kategorie pozorovaného jazyka.

    ``language`` je posloupnost ID skupin z ``Snapshot.languages``, nikoli
    genealogická linie ``Code.language``. Hlasy skupin váží populace a celé
    rozdělení variant, nikoli jen lokální vítěz. Nerozlišitelné kategorie
    mají hodnotu None; psané skupiny bez mluvčích se nezapočítají.
    37A a 66A používají hrubší, výslovně odvozené kategorie.
    """
    from cee.v2.syntax import construction_of, variable_id

    groups = [world.groups[group_id] for group_id in sorted(set(language))
              if not world.groups[group_id].written and world.groups[group_id].domain == "home"
              and world.groups[group_id].population > 0]
    features = {"33A": "PL", "37A": "DEFINITE", "66A": "PAST", "67A": "FUTURE",
                "81A": "ORDER", "143A": "NEG"}
    order_values = {"SOV": "81A-1", "SVO": "81A-2", "VSO": "81A-3",
                    "VOS": "81A-4", "OVS": "81A-5", "OSV": "81A-6"}
    result: dict[str, str | None] = {}
    for feature, function in features.items():
        totals: dict[str | None, float] = {}
        variable = variable_id(function)
        for group in groups:
            distribution = world.distribution(group.id, variable)
            if distribution is None:
                # Funkce vynechaná z profilu se nevyjadřuje a nemůže inovovat.
                absent = {"33A": "plural_absent", "37A": "definite_absent",
                          "66A": "past_absent", "67A": "67A-2"}.get(feature)
                totals[absent] = totals.get(absent, 0.0) + group.population
                continue
            for variant, frequency in zip(distribution.variants, distribution.freqs):
                construction = construction_of(world, variant)
                value: str | None = None
                if feature == "81A" and construction.kind == "fixed":
                    value = order_values.get(construction.order or "")
                elif feature == "143A":
                    value = {"pre": "143A-1", "post": "143A-2", "embraced": "143A-14"}.get(
                        construction.kind
                    )
                elif feature == "67A":
                    if construction.kind == "synthetic":
                        value = "67A-1"
                    elif construction.kind == "zero" or (
                        construction.kind == "periphrastic" and construction.stage == "free"
                    ):
                        value = "67A-2"
                elif feature in ("33A", "37A", "66A"):
                    prefix = {"33A": "plural", "37A": "definite", "66A": "past"}[feature]
                    if construction.kind == "zero":
                        value = f"{prefix}_absent"
                    elif construction.kind in ("synthetic", "periphrastic"):
                        value = f"{prefix}_present"
                totals[value] = totals.get(value, 0.0) + group.population * float(frequency)
        # Při shodě má přednost neznámá hodnota; u známých rozhoduje ID.
        result[feature] = min(totals, key=lambda key: (-totals[key], key is not None, key or "")) if totals else None
    return result


def underlying_inventory_proxy(world: World, language: Sequence[str]) -> dict[str, int | bool] | None:
    """Sjednocený inventář podkladových tvarů mluvených skupin (proxy).

    Změna se do tvarů přepisuje už při částečném šíření. Inventář tedy
    nerozlišuje fonémy a alofony; výskyt nosového vokálu nedokazuje kontrast
    podle WALS 10A a počty nejsou přímo srovnatelné s WALS 1A/2A.
    """
    if world.table is None:
        return None
    groups = [world.groups[group_id] for group_id in sorted(set(language))
              if not world.groups[group_id].written and world.groups[group_id].domain == "home"
              and world.groups[group_id].population > 0]
    segments = {
        segment
        for group in groups
        for unit in sorted(group.main_code.phonology.vocabulary)
        for segment in world.unit_of(group.main_code, unit).form
    }
    if not segments:
        return None
    vowels = [segment for segment in segments if world.table.is_vowel(segment)]
    nasal_index = world.table.index["nas"]
    return {
        "consonants": len(segments) - len(vowels),
        "vowels": len(vowels),
        "nasal_vowel": any(world.table.vectors[segment, nasal_index] == 1 for segment in vowels),
        "nasal_vowels": sum(int(world.table.vectors[segment, nasal_index] == 1) for segment in vowels),
    }


def nasal_contrast_witness(world: World, group_id: str) -> tuple[str, str] | None:
    """Dva různé dominantní lexémy lišící se jen oralitou/nazalitou vokálu.

    Nosový člen páru navíc nesmí mít bezprostředně za vokálem nosovou
    souhlásku: vyloučí se tak dosud podmíněná nazalizace i při lexikální
    difuzi. Jde o postačující pozitivní svědectví v podkladovém slovníku skupiny,
    nikoli úplný fonologický rozbor. None znamená nedoložený kontrast;
    neprokazuje jeho absenci ve skutečném jazyce ani v jiných slovech.
    Aktivní povrchové procesy se zde neaplikují. Sdílený kořen pro dva
    koncepty (polysémie) se nesmí zaměnit za dva různé lexémy.
    """
    import unicodedata

    table = world.table
    group = world.groups[group_id]
    if table is None or group.written or group.domain != "home" or group.population <= 0:
        return None
    roots: set[str] = set()
    for variable_id, variable in sorted(world.variables.items()):
        if variable.kind != "lexical":
            continue
        distribution = world.distribution(group_id, variable_id)
        if distribution is None:
            continue
        root = world.variants[distribution.dominant()[0]].payload.get("morpheme")
        if isinstance(root, str):
            roots.add(root)
    nasal_index = table.index["nas"]
    signatures: dict[int, tuple[tuple[int, ...], str]] = {}
    buckets: dict[tuple[object, ...], dict[bool, str]] = {}
    for root in sorted(roots):
        form = world.form_of(group.main_code, root)
        lexeme = world.morphemes[root].lexeme_id
        for position, segment in enumerate(form):
            if not table.is_vowel(segment):
                continue
            nasal = table.feature(segment, "nas") == 1
            if nasal and position + 1 < len(form):
                following = form[position + 1]
                if not table.is_vowel(following) and table.feature(following, "nas") == 1:
                    continue
            if segment not in signatures:
                vector = tuple(int(value) for index, value in enumerate(table.vectors[segment])
                               if index != nasal_index)
                spelling = unicodedata.normalize("NFD", table.ipa[segment]).replace("\u0303", "")
                signatures[segment] = (vector, spelling)
            key = (form[:position], form[position + 1:], signatures[segment])
            observed = buckets.setdefault(key, {})
            other = observed.get(not nasal)
            if other is not None and other != lexeme:
                return (other, lexeme) if other < lexeme else (lexeme, other)
            observed.setdefault(nasal, lexeme)
    return None
