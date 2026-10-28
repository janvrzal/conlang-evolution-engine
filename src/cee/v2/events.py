"""Světové události: mění strukturu světa, nikdy repertoár přímo (iterace 4)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from cee.v2.history import History
from cee.v2.world import TERRITORY_LEVELS, Code, SpeechGroup, Territory, TerritoryLevel, World


class WorldEvent(ABC):
    """Událost v daném roce. Na jazyk působí jen nepřímo, přes přenos."""

    year: float

    @abstractmethod
    def apply(self, world: World, history: History, tick: int) -> None: ...


@dataclass(frozen=True)
class Border(WorldEvent):
    """Hranice: vazby přes ni zeslábnou na ``factor`` původní síly."""

    year: float
    side_a: tuple[str, ...]
    side_b: tuple[str, ...]
    factor: float = 0.1

    def apply(self, world: World, history: History, tick: int) -> None:
        weakened = 0
        for first in self.side_a:
            for second in self.side_b:
                link = world.links.get((first, second))
                if link is None:
                    continue
                world.connect(first, second, link.strength * self.factor, link.kind)
                weakened += 1
        history.record(
            "border", tick, self.year,
            side_a=sorted(self.side_a), side_b=sorted(self.side_b),
            factor=self.factor, weakened_links=weakened,
        )


@dataclass(frozen=True)
class SettlementSpec:
    """Jedno sídlo, na které se rozepíše souhrnná skupina."""

    id: str
    share: float
    position: tuple[float, float] | None = None


@dataclass(frozen=True)
class RefineTerritory(WorldEvent):
    """Zjemnění od roku X: souhrnnou skupinu nahradí skupiny jednotlivých sídel.

    Sídla převezmou repertoár souhrnné skupiny v roce zjemnění (copy-on-write)
    a populaci podle podílů. Vnější vazby souhrnné skupiny zdědí každé sídlo,
    sídla mezi sebou dostanou silné vazby. Dřívější historie zůstává hrubá.
    """

    year: float
    territory: str
    settlements: tuple[SettlementSpec, ...]
    internal_strength: float = 0.8
    child_level: TerritoryLevel | None = None

    def apply(self, world: World, history: History, tick: int) -> None:
        aggregates = [
            group for group in world.groups.values()
            if group.territory == self.territory and group.aggregate
        ]
        if len(aggregates) != 1:
            raise ValueError(
                f"Území '{self.territory}' musí mít právě jednu souhrnnou skupinu, má {len(aggregates)}."
            )
        if not self.settlements:
            raise ValueError("Zjemnění potřebuje alespoň jedno sídlo.")
        aggregate = aggregates[0]
        parent = world.territories[self.territory]
        level: TerritoryLevel = self.child_level or TERRITORY_LEVELS[-1]
        external = world.neighbors(aggregate.id)
        world.materialize(aggregate.id)
        total_share = sum(spec.share for spec in self.settlements)
        world.remove_group(aggregate.id)

        created: list[str] = []
        for spec in self.settlements:
            world.add_territory(
                Territory(
                    id=spec.id, level=level,
                    parent=parent.id, position=spec.position or parent.position,
                    refined_from_year=self.year,
                )
            )
            group = world.add_group(
                SpeechGroup(
                    id=spec.id,
                    territory=spec.id,
                    population=max(1, round(aggregate.population * spec.share / total_share)),
                    codes=[
                        Code(code.id, code.repertoire.branch(), code.usage_share,
                             code.acquisition, code.l1_source)
                        for code in aggregate.codes
                    ],
                    generation_years=aggregate.generation_years,
                    prestige=aggregate.prestige,
                    openness=aggregate.openness,
                    literacy=aggregate.literacy,
                    schooling=aggregate.schooling,
                )
            )
            for link in external:
                world.connect(group.id, link.target, link.strength, link.kind)
            created.append(group.id)
        for index, first in enumerate(created):
            for second in created[index + 1 :]:
                world.connect(first, second, self.internal_strength, "strong")
        history.record(
            "refinement", tick, self.year,
            territory=self.territory, aggregate=aggregate.id, groups=created,
        )
