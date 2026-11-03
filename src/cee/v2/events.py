"""Světové události: mění strukturu světa, nikdy repertoár přímo (iterace 4)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Sequence

from cee.v2.edits import Edit, Edits, by_tick
from cee.v2.history import History
from cee.v2.world import (
    TERRITORY_LEVELS,
    LinkKind,
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
        edit = Edits(world, tick)
        weakened = 0
        for first in self.side_a:
            for second in self.side_b:
                link = world.links.get((first, second))
                if link is None:
                    continue
                edit.connect(first, second, link.strength * self.factor, link.kind)
                weakened += 1
        history.record(
            "border", tick, self.year,
            side_a=sorted(self.side_a), side_b=sorted(self.side_b),
            factor=self.factor, weakened_links=weakened,
        )


@dataclass(frozen=True)
class Contact(WorldEvent):
    """Skupiny začnou spolu mluvit (obchod, sousedství, dobytí).

    S ``trade`` je vazba obchodní cesta: slova přes ni procházejí kanálem
    ``trade`` (``Parameters.channel_domains``, hlavně kultura a věci), jinak
    je to obecný kontakt sousedů.
    """

    year: float
    pairs: tuple[tuple[str, str], ...]
    strength: float = 0.5
    kind: LinkKind = "weak"
    trade: bool = False

    def apply(self, world: World, history: History, tick: int) -> None:
        edit = Edits(world, tick)
        for first, second in self.pairs:
            edit.connect(first, second, self.strength, self.kind)
            if self.trade:
                edit.set_trade(first, second, world.links[(first, second)].strength)
            else:
                edit.set_trade(first, second, None)
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
    #: ``home``: nový kód vytlačí starý (přechod). ``public``: komunita ho
    #: užívá jen mimo domov a děti se doma učí dál svůj jazyk (stabilní
    #: dvojjazyčnost); ``initial_share`` je pak podíl dvojjazyčných.
    domain: Literal["home", "public"] = "home"

    def apply(self, world: World, history: History, tick: int) -> None:
        edit = Edits(world, tick)
        source, target = world.groups[self.group], world.groups[self.target]
        language = target.main_code.language
        community = source.community or source.id
        edit.set_group(source.id, "community", community)
        population = max(1, round(source.population * self.initial_share))
        if self.domain == "home":
            edit.set_group(source.id, "population", max(1, source.population - population))
        group_id = f"{source.id}>{language}"
        edit.add_group(
            group_id, source.territory, population, target.id,
            generation_years=source.generation_years, prestige=target.prestige, openness=self.openness,
            community=community, domain=self.domain,
        )
        edit.set_code(group_id, acquisition="L2", l1_source=source.id, l2_share=1.0)
        # Novým kódem mluví s těmi sousedy, kteří ho už umějí: s rodilými
        # mluvčími i se sousedními komunitami, které na něj přecházejí také.
        for link in world.neighbors(source.id):
            neighbor = world.groups[link.target]
            for other in world.group_ids():
                peer = world.groups[other]
                same_community = other == neighbor.id or (
                    neighbor.community is not None and peer.community == neighbor.community
                )
                if same_community and other != group_id and peer.main_code.language == language:
                    edit.connect(group_id, other, link.strength, link.kind)
        edit.connect(group_id, source.id, self.internal_strength, "strong")
        history.record(
            "bilingualism", tick, self.year, group=source.id, learners=group_id,
            language=language, population=population, domain=self.domain,
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
        edit = Edits(world, tick)
        source = world.groups[self.source]
        written = f"written:{source.id}"
        edit.add_group(
            written, source.territory, source.population, source.id, generation_years=WRITTEN_GENERATION,
            prestige=source.prestige, openness=0.0, written=True,
        )
        edit.fix_code(written)
        edit.set_code(written, l1_source=None, l2_share=0.0)
        # Jednosměrná vazba: psaný kód může sledovat řeč zdroje (viz Printing),
        # zdroj se od něj přes síť neučí.
        edit.set_link(written, source.id, 1.0, "weak")
        for reader in self.readers:
            group = world.groups[reader]
            edit.set_group(reader, "standard", written)
            edit.set_group(reader, "literacy", max(group.literacy, self.literacy))
        history.record("codification", tick, self.year, source=source.id, written=written,
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
        Edits(world, tick).set_group(self.written, "openness", self.update)
        history.record("printing", tick, self.year, written=self.written, update=self.update)


@dataclass(frozen=True)
class Schooling(WorldEvent):
    """Školy: děti skupin ``groups`` se učí i z psaného kódu, který skupina zná.

    Výchozí škola vlévá psaný kód do mluvené řeči (standardizace). S
    ``diglossic`` se psaný kód učí jako samostatná vysoká varieta (Ferguson
    1959): každá skupina dostane skupinu veřejné domény, která mluví psaným
    kódem naučeným ve škole, s interferencí z lidové řeči. Lidová řeč sama
    školou neprochází, jen čtením přejímá učená slova.
    """

    year: float
    groups: tuple[str, ...]
    schooling: float = 0.8
    literacy: float = 0.8
    diglossic: bool = False

    def apply(self, world: World, history: History, tick: int) -> None:
        edit = Edits(world, tick)
        created = {}
        for group_id in self.groups:
            group = world.groups[group_id]
            edit.set_group(group_id, "literacy", max(group.literacy, self.literacy))
            if not self.diglossic:
                edit.set_group(group_id, "schooling", max(group.schooling, self.schooling))
                continue
            if group.standard not in world.groups:
                continue
            written = world.groups[group.standard]
            edit.set_group(group_id, "community", group.community or group.id)
            high_id = f"{group.id}>H"
            edit.add_group(
                high_id, group.territory, max(1, round(group.population * self.schooling)), written.id,
                generation_years=group.generation_years, prestige=written.prestige, openness=group.openness,
                schooling=1.0, literacy=1.0, standard=written.id, community=group.community, domain="public",
            )
            edit.set_code(high_id, acquisition="L2", l1_source=group.id, l2_share=1.0)
            created[group_id] = high_id
        # Vysokou varietou spolu mluví vzdělaní lidé sousedních komunit.
        for group_id, high_id in sorted(created.items()):
            for link in world.neighbors(group_id):
                if link.target in created:
                    edit.connect(high_id, created[link.target], link.strength, link.kind)
        history.record("schooling", tick, self.year, groups=sorted(self.groups),
                       schooling=self.schooling, literacy=self.literacy, diglossic=self.diglossic)


@dataclass(frozen=True)
class ReligiousChange(WorldEvent):
    """Skupiny přijmou náboženství s liturgickým kódem ``liturgy`` (psaný kód).

    ``devotion`` je podíl lidí, kteří liturgii slyší nebo čtou; přejímají z
    ní učená slova (latinismy, církevní slovanismy, arabismy, tatsama).
    ``network`` > 0 propojí skupiny slabými vazbami církevní správy.
    """

    year: float
    liturgy: str
    groups: tuple[str, ...]
    devotion: float = 0.3
    network: float = 0.0

    def apply(self, world: World, history: History, tick: int) -> None:
        if not world.groups[self.liturgy].written:
            raise ValueError(f"Liturgický kód '{self.liturgy}' musí být psaný kód.")
        edit = Edits(world, tick)
        for group_id in self.groups:
            edit.set_group(group_id, "liturgy", self.liturgy)
            edit.set_group(group_id, "devotion", self.devotion)
        if self.network > 0:
            members = sorted(self.groups)
            for index, first in enumerate(members):
                for second in members[index + 1 :]:
                    if (first, second) not in world.links:
                        edit.connect(first, second, self.network, "weak")
        history.record("religious_change", tick, self.year, liturgy=self.liturgy,
                       groups=sorted(self.groups), devotion=self.devotion)


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
        edit = Edits(world, tick)
        aggregate = aggregates[0]
        parent = world.territories[self.territory]
        level: TerritoryLevel = self.child_level or TERRITORY_LEVELS[-1]
        external = world.neighbors(aggregate.id)
        total_share = sum(spec.share for spec in self.settlements)

        # Sídla převezmou kódy souhrnné skupiny, ta zaniká až po nich.
        created: list[str] = []
        for spec in self.settlements:
            edit.add_territory(spec.id, level, parent.id, spec.position or parent.position, self.year)
            edit.add_group(
                spec.id, spec.id, max(1, round(aggregate.population * spec.share / total_share)), aggregate.id,
                codes="all", generation_years=aggregate.generation_years, prestige=aggregate.prestige,
                openness=aggregate.openness, literacy=aggregate.literacy, schooling=aggregate.schooling,
            )
            for link in external:
                edit.connect(spec.id, link.target, link.strength, link.kind)
            created.append(spec.id)
        for index, first in enumerate(created):
            for second in created[index + 1 :]:
                edit.connect(first, second, self.internal_strength, "strong")
        edit.remove_group(aggregate.id)
        history.record(
            "refinement", tick, self.year,
            territory=self.territory, aggregate=aggregate.id, groups=created,
        )


@dataclass(frozen=True)
class Migration(WorldEvent):
    """Část skupin se přestěhuje do sídla ``target``; když neexistuje, založí ho.

    Noví obyvatelé existujícího sídla se jeho řeč učí v dospělosti (podíl L2
    mluvčích vzroste). Nové sídlo (kolonie, nové město) převezme kód největší
    skupiny přistěhovalců; ostatní do něj vnášejí své varianty vazbami a jako
    L2 mluvčí. Nové sídlo dostane gravitační vazby k sídlům do ``reach`` km.
    """

    year: float
    sources: tuple[tuple[str, float], ...]
    target: str
    position: tuple[float, float] | None = None
    reach: float = 25.0
    prestige: float | None = None

    def apply(self, world: World, history: History, tick: int) -> None:
        edit = Edits(world, tick)
        moving = []
        for group_id, share in self.sources:
            group = world.groups[group_id]
            people = max(1, round(group.population * share))
            edit.set_group(group_id, "population", max(1, group.population - people))
            moving.append((people, group_id))
        arriving = sum(people for people, _ in moving)
        founded = self.target not in world.groups
        if founded:
            _, largest = max(moving, key=lambda item: (item[0], item[1]))
            origin = world.groups[largest]
            parent = world.territories[origin.territory].parent
            edit.add_territory(self.target, "settlement", parent, self.position)
            edit.add_group(
                self.target, self.target, arriving, largest, generation_years=origin.generation_years,
                prestige=origin.prestige if self.prestige is None else self.prestige, openness=origin.openness,
            )
            others = [other for other in world.group_ids()
                      if other != self.target and not world.groups[other].written]
            edit.connect_gravity([self.target, *others], max_distance=self.reach)
            native = max(people for people, _ in moving)
            edit.set_code(self.target, l2_share=(arriving - native) / arriving)
        else:
            group = world.groups[self.target]
            code = group.main_code
            edit.set_code(self.target, l2_share=(code.l2_share * group.population + arriving) / (group.population + arriving))
            edit.set_group(self.target, "population", group.population + arriving)
        history.record("migration", tick, self.year, target=self.target, founded=founded,
                       sources=[[group_id, people] for people, group_id in moving])


@dataclass(frozen=True)
class Conquest(WorldEvent):
    """Dobyvatelé usadí v sídle ``territory`` elitu s vysokou prestiží.

    Elita mluví kódem skupiny ``conqueror`` a má vazby na poddané
    (``subjects``); s dobyvateli doma ji spojuje dálková vazba.
    """

    year: float
    conqueror: str
    territory: str
    subjects: tuple[str, ...]
    population: int = 100
    prestige: float = 2.0
    strength: float = 0.5

    def apply(self, world: World, history: History, tick: int) -> None:
        edit = Edits(world, tick)
        origin = world.groups[self.conqueror]
        elite = f"{self.territory}+{origin.id}"
        edit.add_group(
            elite, self.territory, self.population, origin.id, generation_years=origin.generation_years,
            prestige=self.prestige, openness=origin.openness, elite=True,
        )
        for subject in self.subjects:
            edit.connect(elite, subject, self.strength, "weak")
        edit.connect(elite, origin.id, self.strength / 2, "weak")
        history.record("conquest", tick, self.year, elite=elite, conqueror=origin.id,
                       subjects=sorted(self.subjects))


@dataclass(frozen=True)
class War(WorldEvent):
    """Válka oslabí vazby přes frontu a obě strany ztratí část lidí."""

    year: float
    side_a: tuple[str, ...]
    side_b: tuple[str, ...]
    factor: float = 0.2
    losses: float = 0.2

    def apply(self, world: World, history: History, tick: int) -> None:
        Border(self.year, self.side_a, self.side_b, self.factor).apply(world, History(), tick)
        edit = Edits(world, tick)
        for group_id in (*self.side_a, *self.side_b):
            group = world.groups[group_id]
            edit.set_group(group_id, "population", max(1, round(group.population * (1.0 - self.losses))))
        history.record("war", tick, self.year, side_a=sorted(self.side_a), side_b=sorted(self.side_b),
                       factor=self.factor, losses=self.losses)


@dataclass(frozen=True)
class Epidemic(WorldEvent):
    """Epidemie: skupiny ztratí podíl ``mortality`` lidí (víc driftu v malých)."""

    year: float
    groups: tuple[str, ...]
    mortality: float = 0.3

    def apply(self, world: World, history: History, tick: int) -> None:
        edit = Edits(world, tick)
        for group_id in self.groups:
            group = world.groups[group_id]
            edit.set_group(group_id, "population", max(1, round(group.population * (1.0 - self.mortality))))
        history.record("epidemic", tick, self.year, groups=sorted(self.groups), mortality=self.mortality)


@dataclass(frozen=True)
class StateCollapse(WorldEvent):
    """Kolaps státu: zaniknou dálkové vazby, školy a většina gramotnosti."""

    year: float
    groups: tuple[str, ...]
    #: Vazby delší než tato vzdálenost (km) zaniknou.
    reach: float = 30.0
    literacy: float = 0.2

    def apply(self, world: World, history: History, tick: int) -> None:
        import math

        edit = Edits(world, tick)
        members = set(self.groups)
        cut = 0
        for (first, second), _ in sorted(world.links.items()):
            if first not in members and second not in members:
                continue
            a, b = world.position_of(first), world.position_of(second)
            if a is not None and b is not None and math.dist(a, b) > self.reach:
                edit.drop_link(first, second)
                cut += 1
        for group_id in self.groups:
            group = world.groups[group_id]
            edit.set_group(group_id, "schooling", 0.0)
            edit.set_group(group_id, "literacy", group.literacy * self.literacy)
        history.record("state_collapse", tick, self.year, groups=sorted(self.groups), links_cut=cut)


@dataclass(frozen=True)
class ReplayEdits(WorldEvent):
    """Přehraje zapsané změny světa jednoho ticku (deník změn, :mod:`cee.v2.edits`).

    Nahrazuje události: běh bez nich, ve kterém se v ticích deníku provedou
    tytéž operace, má dát stejný stav světa jako běh s událostmi. Rok je rok
    ticku (:func:`replay_events`), aby se událost provedla přesně v něm.
    """

    year: float
    edits: tuple[Edit, ...]

    def apply(self, world: World, history: History, tick: int) -> None:
        edit = Edits(world, tick)
        for item in self.edits:
            edit.replay(item)


def replay_events(journal: Sequence[Edit], *, start_year: float, dt: float) -> list[WorldEvent]:
    """Události přehrání deníku: jedna na každý tik s operacemi (rok jako ``Simulation.year``)."""
    return [ReplayEdits(start_year + tick * dt, edits) for tick, edits in by_tick(journal)]
