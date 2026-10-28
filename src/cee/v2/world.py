"""Svět: strom území, skupiny mluvčích, jejich kódy a síť vazeb (iterace 4)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Mapping, Sequence

from cee.v2.language.lexicon import FormStore, Morpheme, PhonologyState
from cee.v2.language.processes import Process, StressRule
from cee.v2.language.segments import SegmentTable, default_table
from cee.v2.pools import LivePools
from cee.v2.repertoire import Distribution, Origin, Repertoire, Variable, Variant
from cee.v2.rng import stable_id

TerritoryLevel = Literal["world", "continent", "region", "area", "settlement"]
TERRITORY_LEVELS: tuple[TerritoryLevel, ...] = ("world", "continent", "region", "area", "settlement")

LinkKind = Literal["strong", "weak"]


@dataclass(slots=True)
class Territory:
    """Uzel stromu území. Bez potomků je území „nerozepsané“."""

    id: str
    level: TerritoryLevel
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    #: Poloha těžiště v mapových jednotkách (km). Gravitační vazby ji potřebují.
    position: tuple[float, float] | None = None
    #: ``None`` = rozepsáno od začátku běhu, jinak rok zjemnění.
    refined_from_year: float | None = None


@dataclass(slots=True)
class Code:
    """Jedna jazyková varieta, kterou skupina užívá."""

    id: str
    repertoire: Repertoire
    usage_share: float = 1.0
    acquisition: Literal["L1", "L2"] = "L1"
    l1_source: str | None = None
    #: Podkladové tvary morfémů, které se od výchozích liší.
    forms: FormStore = field(default_factory=FormStore)
    phonology: PhonologyState = field(default_factory=PhonologyState)
    stress_rule: StressRule = "penult"

    def branch(self) -> Code:
        """Nezávislá kopie kódu (zjemnění, odštěpení)."""
        return Code(
            self.id, self.repertoire.branch(), self.usage_share, self.acquisition,
            self.l1_source, self.forms.branch(), self.phonology.branch(), self.stress_rule,
        )


@dataclass(slots=True)
class SpeechGroup:
    """Základní jednotka simulace: lidé na jednom místě s vlastními kódy."""

    id: str
    territory: str
    population: int
    codes: list[Code]
    #: Délka generace v letech; fantasy národ může mít 500 let.
    generation_years: float = 25.0
    prestige: float = 0.5
    #: Jak velkou část vstupu nová generace bere od sousedů (0 = nic). Výchozí
    #: hodnota odpovídá venkovské skupině s převážně místními vazbami.
    openness: float = 0.1
    literacy: float = 0.0
    schooling: float = 0.0
    #: Souhrnná skupina zastupuje celé nerozepsané území.
    aggregate: bool = False
    internal_diversity: float = 0.0

    def __post_init__(self) -> None:
        if self.population <= 0:
            raise ValueError(f"Skupina '{self.id}' musí mít kladnou populaci.")
        if self.generation_years <= 0:
            raise ValueError(f"Skupina '{self.id}' musí mít kladnou délku generace.")
        if not 0.0 <= self.openness <= 1.0:
            raise ValueError(f"Otevřenost skupiny '{self.id}' musí ležet v intervalu 0 až 1.")
        if self.prestige < 0:
            raise ValueError(f"Prestiž skupiny '{self.id}' nesmí být záporná.")
        if not self.codes:
            raise ValueError(f"Skupina '{self.id}' musí mít alespoň jeden kód.")

    @property
    def main_code(self) -> Code:
        return self.codes[0]


@dataclass(frozen=True, slots=True)
class Link:
    """Směrovaná vazba: ``source`` se učí od ``target`` se sílou ``strength``."""

    source: str
    target: str
    strength: float
    kind: LinkKind = "weak"


@dataclass(slots=True)
class World:
    seed: int
    start_year: float = 0.0
    territories: dict[str, Territory] = field(default_factory=dict)
    groups: dict[str, SpeechGroup] = field(default_factory=dict)
    links: dict[tuple[str, str], Link] = field(default_factory=dict)
    variables: dict[str, Variable] = field(default_factory=dict)
    variants: dict[str, Variant] = field(default_factory=dict)
    #: Proměnné, ve kterých se skupiny liší; viz :mod:`cee.v2.pools`.
    live: LivePools = field(default_factory=LivePools)
    morphemes: dict[str, Morpheme] = field(default_factory=dict)
    #: ID procesní proměnné → proces. Chronologii změn drží každý kód sám.
    processes: dict[str, Process] = field(default_factory=dict)
    #: Tabulka hlásek; svět bez hláskových tvarů (M1) ji nepotřebuje.
    table: SegmentTable | None = None

    def distribution(self, group_id: str, variable_id: str) -> Distribution | None:
        """Jediné správné čtení stavu: živá proměnná má přednost před repertoárem."""
        if variable_id in self.live and group_id in self.live.group_index:
            return self.live.get(group_id, variable_id)
        return self.stored(group_id, variable_id)

    def stored(self, group_id: str, variable_id: str) -> Distribution | None:
        """Stav z repertoáru (bez živého skladu), včetně výchozí varianty."""
        found = self.groups[group_id].main_code.repertoire.get(variable_id)
        if found is None:
            variable = self.variables.get(variable_id)
            if variable is not None and variable.default is not None:
                return Distribution.fixed(variable.default)
        return found

    def form_of(self, code: Code, morpheme_id: str) -> tuple[int, ...]:
        """Aktuální podkladový tvar morfému v daném kódu."""
        return code.forms.get(morpheme_id) or self.morphemes[morpheme_id].form

    def materialize(self, group_id: str) -> None:
        """Zapíše živé proměnné skupiny do jejího repertoáru (před odebráním či kopií)."""
        if group_id not in self.live.group_index:
            return
        repertoire = self.groups[group_id].main_code.repertoire
        for variable_id in self.live.variable_ids:
            item = self.live.get(group_id, variable_id)
            if item is not None:
                repertoire.set(variable_id, item)

    def add_territory(self, territory: Territory) -> Territory:
        if territory.id in self.territories:
            raise ValueError(f"Území '{territory.id}' už existuje.")
        if territory.parent is not None:
            parent = self.territories.get(territory.parent)
            if parent is None:
                raise ValueError(f"Nadřazené území '{territory.parent}' neexistuje.")
            if TERRITORY_LEVELS.index(territory.level) <= TERRITORY_LEVELS.index(parent.level):
                raise ValueError(
                    f"Území '{territory.id}' musí ležet níž než '{parent.id}' ({parent.level})."
                )
            parent.children.append(territory.id)
        self.territories[territory.id] = territory
        return territory

    def add_group(self, group: SpeechGroup) -> SpeechGroup:
        if group.id in self.groups:
            raise ValueError(f"Skupina '{group.id}' už existuje.")
        if group.territory not in self.territories:
            raise ValueError(f"Území '{group.territory}' skupiny '{group.id}' neexistuje.")
        self.groups[group.id] = group
        return group

    def remove_group(self, group_id: str) -> SpeechGroup:
        group = self.groups.pop(group_id)
        for key in [key for key in self.links if group_id in key]:
            del self.links[key]
        return group

    def connect(self, first: str, second: str, strength: float, kind: LinkKind = "weak") -> None:
        """Oboustranná vazba. Sousedé se učí jeden od druhého stejně často."""
        for group_id in (first, second):
            if group_id not in self.groups:
                raise ValueError(f"Skupina '{group_id}' neexistuje.")
        if first == second:
            raise ValueError("Skupina nemůže mít vazbu sama na sebe.")
        value = max(0.0, min(1.0, float(strength)))
        self.links[(first, second)] = Link(first, second, value, kind)
        self.links[(second, first)] = Link(second, first, value, kind)

    def neighbors(self, group_id: str) -> list[Link]:
        return sorted(
            (link for (source, _), link in self.links.items() if source == group_id),
            key=lambda link: link.target,
        )

    def group_ids(self) -> list[str]:
        return sorted(self.groups)

    def position_of(self, group_id: str) -> tuple[float, float] | None:
        return self.territories[self.groups[group_id].territory].position

    def generation_ceiling(self) -> float:
        """Nejkratší délka generace; krok simulace nesmí být delší."""
        return min(group.generation_years for group in self.groups.values())

    def seed_lexicon(
        self,
        concepts: Sequence[str],
        forms: Mapping[str, str] | None = None,
        frequencies: Mapping[str, float] | None = None,
    ) -> Repertoire:
        """Zmrazený protojazyk: každý pojem má jedno zděděné slovo.

        Bez ``forms`` je slovo jen identifikátor lexému (svět M1). S nimi
        dostane každý pojem morfém s hláskovou podobou a svět tabulku hlásek.
        """
        repertoire = Repertoire()
        if forms is not None and self.table is None:
            self.table = default_table()
        for concept in dict.fromkeys(concepts):
            variable = Variable("lexical", concept)
            payload: dict[str, object] = {"lexeme": stable_id("lexeme", "proto", concept)}
            if forms is not None:
                assert self.table is not None
                morpheme = Morpheme(
                    id=stable_id("morpheme", "proto", concept),
                    meaning=concept,
                    form=self.table.parse(forms[concept]),
                    frequency=float((frequencies or {}).get(concept, 0.5)),
                )
                self.morphemes[morpheme.id] = morpheme
                payload["morpheme"] = morpheme.id
            variant = Variant(
                id=stable_id("variant", "proto", variable.id),
                variable=variable.id,
                payload=payload,
                origin=Origin(change=None, tick=0, year=self.start_year, group=None),
            )
            self.variables[variable.id] = variable
            self.variants[variant.id] = variant
            repertoire.set(variable.id, Distribution.fixed(variant.id))
        return repertoire.freeze()


def gravity_links(
    world: World,
    *,
    scale: float = 1.0,
    reference_population: float = 1_000.0,
    reference_distance: float = 10.0,
    max_distance: float | None = None,
) -> int:
    """Doplní vazby podle gravitačního modelu (Trudgill 1974).

    Síla roste s geometrickým průměrem populací a klesá se čtvercem
    vzdálenosti; saturace ``x / (1 + x)`` ji drží v intervalu 0 až 1.
    Referenční populace a vzdálenost jsou výchozí odhad, ne kalibrace.
    Vrací počet vytvořených oboustranných vazeb.
    """
    placed = [
        (group_id, world.position_of(group_id))
        for group_id in world.group_ids()
        if world.position_of(group_id) is not None
    ]
    created = 0
    for index, (first, first_position) in enumerate(placed):
        for second, second_position in placed[index + 1 :]:
            assert first_position is not None and second_position is not None
            distance = math.dist(first_position, second_position)
            if distance == 0 or (max_distance is not None and distance > max_distance):
                continue
            mass = math.sqrt(world.groups[first].population * world.groups[second].population)
            pull = scale * (mass / reference_population) / (distance / reference_distance) ** 2
            world.connect(first, second, pull / (1.0 + pull))
            created += 1
    return created
