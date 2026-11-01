"""Podklady pro jména jazyků a nářečí (export pro UI).

Engine jména nevymýšlí v češtině ani v jiném jazyce UI. Dodává fakta, ze
kterých UI jméno složí podle svých pravidel:

- **vlastní jméno jazyka** (endonym): jak jazyk sám sobě říká. Je to složenina
  slov protojazyka (``World.endonyms``, např. „lidé“ + „řeč“), kterou si
  každá linie nese a mění s ostatními slovy. Dceřiné jazyky tak mají jméno,
  které se z rodičovského vyvinulo (jako *Deutsch* a *Dutch*);
- **kde jazyk vznikl**: region, ve kterém ležela většina jeho vesnic při
  rozštěpení;
- **poloha nářečí**: směr od středu jazyka (osm směrů nebo střed), regiony,
  terén a ostrov. UI z toho složí „východní nářečí“, „horské nářečí“ nebo
  jméno podle regionu.

Nic z toho neovlivňuje dynamiku ani otisk historie; počítá se jen při exportu
a ve snímcích pro UI. Poloha je v km jako ``Territory.position``; osa *y*
roste k jihu, tak jak mapu kreslí UI.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

if TYPE_CHECKING:
    from cee.v2.world import World

#: Pojmy, ze kterých se složí vlastní jméno jazyka, když autor nezadá jiné.
DEFAULT_ENDONYM: tuple[str, ...] = ("language",)

#: Směry od středu jazyka po 45° (osa y k jihu); ``center`` je blízko středu.
DIRECTIONS = ("east", "southeast", "south", "southwest", "west", "northwest", "north", "northeast")

#: Nářečí blíž ke středu jazyka než tento podíl jeho poloměru je ``center``.
CENTER_SHARE = 0.35


def syllables(segments: Sequence[str], is_vowel) -> list[list[str]]:
    """Slabiky tvaru: souhláska před samohláskou začíná novou slabiku."""
    out: list[list[str]] = [[]]
    for index, segment in enumerate(segments):
        current = out[-1]
        has_vowel = any(is_vowel(item) for item in current)
        next_vowel = index + 1 < len(segments) and is_vowel(segments[index + 1])
        if has_vowel and (is_vowel(segment) or next_vowel):
            out.append([segment])
        else:
            current.append(segment)
    return [syllable for syllable in out if syllable]


def compound(parts: Sequence[Sequence[str]], is_vowel) -> list[str]:
    """Složenina jako u místních jmen: první části na slabiku, celek nejvýš o dvě slabiky delší."""
    split = [syllables(part, is_vowel) for part in parts if part]
    if not split:
        return []
    head = [part[0] for part in split[:-1]]
    tail = split[-1]
    kept = [*head, *tail][: max(2, len(head) + 2)]
    return [segment for syllable in kept for segment in syllable]


def representative(world: World, groups: Iterable[str]) -> str | None:
    """Mluvená domácí skupina s nejvíc lidmi (při shodě první podle ID)."""
    best = None
    for group_id in sorted(groups):
        group = world.groups.get(group_id)
        if group is None or group.written or group.domain != "home":
            continue
        if best is None or group.population > world.groups[best].population:
            best = group_id
    return best


def endonym(world: World, groups: Iterable[str]) -> str | None:
    """Vlastní jméno jazyka, jak ho dnes vyslovují jeho mluvčí (IPA)."""
    group_id = representative(world, groups)
    if group_id is None or world.table is None:
        return None
    code = world.groups[group_id].main_code
    concepts = world.endonyms.get(code.language, DEFAULT_ENDONYM)
    table = world.table
    parts = []
    for concept in concepts:
        root = code.phonology.dominant.get(concept)
        if root is None:
            continue
        parts.append([table.render((segment,)) for segment in world.form_of(code, root)])
    is_vowel = _vowel_test(world)
    form = compound(parts, is_vowel)
    return "".join(form) or None


def origin_region(world: World, groups: Iterable[str]) -> str | None:
    """Region, ve kterém leží většina vesnic (při shodě první podle ID)."""
    counts = Counter(_region(world, group_id) for group_id in groups)
    counts.pop(None, None)
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def direction(offset: tuple[float, float], radius: float) -> str:
    """Směr posunu od středu (osa y k jihu), nebo ``center``."""
    dx, dy = offset
    if radius <= 0 or math.hypot(dx, dy) < CENTER_SHARE * radius:
        return "center"
    angle = math.degrees(math.atan2(dy, dx)) % 360.0
    return DIRECTIONS[int(((angle + 22.5) % 360.0) // 45.0)]


def dialects(world: World, clusters: Sequence[Sequence[str]], lineage_of: Mapping[str, str]) -> list[dict[str, Any]]:
    """Fakta pro jméno každého nářečí: jazyk, regiony, směr od středu jazyka, terén."""
    members: dict[str, list[str]] = {}
    for cluster in clusters:
        for group_id in cluster:
            lineage = lineage_of.get(group_id)
            if lineage is not None:
                members.setdefault(lineage, []).append(group_id)
    centres = {lineage: _centre(world, groups) for lineage, groups in members.items()}
    radius = {
        lineage: max((math.dist(centres[lineage], world.position_of(g)) for g in groups), default=0.0)
        for lineage, groups in members.items()
    }
    out = []
    for cluster in clusters:
        groups = sorted(cluster)
        lineages = Counter(lineage_of.get(g) for g in groups)
        lineages.pop(None, None)
        lineage = sorted(lineages.items(), key=lambda item: (-item[1], item[0]))[0][0] if lineages else None
        regions = Counter(_region(world, g) for g in groups)
        regions.pop(None, None)
        terrains = {world.territories[r].terrain for r in regions}
        centre = _centre(world, groups)
        offset = (0.0, 0.0) if lineage is None else (centre[0] - centres[lineage][0], centre[1] - centres[lineage][1])
        out.append({
            "groups": groups,
            "lineage": lineage,
            "regions": [r for r, _ in sorted(regions.items(), key=lambda item: (-item[1], item[0]))],
            "direction": "center" if lineage is None or len(members[lineage]) == len(groups)
            else direction(offset, radius[lineage]),
            "terrain": terrains.pop() if len(terrains) == 1 else None,
            "sole": lineage is not None and len(members[lineage]) == len(groups),
        })
    return out


def _centre(world: World, groups: Sequence[str]) -> tuple[float, float]:
    points = [world.position_of(g) for g in groups]
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


def _region(world: World, group_id: str) -> str | None:
    territory = world.territories.get(world.groups[group_id].territory) if group_id in world.groups else None
    while territory is not None and territory.level != "region":
        territory = world.territories.get(territory.parent) if territory.parent else None
    return None if territory is None else territory.id


def _vowel_test(world: World):
    table = world.table
    cache: dict[str, bool] = {}

    def is_vowel(ipa: str) -> bool:
        if ipa not in cache:
            cache[ipa] = table.is_vowel(table.id_of(ipa))
        return cache[ipa]

    return is_vowel
