"""Světové události: mění strukturu světa, nikdy repertoár přímo (iterace 4)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from cee.v2.history import History
from cee.v2.repertoire import Distribution
from cee.v2.world import (
    TERRITORY_LEVELS,
    Link,
    LinkKind,
    SpeechGroup,
    Territory,
    TerritoryLevel,
    World,
)


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
class Contact(WorldEvent):
    """Skupiny začnou spolu mluvit (obchod, sousedství, dobytí)."""

    year: float
    pairs: tuple[tuple[str, str], ...]
    strength: float = 0.5
    kind: LinkKind = "weak"

    def apply(self, world: World, history: History, tick: int) -> None:
        for first, second in self.pairs:
            world.connect(first, second, self.strength, self.kind)
        history.record("contact", tick, self.year, pairs=[list(pair) for pair in self.pairs],
                       strength=self.strength)


@dataclass(frozen=True)
class LanguageShift(WorldEvent):
    """Dospělí ze skupiny ``group`` se začnou učit kód skupiny ``target``.

    Vznikne nová skupina téže komunity: mluví kódem cílového jazyka, který
    se její členové naučili jako druhý (``l2_share`` = 1), a do kterého proto
    nesou svůj první jazyk. Další průběh (kolik mluvčích přejde, kdy se
    starý kód přestanou učit děti, zda vymře) řídí
    :func:`cee.v2.contact.community_step`.
    """

    year: float
    group: str
    target: str
    #: Podíl komunity, který se cílový kód naučí hned na začátku.
    initial_share: float = 0.1
    #: Jak velkou část vstupu bere nová skupina od rodilých mluvčích cílového
    #: jazyka. Komunita, která jazyk mění, se ho učí hlavně sama od sebe.
    openness: float = 0.2
    internal_strength: float = 0.8

    def apply(self, world: World, history: History, tick: int) -> None:
        source, target = world.groups[self.group], world.groups[self.target]
        world.materialize(target.id)
        code = target.main_code.branch()
        code.acquisition, code.l1_source, code.l2_share = "L2", source.id, 1.0
        community = source.community or source.id
        source.community = community
        population = max(1, round(source.population * self.initial_share))
        source.population = max(1, source.population - population)
        group = world.add_group(
            SpeechGroup(
                id=f"{source.id}>{code.language}",
                territory=source.territory,
                population=population,
                codes=[code],
                generation_years=source.generation_years,
                prestige=target.prestige,
                openness=self.openness,
                community=community,
            )
        )
        # Novým kódem mluví s těmi sousedy, kteří ho už umějí: s rodilými
        # mluvčími i se sousedními komunitami, které na něj přecházejí také.
        for link in world.neighbors(source.id):
            neighbor = world.groups[link.target]
            for other in world.group_ids():
                peer = world.groups[other]
                same_community = other == neighbor.id or (
                    neighbor.community is not None and peer.community == neighbor.community
                )
                if same_community and other != group.id and peer.main_code.language == code.language:
                    world.connect(group.id, other, link.strength, link.kind)
        world.connect(group.id, source.id, self.internal_strength, "strong")
        history.record(
            "bilingualism", tick, self.year, group=source.id, learners=group.id,
            language=code.language, population=population,
        )


@dataclass(frozen=True)
class Codification(WorldEvent):
    """Vznik písma: řeč skupiny ``source`` (obvykle elity) se zapíše a zmrazí.

    Vznikne psaný kód jako samostatná skupina bez mluvčích: v každé proměnné
    má jen variantu, která v roce kodifikace v řeči ``source`` převládala.
    Skupiny ``readers`` ho znají a čtou s gramotností ``literacy``.
    """

    year: float
    source: str
    readers: tuple[str, ...]
    literacy: float = 0.05

    def apply(self, world: World, history: History, tick: int) -> None:
        source = world.groups[self.source]
        world.materialize(source.id)
        code = source.main_code.branch()
        for variable_id in sorted(world.variables):
            distribution = code.repertoire.get(variable_id)
            if distribution is not None and not distribution.is_fixed:
                code.repertoire.set(variable_id, Distribution.fixed(distribution.dominant()[0]))
        code.l1_source, code.l2_share = None, 0.0
        written = world.add_group(
            SpeechGroup(
                id=f"written:{source.id}", territory=source.territory, population=source.population,
                codes=[code], generation_years=WRITTEN_GENERATION, prestige=source.prestige,
                openness=0.0, written=True,
            )
        )
        # Jednosměrná vazba: psaný kód může sledovat řeč zdroje (viz Printing),
        # zdroj se od něj přes síť neučí.
        world.links[(written.id, source.id)] = Link(written.id, source.id, 1.0, "weak")
        for reader in self.readers:
            group = world.groups[reader]
            group.standard = written.id
            group.literacy = max(group.literacy, self.literacy)
        history.record("codification", tick, self.year, source=source.id, written=written.id,
                       readers=sorted(self.readers), literacy=self.literacy)


#: Jak často se psaná norma reviduje, když sleduje řeč (let).
WRITTEN_GENERATION = 100.0


@dataclass(frozen=True)
class Printing(WorldEvent):
    """Tisk a široká vrstva píšících: psaná norma začne sledovat řeč zdroje.

    ``update`` je podíl řeči zdroje v každé revizi normy (jednou za
    :data:`WRITTEN_GENERATION` let). Do té doby psaný kód stojí.
    """

    year: float
    written: str
    update: float = 0.3

    def apply(self, world: World, history: History, tick: int) -> None:
        world.groups[self.written].openness = self.update
        history.record("printing", tick, self.year, written=self.written, update=self.update)


@dataclass(frozen=True)
class Schooling(WorldEvent):
    """Školy: děti skupin ``groups`` se učí i z psaného kódu, který skupina zná."""

    year: float
    groups: tuple[str, ...]
    schooling: float = 0.8
    literacy: float = 0.8

    def apply(self, world: World, history: History, tick: int) -> None:
        for group_id in self.groups:
            group = world.groups[group_id]
            group.schooling = max(group.schooling, self.schooling)
            group.literacy = max(group.literacy, self.literacy)
        history.record("schooling", tick, self.year, groups=sorted(self.groups),
                       schooling=self.schooling, literacy=self.literacy)


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
                    codes=[code.branch() for code in aggregate.codes],
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
