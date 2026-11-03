"""Pozadí dějin: drobné události, které svět generuje sám vedle událostí autora.

Ve skutečnosti se pořád něco děje: kraj vylidní mor a za pár generací se
zase zaplní, část lidí se přestěhuje k sousedům, obchodní cesta zesílí
a po čase upadne, kraj zbohatne nebo zchudne, soused jiného jazyka dosadí
elitu, která po několika generacích splyne s místními. Tyhle drobné otřesy hýbou jazykem: přinášejí výpůjčky a míšení,
v malých populacích zesilují drift. Klidný svět bez nich mění slovní zásobu
pomaleji než skutečné jazyky (kalibrace M7, retence).

Autor volí jen míru (``Parameters.background_levels``: ``none``, ``calm``,
``normal``, ``turbulent``); četnosti druhů událostí jsou v
``Parameters.background_rates``, rozsahy veličin v
``Parameters.background_spans``. Generátor je deterministický podle seedu
světa a vlastního proudu náhody, takže stejný svět dá stejné dějiny a na
ostatní náhodu enginu nesahá. Události pracují s kraji; vesnice si najdou
až při provedení, takže fungují i po přechodu k jinému jazyku nebo migraci.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from cee.v2.events import Conquest, Migration, WorldEvent
from cee.v2.history import History
from cee.v2.parameters import Parameters, level
from cee.v2.polity import groups_in, refresh, region_of, seat_of
from cee.v2.rng import generator
from cee.v2.world import World

#: Krok generátoru v letech (jako krok simulace).
STEP = 25.0


@dataclass(frozen=True)
class Plague(WorldEvent):
    """Mor nebo hladomor: domácí skupiny kraje ztratí podíl ``mortality`` lidí."""

    year: float
    regions: tuple[str, ...]
    mortality: float

    def apply(self, world: World, history: History, tick: int) -> None:
        groups = groups_in(world, self.regions)
        for group_id in groups:
            group = world.groups[group_id]
            group.population = max(1, round(group.population * (1.0 - self.mortality)))
        history.record("plague", tick, self.year, regions=sorted(self.regions), mortality=self.mortality,
                       groups=groups, background=True)


@dataclass(frozen=True)
class Recovery(WorldEvent):
    """Obnova po moru: populace kraje doroste o násobek ``factor``."""

    year: float
    regions: tuple[str, ...]
    factor: float

    def apply(self, world: World, history: History, tick: int) -> None:
        groups = groups_in(world, self.regions)
        for group_id in groups:
            group = world.groups[group_id]
            group.population = max(1, round(group.population * self.factor))
        history.record("recovery", tick, self.year, regions=sorted(self.regions), factor=self.factor,
                       background=True)


@dataclass(frozen=True)
class Resettlement(WorldEvent):
    """Část lidí kraje ``source`` se přestěhuje do sídla sousedního kraje ``target``.

    Přistěhovalci se řeč nového domova učí v dospělosti (podíl L2 mluvčích
    tam vzroste), jako u :class:`cee.v2.events.Migration`.
    """

    year: float
    source: str
    target: str
    share: float

    def apply(self, world: World, history: History, tick: int) -> None:
        sources = tuple((group_id, self.share) for group_id in groups_in(world, (self.source,)))
        if not sources or not groups_in(world, (self.target,)):
            return
        target = seat_of(world, self.target)
        Migration(self.year, sources, target).apply(world, History(), tick)
        history.record("resettlement", tick, self.year, source=self.source, target=self.target,
                       share=self.share, background=True)


@dataclass(frozen=True)
class TradeShift(WorldEvent):
    """Obchodní cesta mezi dvěma sousedními kraji zesílí (``factor`` > 1) nebo upadne.

    Přidaná síla vazeb je podíl kanálu ``trade`` (``World.trade``); upadne-li
    cesta zpět na původní sílu, podíl zmizí.
    """

    year: float
    regions: tuple[str, str]
    factor: float

    def apply(self, world: World, history: History, tick: int) -> None:
        first, second = self.regions
        changed = 0
        for (a, b), link in sorted(world.links.items()):
            if a > b or world.groups[a].written or world.groups[b].written:
                continue
            pair = {region_of(world, a), region_of(world, b)}
            if pair == {first, second}:
                world.connect(a, b, link.strength * self.factor, link.kind)
                # Co obchodní cesta přidala (nebo ubrala) ze síly vazby, patří kanálu
                # ``trade``; po jejím úpadku zůstane obecný kontakt sousedů.
                kept = world.links[(a, b)].strength
                carried = world.trade.get((a, b), 0.0) + link.strength * (self.factor - 1.0)
                if carried > 0.0:
                    world.trade[(a, b)] = min(kept, carried)
                else:
                    world.trade.pop((a, b), None)
                changed += 1
        history.record("trade", tick, self.year, regions=[first, second], factor=self.factor, links=changed,
                       background=True)


@dataclass(frozen=True)
class PrestigeShift(WorldEvent):
    """Kraj zbohatne nebo zchudne: základní prestiž jeho skupin se násobí ``factor``."""

    year: float
    region: str
    factor: float

    def apply(self, world: World, history: History, tick: int) -> None:
        for group_id in groups_in(world, (self.region,)):
            base = world.base_prestige.get(group_id, world.groups[group_id].prestige)
            world.base_prestige[group_id] = base * self.factor
            world.groups[group_id].prestige = base * self.factor
        refresh(world)
        history.record("prestige", tick, self.year, region=self.region, factor=self.factor, background=True)


@dataclass(frozen=True)
class ForeignElite(WorldEvent):
    """Soused jiného jazyka dosadí v kraji elitu (vláda, šlechta, posádka)."""

    year: float
    conqueror: str
    region: str

    def apply(self, world: World, history: History, tick: int) -> None:
        subjects = tuple(groups_in(world, (self.region,)))
        if not subjects or not groups_in(world, (self.conqueror,)):
            return
        seat = world.groups[seat_of(world, self.region)]
        conqueror = seat_of(world, self.conqueror)
        if f"{seat.territory}+{conqueror}" in world.groups:
            return
        params = world.params
        Conquest(self.year, conqueror, seat.territory, subjects,
                 population=max(20, round(seat.population * params.background_elite_share)),
                 prestige=params.background_elite_prestige,
                 strength=params.background_elite_link).apply(world, History(), tick)
        history.record("foreign_elite", tick, self.year, conqueror=self.conqueror, region=self.region,
                       background=True)


@dataclass(frozen=True)
class EliteAssimilation(WorldEvent):
    """Cizí elita v kraji splyne s místními a zanikne; výpůjčky po ní zůstanou.

    Elity se do několika generací přestanou odlišovat (Normané v Anglii,
    Varjagové na Rusi). Bez konce by elita dodávala výpůjčky navždy.
    """

    year: float
    conqueror: str
    region: str

    def apply(self, world: World, history: History, tick: int) -> None:
        rulers = groups_in(world, (self.conqueror,))
        if not rulers:
            return
        language = world.groups[rulers[0]].main_code.language
        ended = [group_id for group_id in groups_in(world, (self.region,))
                 if "+" in group_id and world.groups[group_id].main_code.language == language]
        for group_id in ended:
            world.remove_group(group_id)
        if ended:
            history.record("elite_assimilation", tick, self.year, conqueror=self.conqueror, region=self.region,
                           groups=ended, background=True)


def _span(rng, spans: Mapping[str, Mapping[str, float]], name: str) -> float:
    return float(rng.uniform(spans[name]["low"], spans[name]["high"]))


def _steps(rng, spans: Mapping[str, Mapping[str, float]], name: str) -> int:
    return int(rng.integers(int(spans[name]["low"]), int(spans[name]["high"]) + 1))


def generate(
    regions: Sequence[tuple[str, Sequence[str], str | None]],
    *,
    start: float,
    end: float,
    level_name: str,
    seed: int,
    params: Parameters | None = None,
) -> list[WorldEvent]:
    """Události pozadí pro kraje ``(id, sousedé, protojazyk)`` mezi ``start`` a ``end``."""
    params = params or Parameters()
    scale = float(level(params.background_levels, level_name, "míra pozadí dějin"))
    if scale <= 0.0:
        return []
    rates: Mapping[str, float] = params.background_rates
    spans = params.background_spans
    rng = generator(seed, "background")
    neighbours = {region: sorted(set(near)) for region, near, _ in regions}
    language = {region: lang for region, _, lang in regions}
    ids = sorted(neighbours)
    events: list[WorldEvent] = []
    year = start + STEP
    while year < end:
        for region in ids:
            near = neighbours[region]
            for kind in ("plague", "resettlement", "trade", "prestige", "foreign_elite"):
                expected = rates.get(kind, 0.0) * scale * STEP / 100.0
                if expected <= 0.0 or int(rng.poisson(expected)) == 0:
                    continue
                if kind == "plague":
                    mortality = round(_span(rng, spans, "plague_mortality"), 2)
                    events.append(Plague(year, (region,), mortality))
                    later = year + STEP * _steps(rng, spans, "recovery_steps")
                    if later < end:
                        events.append(Recovery(later, (region,), round(1.0 / (1.0 - mortality), 3)))
                elif kind == "resettlement" and near:
                    target = near[int(rng.integers(len(near)))]
                    events.append(Resettlement(year, region, target, round(_span(rng, spans, "resettlement_share"), 2)))
                elif kind == "trade" and near:
                    other = near[int(rng.integers(len(near)))]
                    pair = (min(region, other), max(region, other))
                    factor = round(_span(rng, spans, "trade_factor"), 2)
                    events.append(TradeShift(year, pair, factor))
                    later = year + STEP * _steps(rng, spans, "trade_steps")
                    if later < end:
                        events.append(TradeShift(later, pair, round(1.0 / factor, 3)))
                elif kind == "prestige":
                    events.append(PrestigeShift(year, region, round(_span(rng, spans, "prestige_factor"), 2)))
                elif kind == "foreign_elite":
                    foreign = [other for other in near if language.get(other) != language.get(region)]
                    if foreign:
                        conqueror = foreign[int(rng.integers(len(foreign)))]
                        events.append(ForeignElite(year, conqueror, region))
                        later = year + STEP * _steps(rng, spans, "elite_steps")
                        if later < end:
                            events.append(EliteAssimilation(later, conqueror, region))
        year += STEP
    return events
