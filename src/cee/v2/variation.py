"""Souběžná variabilita slovní zásoby protojazyka už na začátku běhu.

Protojazyk, jak ho zadá autor, má pro každý pojem jediné slovo. Živý jazyk
ale vždy žije s rozpracovanými změnami: synonyma, nová slova u části
mluvčích, posuny významu na půli cesty, a to jako nářeční kontinuum, kde
menšinové varianty vesnice jsou z velké části slova sousedů. Bez nich je
první tisíciletí běhu téměř bez lexikálních změn a druhé naopak rychlé,
než se variabilita ustálí (asi po 2 000 letech; kalibrace retence,
``docs/engine-v2/17-pozadi-dejin.md``).

Engine proto variabilitu rozdá při tvorbě světa bez simulace, podle
statistiky naměřené na ustálené síti vesnic
(``cee/data/v2_standing_variation.json``, skript
``scripts/v2_measure_variation.py``): pro každý pojem, vesnici a druh
změny, který u pojmu jde navrhnout, vylosuje počet variant podle hustoty
přeživších variant toho druhu pro frekvenci pojmu, a skutečná změna
navrhne skutečné slovo (posun
významu z příbuzného pojmu, odvozeninu ze slov protojazyka…). Varianta
dostane ve své vesnici vylosovaný vrcholový podíl a v sousedních vesnicích
(do tří vazeb, jen stejného jazyka) jeho naměřený násobek. Slovo autora
zůstane převládající: součet menšin u pojmu ve vesnici je nanejvýš
``Parameters.variation_cap``. Hustotu násobí
``Parameters.standing_variation`` (0 = bez variability). Varianty mají
tik 0 (běh začíná tikem 1). Zvukové změny ani gramatika se netýká.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import TYPE_CHECKING, Any

import numpy as np

from cee.v2.repertoire import Distribution
from cee.v2.rng import generator

if TYPE_CHECKING:
    from cee.v2.world import World

#: Nejvzdálenější soused (počet vazeb), kam varianta z vesnice sahá.
REACH = 3


@lru_cache(maxsize=1)
def measured() -> dict[str, Any]:
    text = resources.files("cee.data").joinpath("v2_standing_variation.json").read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


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
    distance = _distances(world, groups)
    sites: dict[tuple[str, str], frozenset[str]] = {}
    minorities: dict[tuple[str, str], dict[str, float]] = {}
    for variable_id in lexical:
        entry = data["bins"][int(np.searchsorted(edges, world.concept_frequency(variable_id.split(":", 1)[1]),
                                                 side="right"))]
        peaks = np.array(entry["peak"])
        for group_id in groups:
            group = world.groups[group_id]
            context = InnovationContext(world, group, group.main_code, 0, world.start_year)
            rng = generator(world.seed, "variation", variable_id, group_id)
            index = 0
            for kind, density in sorted(entry["density"].items()):
                change = changes.get(kind)
                if change is None:
                    continue
                key = (group_id, kind)
                if key not in sites:
                    sites[key] = frozenset(change.weighted_sites(context)[0])
                if variable_id not in sites[key]:
                    continue
                for _ in range(int(rng.poisson(density * scale))):
                    index += 1
                    peak = float(np.interp(rng.uniform(), quantiles, peaks))
                    variant = change.propose(context, variable_id, rng, index)
                    if variant is None or variant.id in world.variants:
                        continue
                    world.variants[variant.id] = variant
                    language = group.main_code.language
                    for other, depth in distance[group_id].items():
                        if world.groups[other].main_code.language != language:
                            continue
                        share = peak if depth == 0 else peak * entry["decay"][depth - 1]
                        if share >= floor:
                            found = minorities.setdefault((other, variable_id), {})
                            found[variant.id] = found.get(variant.id, 0.0) + share
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
        shares = {variant: share * factor for variant, share in minority.items()}
        shares[before.variants[0]] = 1.0 - sum(shares.values())
        variants = tuple(sorted(shares))
        world.groups[group_id].main_code.repertoire.set(
            variable_id, Distribution(variants, np.array([shares[variant] for variant in variants])))


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
