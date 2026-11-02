"""Souběžná variabilita slovní zásoby protojazyka už na začátku běhu.

Protojazyk, jak ho zadá autor, má pro každý pojem jediné slovo. Živý jazyk
ale vždy žije s rozpracovanými změnami: synonyma, nová slova u části
mluvčích, posuny významu na půli cesty, a to jako nářeční kontinuum, kde
menšinové varianty vesnice jsou z velké části slova sousedů. Bez nich je
první tisíciletí běhu téměř bez lexikálních změn a druhé naopak rychlé,
než se variabilita ustálí (asi po 2 000 letech; kalibrace retence,
``docs/engine-v2/17-pozadi-dejin.md``).

Engine proto variabilitu rozdá při tvorbě světa bez simulace, podle
statistiky naměřené na ustálených sítích vesnic
(``cee/data/v2_standing_variation.json``, skript
``scripts/v2_measure_variation.py``):

- **tvar** variability (podle frekvence pojmu): hustota přeživších variant
  každého druhu změny na vesnici a pojem, u kterého ten druh jde navrhnout,
  kvantily vrcholového podílu a dosah šíření k sousedům;
- **množství** variability ve vesnici: kolik menšinových variant a jakou
  celkovou masu (součet podílů) vesnice v ustáleném stavu drží. Silně závisí
  na otevřenosti, populaci a na tom, z kolika vesnic řeč přes vazby
  přichází (řídká vesnice s malou otevřeností jich drží desetinu toho co
  otevřená vesnice v husté síti), proto je to naměřený model vesnice
  (:func:`model_terms`).

Obojí čte síť jako graf (:func:`source_graph`): vesnice ``j`` přejímá od
souseda ``k`` podíl ``o_j · w_jk`` (otevřenost krát poměrná síla vazby, jako
v přenosu) a ``G = (I − γ·B)⁻¹`` sečte všechny cesty s útlumem
:data:`GRAPH_DECAY` na krok. ``G[j, k]`` je, kolik řeči vesnice ``j``
pochází z ``k``; efektivní počet zdrojů vesnice vstupuje do modelu
a varianta z původce ``i`` dosáhne do ``j`` s podílem úměrným
``G[j, i] / G[i, i]``. Slabá vazba přes hranici kraje tak variantu
propustí méně než silná vazba uvnitř kraje.

Pro každou vesnici engine spočte cíl z modelu a dopočte, kolik variant má
vesnice jako původce navrhnout (činitel hustoty) a jak silné (činitel
vrcholového podílu), aby po rozšíření k sousedům očekávaný počet a masa
menšin v každé vesnici seděly s cílem (:func:`_factors`, z očekávaných
hodnot, bez losování). Pak pro každý pojem, vesnici a druh změny vylosuje
počet variant a skutečná změna navrhne skutečné slovo (posun významu
z příbuzného pojmu, odvozeninu ze slov protojazyka…). Varianta dostane ve
své vesnici vylosovaný vrcholový podíl a v okolních vesnicích (do tří
vazeb, jen stejného jazyka) podíl podle grafu. Slovo autora zůstane
převládající: součet menšin u pojmu ve vesnici je nanejvýš
``Parameters.variation_cap``. Hustotu násobí
``Parameters.standing_variation`` (0 = bez variability). Varianty mají
tik 0 (běh začíná tikem 1). Zvukové změny ani gramatika se netýká.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from importlib import resources
from typing import TYPE_CHECKING, Any, Mapping, Sequence

import numpy as np
import numpy.typing as npt

from cee.v2.repertoire import Distribution
from cee.v2.rng import generator

if TYPE_CHECKING:
    from cee.v2.world import World

#: Nejvzdálenější soused (počet vazeb), kam varianta z vesnice sahá.
REACH = 3
#: Útlum cesty grafem vazeb na jeden krok (:func:`source_graph`). Zvoleno
#: srovnáním 0,5 / 0,9 / 0,99 na sítích modelu vesnice: 0,9 a výš vysvětlí
#: rozdíl řad, mřížek a krajů stejně dobře, 0,5 hůř.
GRAPH_DECAY = 0.9
#: Body rovnoměrné náhody pro očekávané hodnoty vrcholového podílu.
_GRID = (np.arange(400) + 0.5) / 400
#: Kola dopočtu činitelů vesnic (:func:`_factors`).
_ROUNDS = 8
#: Meze činitelů (hustota, vrcholový podíl) vůči naměřenému tvaru.
_DENSITY_BOUNDS = (1e-3, 1e3)
_SHARE_BOUNDS = (0.05, 20.0)

#: Vlastnosti vesnice pro model množství variability: otevřenost, populace,
#: efektivní počet zdrojových vesnic.
Features = tuple[float, float, float]


@lru_cache(maxsize=1)
def measured() -> dict[str, Any]:
    text = resources.files("cee.data").joinpath("v2_standing_variation.json").read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


def source_graph(world: World, groups: Sequence[str]) -> npt.NDArray[np.float64]:
    """Matice ``G = (I − γ·B)⁻¹``: kolik řeči vesnice (řádek) pochází z vesnice (sloupec).

    ``B[j, k] = o_j · w_jk`` (otevřenost ``j`` krát síla vazby ``j → k``
    poměrně k součtu vazeb ``j``, jen mezi ``groups``), ``γ`` je
    :data:`GRAPH_DECAY`. Pořadí řádků a sloupců je pořadí ``groups``.
    """
    index = {group_id: position for position, group_id in enumerate(groups)}
    weights = np.zeros((len(groups), len(groups)))
    for (first, second), link in sorted(world.links.items()):
        if first in index and second in index and link.strength > 0.0:
            weights[index[first], index[second]] = link.strength
    totals = weights.sum(axis=1, keepdims=True)
    weights = np.divide(weights, totals, out=np.zeros_like(weights), where=totals > 0.0)
    openness = np.array([world.groups[group_id].openness for group_id in groups])
    graph: npt.NDArray[np.float64] = np.linalg.inv(
        np.eye(len(groups)) - GRAPH_DECAY * openness[:, None] * weights)
    return graph


def village_features(
    world: World, groups: Sequence[str], graph: npt.NDArray[np.float64] | None = None,
) -> dict[str, Features]:
    """Otevřenost, populace a efektivní počet zdrojů každé vesnice.

    Efektivní počet zdrojů je inverzní Simpsonův index řádku grafu
    (:func:`source_graph`) bez vesnice samotné: ``(Σ G_jk)² / Σ G_jk²``.
    Vesnice bez vazeb ho má nulový.
    """
    graph = source_graph(world, groups) if graph is None else graph
    others = graph - np.diag(np.diag(graph))
    totals = others.sum(axis=1)
    squares = (others ** 2).sum(axis=1)
    sources = np.divide(totals ** 2, squares, out=np.zeros_like(totals), where=squares > 0.0)
    return {
        group_id: (world.groups[group_id].openness, float(world.groups[group_id].population), float(sources[position]))
        for position, group_id in enumerate(groups)
    }


def model_terms(features: Features, knots: Mapping[str, Sequence[float]],
                sources_range: Sequence[float] | None = None) -> list[float]:
    """Členy modelu množství variability vesnice.

    Tabulka nad uzly otevřenosti × populace (``knots``) s bilineární
    interpolací v logaritmech (vlastnost mimo uzly se omezí na krajní uzel)
    a člen ``ln max(zdroje, 1)``. Počet zdrojů se se ``sources_range`` omezí
    do naměřeného rozpětí.
    """
    openness, population, sources = features
    if sources_range is not None:
        sources = min(max(sources, sources_range[0]), sources_range[1])
    across = _tent([math.log(value) for value in knots["openness"]], math.log(max(openness, 1e-9)))
    down = _tent([math.log(value) for value in knots["population"]], math.log(max(population, 1.0)))
    return [a * b for a in across for b in down] + [math.log(max(sources, 1.0))]


def _tent(knots: Sequence[float], value: float) -> list[float]:
    """Váhy uzlů pro lineární interpolaci (dva sousední uzly, jinak nula)."""
    value = min(max(value, knots[0]), knots[-1])
    index = min(int(np.searchsorted(knots, value, side="right")) - 1, len(knots) - 2)
    part = (value - knots[index]) / (knots[index + 1] - knots[index])
    weights = [0.0] * len(knots)
    weights[index], weights[index + 1] = 1.0 - part, part
    return weights


def target(model: Mapping[str, Any], features: Features) -> tuple[float, float]:
    """Ustálený počet menšinových variant a jejich masa ve vesnici podle modelu."""
    terms = model_terms(features, model["knots"], model["ranges"]["sources"])
    count = math.exp(sum(c * t for c, t in zip(model["count"], terms))) - 1.0
    mass = math.exp(sum(c * t for c, t in zip(model["mass"], terms))) - 1.0
    return max(count, 0.0), max(mass, 0.0)


def seed(world: World) -> None:
    """Dá výchozím vesnicím souběžnou variabilitu slovní zásoby."""
    from cee.v2.changes import LEXICAL_CHANGES
    from cee.v2.changes.base import InnovationContext

    scale = world.params.standing_variation
    if scale <= 0.0 or world.semantics is None or world.table is None:
        return
    lexical = sorted(variable_id for variable_id, variable in world.variables.items() if variable.kind == "lexical")
    groups = [group_id for group_id in world.group_ids() if not world.groups[group_id].written]
    if not lexical or not groups:
        return
    data = measured()
    edges, quantiles, floor = data["edges"], np.array(data["quantiles"]), data["min_share"]
    changes = {change.kind: change for change in LEXICAL_CHANGES}
    graph = source_graph(world, groups)
    spread = _spread(world, groups, graph)
    contexts = {
        group_id: InnovationContext(world, world.groups[group_id], world.groups[group_id].main_code, 0, world.start_year)
        for group_id in groups
    }
    sites = {
        (group_id, kind): frozenset(changes[kind].weighted_sites(contexts[group_id])[0])
        for group_id in groups for kind in sorted({k for entry in data["bins"] for k in entry["density"]})
        if kind in changes
    }
    bins = {
        variable_id: int(np.searchsorted(edges, world.concept_frequency(variable_id.split(":", 1)[1]), side="right"))
        for variable_id in lexical
    }
    density, share = _factors(world, data, groups, lexical, bins, sites, graph, spread)
    minorities: dict[tuple[str, str], dict[str, float]] = {}
    for variable_id in lexical:
        entry = data["bins"][bins[variable_id]]
        peaks, reach = np.array(entry["peak"]), entry["graph_scale"]
        for group_id in groups:
            context = contexts[group_id]
            rng = generator(world.seed, "variation", variable_id, group_id)
            index = 0
            for kind, rate in sorted(entry["density"].items()):
                change = changes.get(kind)
                if change is None or variable_id not in sites[(group_id, kind)]:
                    continue
                for _ in range(int(rng.poisson(rate * scale * density[group_id]))):
                    index += 1
                    peak = min(1.0, share[group_id] * float(np.interp(rng.uniform(), quantiles, peaks)))
                    variant = change.propose(context, variable_id, rng, index)
                    if variant is None or variant.id in world.variants:
                        continue
                    world.variants[variant.id] = variant
                    for other, relative in spread[group_id]:
                        found_share = peak if other == group_id else min(1.0, peak * reach * relative)
                        if found_share >= floor:
                            found = minorities.setdefault((other, variable_id), {})
                            found[variant.id] = found.get(variant.id, 0.0) + found_share
    # Indexy míst změn jsou odvozená data; postaví se znovu z aktuálního stavu
    # (jinak by svět změněný před prvním krokem četl index z doby rozdání).
    for group_id in groups:
        world.groups[group_id].main_code.phonology.cache.clear()
    cap = world.params.variation_cap
    for (group_id, variable_id), minority in sorted(minorities.items()):
        before = world.distribution(group_id, variable_id)
        if before is None or not before.is_fixed:
            continue
        total = sum(minority.values())
        factor = min(1.0, cap / total)
        shares = {variant: value * factor for variant, value in minority.items()}
        shares[before.variants[0]] = 1.0 - sum(shares.values())
        variants = tuple(sorted(shares))
        world.groups[group_id].main_code.repertoire.set(
            variable_id, Distribution(variants, np.array([shares[variant] for variant in variants])))


def _spread(
    world: World, groups: Sequence[str], graph: npt.NDArray[np.float64],
) -> dict[str, list[tuple[str, float]]]:
    """Kam varianta z původce sahá: vesnice stejného jazyka do ``REACH`` vazeb a ``G[j, i] / G[i, i]``.

    Původce sám je první s poměrem 1. Naměřený činitel koše
    (``graph_scale``) poměr teprve převede na podíl.
    """
    position = {group_id: index for index, group_id in enumerate(groups)}
    found = {}
    for origin, near in _distances(world, list(groups)).items():
        language = world.groups[origin].main_code.language
        own = graph[position[origin], position[origin]]
        found[origin] = [(origin, 1.0)] + [
            (other, float(graph[position[other], position[origin]] / own))
            for other in near if other != origin and world.groups[other].main_code.language == language
        ]
    return found


def _factors(
    world: World, data: Mapping[str, Any], groups: Sequence[str], lexical: Sequence[str],
    bins: Mapping[str, int], sites: Mapping[tuple[str, str], frozenset[str]],
    graph: npt.NDArray[np.float64], spread: Mapping[str, Sequence[tuple[str, float]]],
) -> tuple[dict[str, float], dict[str, float]]:
    """Činitele hustoty a vrcholového podílu původců, aby vesnice dostaly cílové množství.

    Očekávaný příspěvek původce ``i`` do vesnice ``j``: pro každý koš
    frekvence ``λ_i`` (součet hustot druhů přes pojmy, u kterých druh v ``i``
    jde navrhnout) krát pravděpodobnost, že podíl ``g_i · Q(u) · r_ij``
    dosáhne prahu (počet), resp. jeho střední hodnota nad prahem (masa);
    ``Q`` je naměřená kvantilová funkce vrcholového podílu a ``r_ij`` poměr
    šíření (1 u původce, jinak ``graph_scale`` koše krát poměr z
    :func:`_spread`). Činitele se dopočtou v několika kolech: hustota poměrem
    cílového a očekávaného počtu ve vesnici, podíl poměrem cílové a očekávané
    masy na variantu.
    """
    model = data["village_model"]
    features = village_features(world, groups, graph)
    # Rozdání dodá jen část očekávaného množství (``delivery``, naměřeno):
    # některé navržené varianty nejde vytvořit a strop menšin ořízne masu.
    delivery = model.get("delivery", {"count": 1.0, "mass": 1.0})
    targets = {
        group_id: (count / delivery["count"], mass / delivery["mass"])
        for group_id, (count, mass) in ((group_id, target(model, features[group_id])) for group_id in groups)
    }
    floor, quantiles = data["min_share"], data["quantiles"]
    shape = [np.interp(_GRID, quantiles, entry["peak"]) for entry in data["bins"]]
    rates = {group_id: np.zeros(len(data["bins"])) for group_id in groups}
    for variable_id in lexical:
        entry = data["bins"][bins[variable_id]]
        for group_id in groups:
            for kind, rate in entry["density"].items():
                available = sites.get((group_id, kind))
                if available is not None and variable_id in available:
                    rates[group_id][bins[variable_id]] += rate
    density = dict.fromkeys(groups, 1.0)
    share = dict.fromkeys(groups, 1.0)
    for _ in range(_ROUNDS):
        count = dict.fromkeys(groups, 0.0)
        mass = dict.fromkeys(groups, 0.0)
        for origin in groups:
            for index, values in enumerate(shape):
                rate = rates[origin][index] * density[origin]
                if rate <= 0.0:
                    continue
                peaks = np.minimum(1.0, share[origin] * values)
                reach = data["bins"][index]["graph_scale"]
                for other, relative in spread[origin]:
                    found = peaks if other == origin else np.minimum(1.0, peaks * reach * relative)
                    above = found >= floor
                    count[other] += rate * float(np.mean(above))
                    mass[other] += rate * float(np.mean(np.where(above, found, 0.0)))
        for group_id in groups:
            wanted_count, wanted_mass = targets[group_id]
            if count[group_id] <= 0.0 or mass[group_id] <= 0.0 or wanted_count <= 0.0:
                continue
            density[group_id] = _bounded(density[group_id] * wanted_count / count[group_id], _DENSITY_BOUNDS)
            per_variant = (wanted_mass / wanted_count) / (mass[group_id] / count[group_id])
            share[group_id] = _bounded(share[group_id] * per_variant, _SHARE_BOUNDS)
    return density, share


def _bounded(value: float, bounds: tuple[float, float]) -> float:
    return min(max(value, bounds[0]), bounds[1])


def _distances(world: World, groups: list[str]) -> dict[str, dict[str, int]]:
    """Vesnice do ``REACH`` vazeb od každé vesnice: skupina → (skupina → počet vazeb)."""
    members = set(groups)
    near: dict[str, list[str]] = {group_id: [] for group_id in groups}
    for (first, second), link in sorted(world.links.items()):
        if first in members and second in members and link.strength > 0.0:
            near[first].append(second)
    found = {}
    for start in groups:
        depth, frontier = {start: 0}, [start]
        for level in range(1, REACH + 1):
            following = []
            for group_id in frontier:
                for other in near[group_id]:
                    if other not in depth:
                        depth[other] = level
                        following.append(other)
            frontier = following
        found[start] = depth
    return found
