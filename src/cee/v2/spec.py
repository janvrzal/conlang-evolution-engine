"""Popis světa pro UI: JSON, ze kterého engine postaví svět a události.

Autor světa (a UI za něj) popisuje jen to, co zná: protojazyky, regiony
(poloha, relativní hustota, sousedé, terén, identita, jazyk) a časovou osu
událostí po regionech a státech se slovními úrovněmi. Čísla dynamiky jsou
v ``Parameters`` a autor je smí přepsat v ``parameters``.

- :class:`WorldSpec` je pydantic model; ``WorldSpec.model_json_schema()``
  dá UI schéma formuláře a :func:`levels` možnosti slovních úrovní.
- :func:`check` vrátí seznam chyb s cestou k poli (prázdný = v pořádku);
  události ověří zkušebním provedením na kopii světa v pořadí roků.
- :func:`build` postaví svět a události, nebo vyhodí :class:`SpecError`.

Formát má verzi ``FORMAT``; mění se jen přidáváním polí.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, fields
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from cee.v2.events import WorldEvent
from cee.v2.history import History
from cee.v2.parameters import LEVEL_TABLES, Parameters
from cee.v2.polity import (
    Annexation,
    BorderPolicy,
    Collapse,
    LanguagePolicy,
    LinguaFranca,
    Preserve,
    Revival,
    Schools,
    Secession,
    Standard,
    State,
)
from cee.v2.scenarios import (
    FULL_GRAMMAR,
    SUBSTRATE_GRAMMAR,
    SYNTAX_GRAMMAR,
    ProtoLanguage,
    Region,
    region_world,
)
from cee.v2.world import World

FORMAT = "cee-v2-world/1"

#: Profily gramatiky protojazyka, které autor vybírá jménem.
GRAMMARS = {"default": SYNTAX_GRAMMAR, "substrate": SUBSTRATE_GRAMMAR, "full": FULL_GRAMMAR}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LanguageSpec(_Model):
    """Protojazyk jedné linie."""

    id: str = Field(min_length=1)
    name: str | None = None
    #: Inventář souhlásek a samohlásek (IPA); ``None`` = výchozí inventář.
    consonants: list[str] | None = Field(default=None, min_length=1)
    vowels: list[str] | None = Field(default=None, min_length=1)
    #: ``default`` (pády, minulý čas, plurál), ``substrate`` (zápor za slovesem,
    #: pevné SOV), ``full`` (i funkce, které jazyk může vyvinout: člen, budoucí čas, vid).
    grammar: Literal["default", "substrate", "full"] = "default"
    stress: Literal["initial", "second", "antepenult", "penult", "final"] = "penult"
    stress_strength: Literal["weak", "strong"] = "weak"


class RegionSpec(_Model):
    """Region jako síť vesnic (``scenarios.Region``)."""

    id: str = Field(min_length=1)
    name: str | None = None
    #: Poloha těžiště v km.
    position: tuple[float, float]
    #: Relativní hustota osídlení (1 = běžná krajina).
    density: float = Field(default=1.0, gt=0.0, le=100.0)
    neighbours: list[str] = Field(default_factory=list)
    villages: int = Field(default=4, ge=1, le=12)
    prestige: float = Field(default=0.5, ge=0.0)
    #: ID protojazyka; ``None`` = první z ``languages``.
    language: str | None = None
    terrain: str = "plain"
    identity: str = "shared"
    preserve: bool = False
    #: Podíl přistěhovalců za generaci (obchodní město).
    immigration: float = Field(default=0.0, ge=0.0, le=1.0)


class _Event(_Model):
    year: float


class StateSpec(_Event):
    kind: Literal["state"]
    id: str = Field(min_length=1)
    regions: list[str] = Field(min_length=1)
    capital: str
    centralization: str = "moderate"
    policy: str = "tolerant"
    border: str = "normal"

    def event(self) -> WorldEvent:
        return State(self.year, self.id, tuple(self.regions), self.capital, self.centralization, self.policy,
                     self.border)


class LanguagePolicySpec(_Event):
    kind: Literal["language_policy"]
    state: str
    policy: str

    def event(self) -> WorldEvent:
        return LanguagePolicy(self.year, self.state, self.policy)


class AnnexationSpec(_Event):
    kind: Literal["annexation"]
    state: str
    regions: list[str] = Field(min_length=1)

    def event(self) -> WorldEvent:
        return Annexation(self.year, self.state, tuple(self.regions))


class SecessionSpec(_Event):
    kind: Literal["secession"]
    id: str = Field(min_length=1)
    regions: list[str] = Field(min_length=1)
    capital: str
    centralization: str = "moderate"
    policy: str = "tolerant"
    border: str = "normal"

    def event(self) -> WorldEvent:
        return Secession(self.year, self.id, tuple(self.regions), self.capital, self.centralization,
                         self.policy, self.border)


class CollapseSpec(_Event):
    kind: Literal["collapse"]
    state: str

    def event(self) -> WorldEvent:
        return Collapse(self.year, self.state)


class BorderPolicySpec(_Event):
    kind: Literal["border_policy"]
    state: str
    border: str

    def event(self) -> WorldEvent:
        return BorderPolicy(self.year, self.state, self.border)


class LinguaFrancaSpec(_Event):
    kind: Literal["lingua_franca"]
    #: Region (jeho největší vesnice), odkud lingua franca pochází.
    source: str
    regions: list[str] = Field(min_length=1)
    spread: str = "common"
    nativize: bool = False

    def event(self) -> WorldEvent:
        return LinguaFranca(self.year, self.source, tuple(self.regions), self.spread, self.nativize)


class StandardSpec(_Event):
    kind: Literal["standard"]
    #: ID státu nebo regionu.
    of: str
    literacy: str = "elite"

    def event(self) -> WorldEvent:
        return Standard(self.year, self.of, self.literacy)


class SchoolsSpec(_Event):
    kind: Literal["schools"]
    of: str
    coverage: str = "mass"
    printing: bool = True
    diglossic: bool = False

    def event(self) -> WorldEvent:
        return Schools(self.year, self.of, self.coverage, self.printing, self.diglossic)


class RevivalSpec(_Event):
    kind: Literal["revival"]
    regions: list[str] = Field(min_length=1)
    language: str | None = None
    strength: str = "movement"

    def event(self) -> WorldEvent:
        return Revival(self.year, tuple(self.regions), self.language, self.strength)


class PreserveSpec(_Event):
    kind: Literal["preserve"]
    regions: list[str] = Field(min_length=1)
    language: str | None = None
    preserved: bool = True

    def event(self) -> WorldEvent:
        return Preserve(self.year, tuple(self.regions), self.language, self.preserved)


EventSpec = Annotated[
    Union[
        StateSpec, LanguagePolicySpec, AnnexationSpec, SecessionSpec, CollapseSpec, BorderPolicySpec,
        LinguaFrancaSpec, StandardSpec, SchoolsSpec, RevivalSpec, PreserveSpec,
    ],
    Field(discriminator="kind"),
]
EVENT_KINDS = (
    "state", "language_policy", "annexation", "secession", "collapse", "border_policy",
    "lingua_franca", "standard", "schools", "revival", "preserve",
)


class WorldSpec(_Model):
    """Celý svět: protojazyky, regiony, časová osa a přepisy parametrů."""

    format: Literal["cee-v2-world/1"] = FORMAT
    name: str | None = None
    seed: int = 1
    start_year: float = 0.0
    end_year: float
    languages: list[LanguageSpec] = Field(min_length=1)
    regions: list[RegionSpec] = Field(min_length=1)
    events: list[EventSpec] = Field(default_factory=list)
    #: Posun významu slov (sémantický graf); vypnutí běh zrychlí.
    semantics: bool = True
    #: Vzdálenost vesnic v regionu (km) a délka generace (roky).
    village_spacing: float = Field(default=10.0, gt=0.0)
    generation_years: float = Field(default=25.0, ge=25.0, le=1000.0)
    #: Přepisy polí ``Parameters`` (kalibrační konstanty, tabulky úrovní).
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ordered_years(self) -> WorldSpec:
        if self.end_year <= self.start_year:
            raise ValueError("end_year musí být později než start_year")
        return self


@dataclass(frozen=True)
class Issue:
    """Chyba popisu světa: cesta k poli (``events.2.capital``) a zpráva."""

    path: str
    message: str


class SpecError(ValueError):
    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{issue.path}: {issue.message}" for issue in issues))


def levels(params: Parameters | None = None) -> dict[str, list[str]]:
    """Možnosti slovních úrovní (pro výběr v UI) podle tabulek ``Parameters``."""
    params = params or Parameters()
    return {name: sorted(getattr(params, name)) for name in LEVEL_TABLES}


def parse(data: dict[str, Any] | WorldSpec) -> tuple[WorldSpec | None, list[Issue]]:
    if isinstance(data, WorldSpec):
        return data, []
    try:
        return WorldSpec.model_validate(data), []
    except ValidationError as error:
        return None, [
            Issue(".".join(str(part) for part in item["loc"]) or "(svět)", _czech(item))
            for item in error.errors()
        ]


#: Zprávy pydanticu česky podle typu chyby (``ctx`` doplní meze).
MESSAGES = {
    "missing": "chybí povinné pole",
    "extra_forbidden": "neznámé pole",
    "too_short": "počet položek musí být aspoň {min_length}",
    "string_too_short": "nesmí být prázdné",
    "greater_than": "musí být větší než {gt}",
    "greater_than_equal": "musí být aspoň {ge}",
    "less_than_equal": "smí být nejvýš {le}",
    "literal_error": "musí být jedna z možností: {expected}",
    "union_tag_invalid": "neznámý druh události '{tag}'; možnosti: {expected_tags}",
    "union_tag_not_found": "chybí druh události (kind)",
    "int_parsing": "musí být celé číslo",
    "float_parsing": "musí být číslo",
    "bool_parsing": "musí být true nebo false",
    "string_type": "musí být text",
    "list_type": "musí být seznam",
    "tuple_type": "musí být dvojice čísel",
}


def _czech(item: Any) -> str:
    kind = item["type"]
    if kind == "value_error":
        return str(item["ctx"]["error"])
    template = MESSAGES.get(kind)
    if template is None:
        return item["msg"]
    try:
        return template.format(**item.get("ctx", {}))
    except KeyError:
        return item["msg"]


def _parameters(spec: WorldSpec) -> tuple[Parameters | None, list[Issue]]:
    known = {item.name for item in fields(Parameters)}
    unknown = sorted(set(spec.parameters) - known)
    if unknown:
        return None, [Issue(f"parameters.{name}", "neznámý parametr") for name in unknown]
    try:
        return Parameters(**spec.parameters), []
    except (TypeError, ValueError) as error:
        return None, [Issue("parameters", str(error))]


def _world(spec: WorldSpec, params: Parameters) -> World:
    languages = tuple(
        ProtoLanguage(
            language.id, grammar=dict(GRAMMARS[language.grammar]),
            **({"consonants": tuple(language.consonants)} if language.consonants else {}),
            **({"vowels": tuple(language.vowels)} if language.vowels else {}),
            stress_rule=language.stress, stress_strength=language.stress_strength,
        )
        for language in spec.languages
    )
    regions = tuple(
        Region(
            region.id, tuple(region.position), density=region.density, neighbours=tuple(region.neighbours),
            villages=region.villages, prestige=region.prestige, immigration=region.immigration,
            language=region.language, terrain=region.terrain, identity=region.identity, preserve=region.preserve,
        )
        for region in spec.regions
    )
    world = region_world(
        regions, seed=spec.seed, semantics=spec.semantics, village_spacing=spec.village_spacing,
        generation_years=spec.generation_years, params=params, languages=languages,
    )
    world.start_year = spec.start_year
    return world


def _ordered(spec: WorldSpec) -> list[tuple[int, Any]]:
    return sorted(enumerate(spec.events), key=lambda item: (item[1].year, item[0]))


def check(data: dict[str, Any] | WorldSpec) -> list[Issue]:
    """Chyby popisu světa (prázdný seznam = svět jde postavit a spustit)."""
    spec, issues = parse(data)
    if spec is None:
        return issues
    params, issues = _parameters(spec)
    if params is None:
        return issues
    try:
        world = _world(spec, params)
    except ValueError as error:
        return [Issue("regions", str(error))]
    for index, item in enumerate(spec.events):
        if not spec.start_year <= item.year <= spec.end_year:
            issues.append(Issue(f"events.{index}.year", "událost leží mimo start_year až end_year"))
    # Zkušební provedení událostí na kopii světa odhalí odkazy na neexistující
    # státy a regiony, neznámé úrovně i pořadí (Collapse před State).
    trial, history = copy.deepcopy(world), History()
    for index, item in _ordered(spec):
        try:
            item.event().apply(trial, history, 0)
        except KeyError as error:
            issues.append(Issue(f"events.{index}", f"neznámé ID {error.args[0]!r}"))
        except ValueError as error:
            issues.append(Issue(f"events.{index}", str(error)))
    return issues


def build(data: dict[str, Any] | WorldSpec) -> tuple[World, list[WorldEvent], WorldSpec]:
    """Svět, události a ověřený popis; při chybě :class:`SpecError` se všemi chybami."""
    issues = check(data)
    if issues:
        raise SpecError(issues)
    spec, _ = parse(data)
    assert spec is not None
    params, _ = _parameters(spec)
    assert params is not None
    return _world(spec, params), [item.event() for _, item in _ordered(spec)], spec
