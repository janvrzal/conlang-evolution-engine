"""Státy, jazyková politika a lingua franca (M6f).

Stát svůj jazyk nešíří přímo. Mění tři věci a jazyk se pak šíří sám
mechanismy, které engine už má:

- **prestiž**: vesnice hlavního města mají vyšší prestiž, takže se od nich
  děti sousedů učí víc (``mixing_matrix``) a jejich jazyk má vyšší status;
- **sítě**: centralizace spojí vesnice státu se sídlem (úřady, trh, vojsko,
  cesty) a nářečí se srovnávají k řeči centra;
- **domény**: regiony jiného jazyka užívají úřední jazyk mimo domov
  (veřejná doména) a politika určuje, jak silně se tlačí i domů
  (:func:`cee.v2.contact._nativize`).

Jestli jazyk regionu přežije, rozhoduje jeho demografie, terén (dosah
státu) a loajalita (odlišnost regionu), ne autor. **Lingua franca** je
týž mechanismus bez státu: komunity různých jazyků se jedním kódem
domlouvají mimo domov; učí se ho dospělí, takže se zjednodušuje (L2 tlaky)
a nese stopy jejich jazyků.

Autor zadává regiony a slovní úrovně (``"strong"``, ``"enforced"``…);
čísla jsou v ``world.params`` a kalibrují se. Je to přiblížení: stát nemá
hospodářství ani armádu, jen tyto tři páky.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from cee.v2.events import LanguageShift, WorldEvent
from cee.v2.history import History
from cee.v2.parameters import level
from cee.v2.world import World


@dataclass(slots=True)
class Polity:
    """Stát ve světě (``world.states``): území, sídlo a jazyková politika."""

    id: str
    regions: tuple[str, ...]
    capital: str
    #: Skupina, jejíž řeč je úředním jazykem (největší vesnice hlavního města).
    seat: str
    language: str
    centralization: str
    policy: str


def region_of(world: World, group_id: str) -> str | None:
    """Region (území úrovně ``region``), ve kterém skupina žije."""
    territory: str | None = world.groups[group_id].territory
    while territory is not None:
        found = world.territories[territory]
        if found.level == "region":
            return found.id
        territory = found.parent
    return None


def groups_in(world: World, regions: tuple[str, ...] | list[str]) -> list[str]:
    """Domácí mluvené skupiny regionů (bez psaných kódů a veřejné domény)."""
    wanted = set(regions)
    return [
        group_id for group_id in world.group_ids()
        if not world.groups[group_id].written and world.groups[group_id].domain == "home"
        and region_of(world, group_id) in wanted
    ]


def seat_of(world: World, region: str) -> str:
    """Největší vesnice regionu (při shodě první podle ID)."""
    found = groups_in(world, [region])
    if not found:
        raise ValueError(f"Region '{region}' nemá žádnou vesnici.")
    return min(found, key=lambda group_id: (-world.groups[group_id].population, group_id))


def reach(world: World, group_id: str, seat: str, *, distance: bool = True) -> float:
    """Dosah centra do skupiny: terén regionu × pokles se vzdáleností."""
    region = region_of(world, group_id)
    terrain = world.territories[region].terrain if region is not None else "plain"
    access = float(world.params.terrain_access[terrain])
    if not distance:
        return access
    here, there = world.position_of(group_id), world.position_of(seat)
    if here is None or there is None:
        return access
    return access * math.exp(-math.dist(here, there) / world.params.capital_reach)


def _check_regions(world: World, regions: tuple[str, ...]) -> None:
    for region in regions:
        territory = world.territories.get(region)
        if territory is None or territory.level != "region":
            raise ValueError(f"'{region}' není region světa.")


def _source_group(world: World, source: str) -> str:
    """Skupina zdroje: ID skupiny, nebo region (jeho největší vesnice)."""
    if source in world.groups:
        return source
    _check_regions(world, (source,))
    return seat_of(world, source)


def public_bilingualism(
    world: World, history: History, tick: int, year: float, group_id: str, source_id: str, *,
    share: float, pull: float, link: float, replace_pull: bool,
) -> str | None:
    """Podíl ``share`` dospělých skupiny užívá kód ``source`` mimo domov.

    Vytvoří (nebo posílí) skupinu veřejné domény (:class:`LanguageShift`
    s ``domain="public"``), spojí ji se zdrojem a nastaví, jak silně se kód
    tlačí domů (``pull``). Vrací ID veřejné skupiny, nebo ``None``.
    """
    group, source = world.groups[group_id], world.groups[source_id]
    public_id = f"{group_id}>{source.main_code.language}"
    existing = world.groups.get(public_id)
    if existing is not None:
        if existing.domain != "public":
            return None
        existing.population = max(existing.population, round(share * group.population))
        existing.home_pull = pull if replace_pull else max(existing.home_pull, pull)
        nativized = world.groups.get(f"{group_id}>{source.main_code.language}:home")
        if nativized is not None and nativized.home_pull > 0:
            nativized.home_pull = max(existing.home_pull, 1e-6)
    else:
        if share * group.population < 1.0:
            return None
        LanguageShift(year, group_id, source_id, initial_share=share, domain="public").apply(world, history, tick)
        existing = world.groups[public_id]
        existing.home_pull = pull
    if link > 0:
        current = world.links.get((public_id, source_id))
        if current is None or current.strength < link:
            world.connect(public_id, source_id, link, "weak")
    return public_id


def _policy(world: World, history: History, tick: int, year: float, polity: Polity) -> list[str]:
    table = level(world.params.policy_levels, polity.policy, "jazyková politika")
    touched = []
    for group_id in groups_in(world, polity.regions):
        if world.groups[group_id].main_code.language == polity.language:
            continue
        scale = reach(world, group_id, polity.seat)
        created = public_bilingualism(
            world, history, tick, year, group_id, polity.seat,
            share=float(table["share"]) * scale, pull=float(table["pull"]) * scale,
            link=world.params.capital_link_strength * scale, replace_pull=True,
        )
        if created is not None:
            touched.append(group_id)
    return touched


def _centralize(world: World, polity: Polity, regions: tuple[str, ...]) -> int:
    strength = world.params.capital_link_strength * float(
        level(world.params.centralization_levels, polity.centralization, "úroveň centralizace")
    )
    linked = 0
    if strength <= 0:
        return linked
    for group_id in groups_in(world, regions):
        if region_of(world, group_id) == polity.capital:
            continue
        value = strength * reach(world, group_id, polity.seat)
        current = world.links.get((group_id, polity.seat))
        if current is None or current.strength < value:
            world.connect(group_id, polity.seat, value, "weak")
            linked += 1
    return linked


@dataclass(frozen=True)
class State(WorldEvent):
    """Vznik státu z regionů ``regions`` s hlavním městem v regionu ``capital``.

    - vesnice hlavního města dostanou ``Parameters.capital_prestige``× prestiž;
    - ``centralization`` (``none``, ``weak``, ``moderate``, ``strong``) spojí
      vesnice státu se sídlem, slaběji s rostoucí vzdáleností a v horách;
    - ``policy`` (``tolerant``, ``promoted``, ``enforced``) určí, kolik lidí
      regionů jiného jazyka užívá úřední jazyk mimo domov a jak silně se tlačí
      domů. Úřední jazyk je řeč sídla (největší vesnice hlavního města).
    """

    year: float
    id: str
    regions: tuple[str, ...]
    capital: str
    centralization: str = "moderate"
    policy: str = "tolerant"

    def apply(self, world: World, history: History, tick: int) -> None:
        if self.id in world.states:
            raise ValueError(f"Stát '{self.id}' už existuje.")
        _check_regions(world, self.regions)
        if self.capital not in self.regions:
            raise ValueError(f"Hlavní město '{self.capital}' musí ležet ve státě '{self.id}'.")
        level(world.params.centralization_levels, self.centralization, "úroveň centralizace")
        level(world.params.policy_levels, self.policy, "jazyková politika")
        seat = seat_of(world, self.capital)
        for group_id in groups_in(world, [self.capital]):
            world.groups[group_id].prestige *= world.params.capital_prestige
        polity = Polity(self.id, tuple(self.regions), self.capital, seat,
                        world.groups[seat].main_code.language, self.centralization, self.policy)
        world.states[self.id] = polity
        linked = _centralize(world, polity, polity.regions)
        bilingual = _policy(world, history, tick, self.year, polity)
        history.record("state", tick, self.year, state=self.id, regions=sorted(self.regions),
                       capital=self.capital, seat=seat, language=polity.language,
                       centralization=self.centralization, policy=self.policy,
                       linked=linked, bilingual=bilingual)


@dataclass(frozen=True)
class LanguagePolicy(WorldEvent):
    """Stát ``state`` změní jazykovou politiku (např. povinná škola v úředním jazyce)."""

    year: float
    state: str
    policy: str

    def apply(self, world: World, history: History, tick: int) -> None:
        polity = _polity(world, self.state)
        level(world.params.policy_levels, self.policy, "jazyková politika")
        polity.policy = self.policy
        bilingual = _policy(world, history, tick, self.year, polity)
        history.record("language_policy", tick, self.year, state=self.state, policy=self.policy,
                       bilingual=bilingual)


@dataclass(frozen=True)
class Annexation(WorldEvent):
    """Stát ``state`` připojí regiony ``regions`` (dobytí, sňatek, unie)."""

    year: float
    state: str
    regions: tuple[str, ...]

    def apply(self, world: World, history: History, tick: int) -> None:
        polity = _polity(world, self.state)
        _check_regions(world, self.regions)
        for other in sorted(world.states.values(), key=lambda found: found.id):
            if other.id != polity.id:
                other.regions = tuple(region for region in other.regions if region not in self.regions)
        added = tuple(region for region in self.regions if region not in polity.regions)
        polity.regions = (*polity.regions, *added)
        linked = _centralize(world, polity, added)
        bilingual = _policy(world, history, tick, self.year, polity)
        history.record("annexation", tick, self.year, state=self.state, regions=sorted(added),
                       linked=linked, bilingual=bilingual)


@dataclass(frozen=True)
class LinguaFranca(WorldEvent):
    """Kód zdroje ``source`` se stane dorozumívacím jazykem regionů ``regions``.

    ``source`` je region (jeho největší vesnice, typicky obchodní město) nebo
    ID skupiny. ``spread`` (``rare``, ``common``, ``universal``) je podíl
    dospělých, kteří se jím domluví mimo domov; hory a ostrovy ho snižují.
    S ``nativize`` se lingua franca časem stane i jazykem domova (svahilština
    ve městech, indonéština), jinak zůstane stabilní dvojjazyčnost.
    """

    year: float
    source: str
    regions: tuple[str, ...]
    spread: str = "common"
    nativize: bool = False

    def apply(self, world: World, history: History, tick: int) -> None:
        _check_regions(world, self.regions)
        share = float(level(world.params.lingua_franca_levels, self.spread, "úroveň rozšíření"))
        source = _source_group(world, self.source)
        language = world.groups[source].main_code.language
        pull = world.params.lingua_franca_pull if self.nativize else 0.0
        bilingual = []
        for group_id in groups_in(world, self.regions):
            if world.groups[group_id].main_code.language == language:
                continue
            scale = reach(world, group_id, source, distance=False)
            created = public_bilingualism(
                world, history, tick, self.year, group_id, source, share=share * scale, pull=pull * scale,
                link=world.params.lingua_franca_link * scale, replace_pull=False,
            )
            if created is not None:
                bilingual.append(group_id)
        history.record("lingua_franca", tick, self.year, source=source, language=language,
                       regions=sorted(self.regions), spread=self.spread, nativize=self.nativize,
                       bilingual=bilingual)


def _polity(world: World, state: str) -> Polity:
    polity = world.states.get(state)
    if polity is None:
        raise ValueError(f"Stát '{state}' neexistuje; nejdřív ho založ událostí State.")
    return polity


def language_census(world: World) -> dict[str, dict[str, Any]]:
    """Jazyky regionů: podíl lidí podle jazyka doma a mimo domov.

    ``home``: linie jazyka → podíl obyvatel regionu, kteří jím mluví doma.
    ``public``: linie → podíl obyvatel, kteří ho užívají jen mimo domov.
    ``state``: stát, do kterého region patří (``None`` mimo státy).
    """
    states = {region: polity.id for polity in sorted(world.states.values(), key=lambda p: p.id)
              for region in polity.regions}
    census: dict[str, dict[str, Any]] = {}
    for group_id in world.group_ids():
        group = world.groups[group_id]
        region = region_of(world, group_id)
        if group.written or region is None:
            continue
        entry = census.setdefault(region, {"home": {}, "public": {}, "people": 0.0, "state": states.get(region)})
        language = group.main_code.language
        if group.domain == "home":
            entry["home"][language] = entry["home"].get(language, 0.0) + group.population
            entry["people"] += group.population
        else:
            entry["public"][language] = entry["public"].get(language, 0.0) + group.population
    for entry in census.values():
        people = entry.pop("people") or 1.0
        for domain in ("home", "public"):
            entry[domain] = {language: count / people for language, count in sorted(entry[domain].items())}
    return dict(sorted(census.items()))
