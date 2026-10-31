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

**Spisovný jazyk** (``Standard``, ``Schools``) zapíše řeč sídla státu
nebo regionu a rozšíří gramotnost a školu po regionech; vrstvy písma,
tisku a školy (M6a) jsou tytéž, jen zadané po regionech. Vlastní norma
zvedne prestiž svého jazyka, a tak brzdí přechod na jiný.

Jestli jazyk regionu přežije, rozhoduje jeho demografie, terén (dosah
státu) a loajalita (odlišnost regionu); autor může jazyk výslovně
zakonzervovat (``Preserve``).

**Hranice** se nezadávají: vzniknou tam, kde sousedí regiony různých
států, a oslabí vazby přes sebe (``border``). **Prestiž** se po každé
události státu spočítá znovu ze stavu světa (:func:`refresh`): základ
regionu × hlavní město existujícího státu × vlastní spisovná norma. Rozpad
státu (``Collapse``) nebo odtržení (``Secession``) proto status jazyků
změní. **Lingua franca** je
týž mechanismus bez státu: komunity různých jazyků se jedním kódem
domlouvají mimo domov; učí se ho dospělí, takže se zjednodušuje (L2 tlaky)
a nese stopy jejich jazyků.

Autor zadává regiony a slovní úrovně (``"strong"``, ``"enforced"``…);
čísla jsou v ``world.params`` a kalibrují se. Je to přiblížení: stát nemá
hospodářství ani armádu, jen tyto tři páky.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from cee.v2.events import Codification, LanguageShift, Printing, Schooling, WorldEvent
from cee.v2.history import History
from cee.v2.parameters import level
from cee.v2.world import Link, SpeechGroup, World


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
    border: str = "normal"
    #: Vazby vesnic k sídlu, které stát vytvořil (centralizace): skupina → síla.
    links: dict[str, float] = field(default_factory=dict)


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
    """Největší vesnice regionu (při shodě první podle ID).

    Přednost mají rodilé skupiny před těmi, které na jazyk teprve přešly.
    """
    found = groups_in(world, [region])
    if not found:
        raise ValueError(f"Region '{region}' nemá žádnou vesnici.")
    return min(found, key=lambda group_id: (
        world.groups[group_id].main_code.l1_source is not None, -world.groups[group_id].population, group_id,
    ))


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
        # Úřední jazyk se mimo domov užívá i psaný: veřejná skupina čte normu zdroje.
        if source.standard is not None:
            existing.standard = source.standard
            existing.literacy = max(group.literacy, source.literacy)
    if link > 0:
        current = world.links.get((public_id, source_id))
        if current is None or current.strength < link:
            world.connect(public_id, source_id, link, "weak")
    world.prestige_mirror[public_id] = source_id
    nativized = f"{group_id}>{source.main_code.language}:home"
    if nativized in world.groups:
        world.prestige_mirror[nativized] = source_id
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
            polity.links[group_id] = value
            linked += 1
    return linked


def _release(world: World, polity: Polity, regions: tuple[str, ...]) -> None:
    """Stát opustí regiony: zmizí jeho vazby k sídlu a jeho politika tam."""
    wanted = set(regions)
    for group_id in sorted(polity.links):
        if group_id in world.groups and region_of(world, group_id) in wanted:
            for key in ((group_id, polity.seat), (polity.seat, group_id)):
                world.links.pop(key, None)
                world.border_factors.pop(key, None)
            del polity.links[group_id]
    for group_id, mirrored in sorted(world.prestige_mirror.items()):
        group = world.groups.get(group_id)
        if group is None or mirrored != polity.seat or region_of(world, group_id) not in wanted:
            continue
        # Lidé jazyk umějí dál, ale stát už ho domů netlačí.
        if group.domain == "public":
            group.home_pull = 0.0
        elif group.home_pull > 0:
            group.home_pull = 1e-6


@dataclass(frozen=True)
class State(WorldEvent):
    """Vznik státu z regionů ``regions`` s hlavním městem v regionu ``capital``.

    - vesnice hlavního města mají ``Parameters.capital_prestige``× prestiž, dokud
      stát trvá (:func:`refresh`);
    - hranice s regiony jiných států a mimo státy oslabí vazby přes sebe
      (``border``: ``open``, ``normal``, ``closed``);
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
    #: Propustnost hranice státu: ``open``, ``normal``, ``closed``.
    border: str = "normal"

    def apply(self, world: World, history: History, tick: int) -> None:
        if self.id in world.states:
            raise ValueError(f"Stát '{self.id}' už existuje.")
        _check_regions(world, self.regions)
        if self.capital not in self.regions:
            raise ValueError(f"Hlavní město '{self.capital}' musí ležet ve státě '{self.id}'.")
        owned = sorted(r for polity in world.states.values() for r in polity.regions if r in self.regions)
        if owned:
            raise ValueError(f"Regiony {owned} už patří jinému státu; použij Annexation nebo Secession.")
        level(world.params.centralization_levels, self.centralization, "úroveň centralizace")
        level(world.params.policy_levels, self.policy, "jazyková politika")
        level(world.params.border_levels, self.border, "propustnost hranice")
        seat = seat_of(world, self.capital)
        polity = Polity(self.id, tuple(self.regions), self.capital, seat,
                        world.groups[seat].main_code.language, self.centralization, self.policy, self.border)
        world.states[self.id] = polity
        refresh(world)
        linked = _centralize(world, polity, polity.regions)
        bilingual = _policy(world, history, tick, self.year, polity)
        refresh(world)
        history.record("state", tick, self.year, state=self.id, regions=sorted(self.regions),
                       capital=self.capital, seat=seat, language=polity.language,
                       centralization=self.centralization, policy=self.policy, border=self.border,
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
    """Stát ``state`` připojí regiony ``regions`` (dobytí, sňatek, unie).

    Stát, který tím přijde o hlavní město, zanikne (jako ``Collapse``).
    """

    year: float
    state: str
    regions: tuple[str, ...]

    def apply(self, world: World, history: History, tick: int) -> None:
        polity = _polity(world, self.state)
        _check_regions(world, self.regions)
        fallen = _take(world, self.regions, keep=polity.id)
        added = tuple(region for region in self.regions if region not in polity.regions)
        polity.regions = (*polity.regions, *added)
        refresh(world)
        linked = _centralize(world, polity, added)
        bilingual = _policy(world, history, tick, self.year, polity)
        refresh(world)
        history.record("annexation", tick, self.year, state=self.state, regions=sorted(added),
                       linked=linked, bilingual=bilingual, fallen=fallen)


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


def _take(world: World, regions: tuple[str, ...], *, keep: str | None = None) -> list[str]:
    """Regiony odejdou ze všech států kromě ``keep``; vrací zaniklé státy.

    Při odtržení (``keep is None``) hlavní město odejít nesmí. Při připojení
    (``keep`` = dobyvatel) stát, který přijde o hlavní město, zanikne.
    """
    fallen = []
    for other in sorted(world.states.values(), key=lambda found: found.id):
        if other.id == keep:
            continue
        leaving = tuple(region for region in other.regions if region in regions)
        if not leaving:
            continue
        if other.capital in leaving:
            if keep is None:
                raise ValueError(f"Hlavní město státu '{other.id}' se nemůže odtrhnout; použij Collapse.")
            _release(world, other, other.regions)
            del world.states[other.id]
            fallen.append(other.id)
            continue
        _release(world, other, leaving)
        other.regions = tuple(region for region in other.regions if region not in regions)
    return fallen


@dataclass(frozen=True)
class Secession(WorldEvent):
    """Regiony ``regions`` se odtrhnou a vytvoří nový stát ``id`` (jako ``State``)."""

    year: float
    id: str
    regions: tuple[str, ...]
    capital: str
    centralization: str = "moderate"
    policy: str = "tolerant"
    border: str = "normal"

    def apply(self, world: World, history: History, tick: int) -> None:
        _check_regions(world, self.regions)
        _take(world, self.regions)
        history.record("secession", tick, self.year, state=self.id, regions=sorted(self.regions))
        State(self.year, self.id, self.regions, self.capital, self.centralization, self.policy,
              self.border).apply(world, history, tick)


@dataclass(frozen=True)
class Collapse(WorldEvent):
    """Stát ``state`` zanikne: hlavní město ztratí status, hranice a politika zmizí.

    Spisovná norma zůstane (jako latina po Římu) a lidé úřední jazyk umějí
    dál, jen ho už nikdo netlačí domů.
    """

    year: float
    state: str

    def apply(self, world: World, history: History, tick: int) -> None:
        polity = _polity(world, self.state)
        _release(world, polity, polity.regions)
        del world.states[self.state]
        refresh(world)
        history.record("collapse", tick, self.year, state=self.state, regions=sorted(polity.regions))


@dataclass(frozen=True)
class BorderPolicy(WorldEvent):
    """Stát ``state`` změní propustnost hranice (``open``, ``normal``, ``closed``)."""

    year: float
    state: str
    border: str

    def apply(self, world: World, history: History, tick: int) -> None:
        polity = _polity(world, self.state)
        level(world.params.border_levels, self.border, "propustnost hranice")
        polity.border = self.border
        refresh(world)
        history.record("border_policy", tick, self.year, state=self.state, border=self.border)


@dataclass(frozen=True)
class Preserve(WorldEvent):
    """Autor zakonzervuje jazyk regionů ``regions``: nikdo z něj nepřejde jinam.

    ``language`` je linie jazyka; ``None`` = původní jazyk každého regionu
    (jazyk jeho největší rodilé vesnice). Jazyk se dál mění, jen nevymře
    a neztrácí mluvčí. ``preserved=False`` konzervaci zruší.
    """

    year: float
    regions: tuple[str, ...]
    language: str | None = None
    preserved: bool = True

    def apply(self, world: World, history: History, tick: int) -> None:
        _check_regions(world, self.regions)
        groups = []
        for region in self.regions:
            language = self.language or _language_of(world, seat_of(world, region))
            for group_id in groups_in(world, [region]):
                if world.groups[group_id].main_code.language == language:
                    world.groups[group_id].preserved = self.preserved
                    groups.append(group_id)
        history.record("preserve", tick, self.year, regions=sorted(self.regions), language=self.language,
                       preserved=self.preserved, groups=groups)


@dataclass(frozen=True)
class Revival(WorldEvent):
    """Obrozenecké hnutí: regiony ``regions`` se vracejí k jazyku ``language``.

    ``language`` je linie; ``None`` = původní jazyk regionu. ``strength``
    (``movement``, ``national``) určí tempo, kterým se rodiny, jež přešly
    na jiný jazyk, k němu vracejí (obousměrný přechod v
    :func:`cee.v2.contact._shift`); mluvčí si jazyk předávají i pod prahem
    užívání. Obce, kde jazyk už nikdo nemluví, ho dostanou zpět jako noví
    mluvčí (podíl ``seed``): od sousedů, kteří ho ještě mluví, nebo z písma
    (hebrejština, kornština). Bez mluvčích i bez písma jazyk oživit nejde.
    Jestli se obrození ujme, rozhoduje dál status a demografie: pomůže
    vlastní stát (``Secession``), norma a škola.
    """

    year: float
    regions: tuple[str, ...]
    language: str | None = None
    strength: str = "movement"

    def apply(self, world: World, history: History, tick: int) -> None:
        _check_regions(world, self.regions)
        table = level(world.params.revival_levels, self.strength, "síla obrození")
        pace, seed = float(table["pace"]), float(table["seed"])
        speakers, revived = [], []
        for region in self.regions:
            language = self.language or world.territories[region].native_language
            if language is None:
                raise ValueError(f"Region '{region}' nezná svůj původní jazyk; zadej language.")
            home = groups_in(world, [region])
            for group_id in home:
                if world.groups[group_id].main_code.language == language:
                    world.groups[group_id].revival = max(world.groups[group_id].revival, pace)
                    speakers.append(group_id)
            for group_id in home:
                group = world.groups[group_id]
                community = group.community or group_id
                if group.main_code.language == language or any(
                    (world.groups[other].community or other) == community
                    and world.groups[other].domain == "home"
                    and world.groups[other].main_code.language == language
                    for other in world.group_ids()
                ):
                    continue
                created = _revive(world, group_id, language, region, pace, seed)
                if created is not None:
                    revived.append(created)
        refresh(world)
        history.record("revival_movement", tick, self.year, regions=sorted(self.regions),
                       language=self.language, strength=self.strength, speakers=speakers, revived=revived)


def _donor(world: World, group_id: str, language: str, region: str) -> str | None:
    """Odkud se ztracený jazyk naučit: soused, který ho mluví, jinak jeho písmo."""
    for link in sorted(world.neighbors(group_id), key=lambda found: (-found.strength, found.target)):
        peer = world.groups[link.target]
        if not peer.written and peer.domain == "home" and peer.main_code.language == language:
            return link.target
    written = world.standards.get(region)
    if written is not None and written in world.groups and _language_of(world, written) == language:
        return written
    for candidate in world.group_ids():
        if world.groups[candidate].written and world.groups[candidate].main_code.language == language:
            return candidate
    return None


def _revive(world: World, group_id: str, language: str, region: str, pace: float, seed: float) -> str | None:
    donor = _donor(world, group_id, language, region)
    group = world.groups[group_id]
    new_id = f"{group_id}>{language}:revived"
    if donor is None or new_id in world.groups:
        return None
    world.materialize(donor)
    code = world.groups[donor].main_code.branch()
    code.acquisition, code.l1_source, code.l2_share = "L2", group_id, 1.0
    community = group.community or group_id
    group.community = community
    written = donor if world.groups[donor].written else world.groups[donor].standard
    created = world.add_group(SpeechGroup(
        id=new_id, territory=group.territory, population=max(1, round(group.population * seed)),
        codes=[code], generation_years=group.generation_years,
        prestige=world.base_prestige.get(group_id, group.prestige), openness=group.openness,
        community=community, home_pull=pace, loyalty=group.loyalty, revival=pace,
        standard=written, literacy=max(group.literacy, 0.5 if written else 0.0),
    ))
    world.base_prestige[new_id] = created.prestige
    world.connect(new_id, group_id, 0.8, "strong")
    for link in world.neighbors(group_id):
        neighbour = world.groups[link.target]
        neighbourhood = neighbour.community or link.target
        for other in world.group_ids():
            peer = world.groups[other]
            if other == new_id or peer.written or peer.main_code.language != language:
                continue
            if other == link.target or (peer.community or other) == neighbourhood:
                world.connect(new_id, other, link.strength, link.kind)
    return new_id


def refresh(world: World) -> None:
    """Hranice a prestiž ze stavu světa (po každé události státu).

    Vazba mezi regiony různých států (nebo státu a regionu mimo státy) má
    sílu základ × propustnost méně propustné hranice; základ si vazba drží
    v ``world.border_factors``, takže připojení hranici zase zruší. Prestiž
    domácí skupiny je základ × ``capital_prestige`` (hlavní město
    existujícího státu) × ``standard_prestige`` (čte normu svého jazyka);
    skupiny v ``world.prestige_mirror`` přebírají prestiž své předlohy.
    """
    params = world.params
    owner = {region: polity.id for polity in sorted(world.states.values(), key=lambda p: p.id)
             for region in polity.regions}
    openness = {polity.id: float(params.border_levels[polity.border]) for polity in world.states.values()}
    regions = {group_id: region_of(world, group_id) for group_id in world.group_ids()}
    for key in sorted(world.links):
        first, second = key
        if world.groups[first].written or world.groups[second].written:
            continue
        here, there = regions[first], regions[second]
        factor = 1.0
        if here is not None and there is not None and owner.get(here) != owner.get(there):
            factor = min(openness.get(owner.get(here), 1.0), openness.get(owner.get(there), 1.0))
        old = world.border_factors.get(key, 1.0)
        if factor == old:
            continue
        link = world.links[key]
        world.links[key] = Link(first, second, min(1.0, link.strength / old) * factor, link.kind)
        if factor == 1.0:
            del world.border_factors[key]
        else:
            world.border_factors[key] = factor
    for key in [key for key in world.border_factors if key not in world.links]:
        del world.border_factors[key]

    capitals = {polity.capital for polity in world.states.values()}
    for group_id in world.group_ids():
        group = world.groups[group_id]
        if group.written or group.domain != "home" or group_id in world.prestige_mirror:
            continue
        base = world.base_prestige.setdefault(group_id, group.prestige)
        factor = params.capital_prestige if regions[group_id] in capitals else 1.0
        standard = world.groups.get(group.standard) if group.standard is not None else None
        if standard is not None and standard.main_code.language == group.main_code.language:
            factor *= params.standard_prestige
        group.prestige = base * factor
    for group_id, model in sorted(world.prestige_mirror.items()):
        if group_id in world.groups and model in world.groups:
            world.groups[group_id].prestige = world.groups[model].prestige
    for stale in [group_id for group_id in world.base_prestige if group_id not in world.groups]:
        del world.base_prestige[stale]
    for stale in [group_id for group_id in world.prestige_mirror if group_id not in world.groups]:
        del world.prestige_mirror[stale]


def borders(world: World) -> list[dict[str, Any]]:
    """Hranice států pro mapu: dvojice sousedních regionů různých států.

    Sousedé jsou regiony, mezi jejichž vesnicemi vede vazba. ``factor`` je
    propustnost hranice (násobek vazeb přes ni).
    """
    owner = {region: polity.id for polity in sorted(world.states.values(), key=lambda p: p.id)
             for region in polity.regions}
    regions = {group_id: region_of(world, group_id) for group_id in world.group_ids()}
    found: dict[tuple[str, str], float] = {}
    for (first, second), _ in sorted(world.links.items()):
        here, there = regions.get(first), regions.get(second)
        if here is None or there is None or here >= there or owner.get(here) == owner.get(there):
            continue
        factor = world.border_factors.get((first, second), 1.0)
        found[(here, there)] = min(found.get((here, there), factor), factor)
    return [
        {"regions": [here, there], "states": [owner.get(here), owner.get(there)], "factor": factor}
        for (here, there), factor in sorted(found.items())
    ]


def states(world: World) -> list[dict[str, Any]]:
    """Státy pro export: území, sídlo, úřední jazyk, úrovně a spisovná norma."""
    return [
        {"id": polity.id, "regions": list(polity.regions), "capital": polity.capital, "seat": polity.seat,
         "language": polity.language, "centralization": polity.centralization, "policy": polity.policy,
         "border": polity.border, "standard": world.standards.get(polity.id)}
        for polity in sorted(world.states.values(), key=lambda found: found.id)
    ]


def _language_of(world: World, group_id: str) -> str:
    return world.groups[group_id].main_code.language


def _scope(world: World, of: str) -> tuple[tuple[str, ...], str, bool]:
    """Regiony, sídlo a zda jde o stát pro ``of`` (ID státu, nebo regionu)."""
    if of in world.states:
        polity = world.states[of]
        return polity.regions, polity.seat, True
    territory = world.territories.get(of)
    if territory is None or territory.level != "region":
        raise ValueError(f"'{of}' není stát ani region světa.")
    return (of,), seat_of(world, of), False


def _readers(world: World, regions: tuple[str, ...]) -> list[str]:
    """Mluvené skupiny regionů včetně veřejné domény (čtou a chodí do školy)."""
    wanted = set(regions)
    return [
        group_id for group_id in world.group_ids()
        if not world.groups[group_id].written and region_of(world, group_id) in wanted
    ]


@dataclass(frozen=True)
class Standard(WorldEvent):
    """Spisovný jazyk státu nebo regionu ``of``: zapíše se řeč jeho sídla.

    Pro stát je to řeč sídla státu (úřední jazyk), pro region řeč jeho
    největší vesnice (vlastní norma menšinového jazyka). Gramotnost
    ``literacy`` (``elite``, ``towns``, ``mass``) se násobí dosahem centra.
    Skupina čte normu svého jazyka; cizí normu jen tehdy, když vlastní nemá
    (učené výpůjčky). Mluvčí, kteří čtou normu svého jazyka, mají
    ``Parameters.standard_prestige``× vyšší prestiž (:func:`refresh`).
    """

    year: float
    of: str
    literacy: str = "elite"

    def apply(self, world: World, history: History, tick: int) -> None:
        regions, seat, is_state = _scope(world, self.of)
        share = float(level(world.params.literacy_levels, self.literacy, "úroveň gramotnosti"))
        if self.of in world.standards or f"written:{seat}" in world.groups:
            raise ValueError(f"'{self.of}' už spisovný jazyk má; školu přidá událost Schools.")
        Codification(self.year, seat, (), 0.0).apply(world, history, tick)
        written = f"written:{seat}"
        world.standards[self.of] = written
        language = _language_of(world, written)
        readers = []
        for group_id in _readers(world, regions):
            group = world.groups[group_id]
            own = group.main_code.language == language
            current = group.standard if group.standard in world.groups else None
            if current is not None and (not own or _language_of(world, current) == group.main_code.language):
                continue
            group.standard = written
            group.literacy = max(group.literacy, share * reach(world, group_id, seat, distance=is_state))
            readers.append(group_id)
        refresh(world)
        history.record("standard", tick, self.year, of=self.of, written=written, language=language,
                       literacy=self.literacy, readers=readers)


@dataclass(frozen=True)
class Schools(WorldEvent):
    """Školy ve státě nebo regionu ``of``: děti se učí spisovný jazyk.

    ``coverage`` (``towns``, ``mass``) je podíl dětí ve škole, násobený
    dosahem centra. Školou prochází jen řeč jazyka normy (standardizace,
    nářečí ustupují); regiony jiného jazyka spisovný jazyk státu čtou a
    jeho mluvčí mimo domov se ho učí ve škole. Asimilaci školou zadává
    ``LanguagePolicy("enforced")``. S ``printing`` norma sleduje řeč sídla
    (moderní spisovné jazyky), s ``diglossic`` se učí jako samostatná vysoká
    varieta a stojí (Ferguson 1959). Vyžaduje dřívější ``Standard``.
    """

    year: float
    of: str
    coverage: str = "mass"
    printing: bool = True
    diglossic: bool = False

    def apply(self, world: World, history: History, tick: int) -> None:
        regions, seat, is_state = _scope(world, self.of)
        written = world.standards.get(self.of)
        if written is None:
            raise ValueError(f"'{self.of}' nemá spisovný jazyk; nejdřív událost Standard.")
        source = written.removeprefix("written:")
        seat = source if source in world.groups else seat  # dosah se měří od sídla normy
        share = float(level(world.params.schooling_levels, self.coverage, "úroveň školství"))
        language = _language_of(world, written)
        pupils = []
        for group_id in _readers(world, regions):
            group = world.groups[group_id]
            if group.standard != written and group.standard in world.groups:
                continue  # chodí do školy vlastní normy
            group.standard = written
            value = share * reach(world, group_id, seat, distance=is_state)
            group.literacy = max(group.literacy, value)
            if group.main_code.language != language:
                continue
            if self.diglossic and group.domain == "home":
                Schooling(self.year, (group_id,), value, value, diglossic=True).apply(world, history, tick)
            else:
                group.schooling = max(group.schooling, value)
            pupils.append(group_id)
        if self.printing and not self.diglossic:
            Printing(self.year, written).apply(world, history, tick)
        history.record("schools", tick, self.year, of=self.of, coverage=self.coverage,
                       printing=self.printing, diglossic=self.diglossic, pupils=pupils)


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
