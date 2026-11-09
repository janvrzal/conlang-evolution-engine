"""Popis světa pro UI: schéma JSON, ze kterého engine v Rustu staví svět a události.

Autor světa (a UI za něj) popisuje jen to, co zná: protojazyky, regiony
(poloha, relativní hustota, sousedé, terén, identita, jazyk) a časovou osu
událostí po regionech a státech se slovními úrovněmi. Čísla dynamiky jsou
metaparametry (``v2_parameters.json``) a autor je smí přepsat v ``parameters``.

Python tu drží jen **schéma a validaci polí**:

- :class:`WorldSpec` je pydantic model; ``WorldSpec.model_json_schema()`` dá UI schéma
  formuláře a :func:`levels` možnosti slovních úrovní.
- :func:`parse` ověří pole podle schématu (české zprávy s cestou k poli),
  :func:`check_parameters` přepisy metaparametrů podle ``v2_parameters.json``.
- Sémantickou kontrolu (neznámé regiony, státy, slova, zkušební provedení událostí)
  dělá Rust (``cee_engine::spec::check``); :func:`cee.v2.runner.check` spojí obojí.
- Slovník: ``vocabulary`` (kolik pojmů) a ``concepts`` (vlastní pojmy).

Formát má verzi ``FORMAT``; mění se jen přidáváním polí.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from cee.v2.parameters import check_override, default_levels

FORMAT = "cee-v2-world/1"

#: Velikost výchozího slovníku (149 pojmů).
DEFAULT_VOCABULARY = 149
#: Velikosti slovníku, které UI nabízí jako předvolby (jiné čtení je povolené).
PRESET_SIZES = (149, 200, 500, 1000)
#: Domény pojmů a rozsah frekvence na stupnici enginu (shodně s ``rust/cee_engine/src/concepts.rs``).
DOMAINS = ("core", "learned", "culture", "religion", "power")
FREQUENCY_RANGE = (0.05, 0.9)
WORD_CLASSES = ("noun", "verb", "uninflected")
RELATION_KINDS = ("polysemy", "derivation", "colexification")
RELATION_DIRECTIONS = ("to", "from", "both")
#: Váha vztahu bez zadání ve stejných jednotkách jako data (počet rodin, resp. jazyků).
DEFAULT_WEIGHT = {"polysemy": 2, "derivation": 2, "colexification": 9}
#: ID vlastního pojmu: písmena, číslice, ``_``, ``.`` a ``-``; začíná písmenem nebo číslicí.
ID_PATTERN = re.compile(r"^\w[\w.-]*$")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConstructionSpec(_Model):
    """Konstrukce gramatické funkce (druh, zdrojové slovo, stadium, pořadí, posila)."""

    kind: str = Field(min_length=1)
    source: str | None = None
    stage: str | None = None
    order: str | None = None
    reinforcer: str | None = None


class InitialProcessSpec(_Model):
    """Zvuková změna rozběhnutá na startu (rodina, popis kandidáta, podíl mluvčích)."""

    family: str = Field(min_length=1)
    label: str = Field(min_length=1)
    share: float = Field(gt=0.0, lt=1.0)


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
    stress: Literal["initial", "second", "antepenult", "penult", "final", "weight"] = "penult"
    stress_strength: Literal["weak", "strong"] = "weak"
    #: Slova, která zadal autor: pojem → tvar v IPA. Ostatní složí generátor.
    words: dict[str, str] = Field(default_factory=dict)
    #: Pojmy, ze kterých se skládá vlastní jméno jazyka (např. ``["person", "language"]``).
    endonym: list[str] = Field(default_factory=list)
    #: Tóny tónového jazyka jako tónové značky (``["˥", "˧", "˩"]``); prázdné = bez tónů.
    tones: list[str] = Field(default_factory=list)
    #: Přepisy konstrukcí profilu podle funkce: ``{"FUTURE": {"kind": "synthetic"}}``.
    constructions: dict[str, ConstructionSpec] = Field(default_factory=dict)
    #: Vlastní koncovky podle ``třída:buňka``: ``{"noun:OBJ": [["m", 1.0]]}``.
    endings: dict[str, list[tuple[str, float]]] = Field(default_factory=dict)
    #: Zvukové změny rozběhnuté na startu: ``[{"family": "coda_loss", "label": "m → ∅ /V_#",
    #: "share": 0.3}]``.
    processes: list[InitialProcessSpec] = Field(default_factory=list)
    #: Odvozovací přípony (IPA); prázdné = engine je vylosuje z inventáře hlásek jazyka.
    suffixes: list[str] = Field(default_factory=list)
    #: Slabičná stavba generovaných slov (WALS 12A); ``None`` = engine ji vylosuje podle
    #: podílů typů ve WALS (dok. 25).
    syllables: Literal["simple", "moderate", "complex"] | None = None


#: Počet vesnic regionu (1–12).
VillageCount = Annotated[int, Field(ge=1, le=12)]


class RegionSpec(_Model):
    """Region jako síť vesnic (``scenarios.Region``)."""

    id: str = Field(min_length=1)
    name: str | None = None
    #: Poloha těžiště v km.
    position: tuple[float, float]
    #: Relativní hustota osídlení (1 = běžná krajina).
    density: float = Field(default=1.0, gt=0.0, le=100.0)
    neighbours: list[str] = Field(default_factory=list)
    #: Počet vesnic: číslo, nebo rozsah ``[min, max]`` vylosovaný podle semínka světa.
    villages: VillageCount | tuple[VillageCount, VillageCount] = 4

    @model_validator(mode="after")
    def _villages_in_range(self) -> "RegionSpec":
        low, high = (self.villages, self.villages) if isinstance(self.villages, int) else self.villages
        if not (1 <= low <= high <= 12):
            raise ValueError("villages: počet 1–12, rozsah [min, max] s min ≤ max")
        return self
    prestige: float = Field(default=0.5, ge=0.0)
    #: ID protojazyka; ``None`` = první z ``languages``.
    language: str | None = None
    terrain: str = "plain"
    #: Prostupnost 0–1 (1 = snadno prostupná krajina, 0 = izolace); chybí = podle terénu.
    permeability: float | None = Field(default=None, ge=0.0, le=1.0)
    identity: str = "shared"
    preserve: bool = False
    #: Podíl přistěhovalců za generaci (obchodní město).
    immigration: float = Field(default=0.0, ge=0.0, le=1.0)
    #: Velikost města regionu (násobek vesnice); ``None`` = parametr ``city_size``, 0 = bez města.
    city: float | None = Field(default=None, ge=0.0)


class RelatedSpec(_Model):
    """Příbuzný pojem vlastního pojmu pro posuny významu (``vocabulary.Related``)."""

    #: ID pojmu světa (výchozího, z katalogu nebo jiného vlastního).
    concept: str = Field(min_length=1)
    #: ``polysemy`` (posun významu), ``derivation`` (odvození), ``colexification`` (kolexifikace).
    kind: Literal["polysemy", "derivation", "colexification"] = "polysemy"
    #: ``to``: slovo vlastního pojmu se posune k druhému pojmu (resp. druhý se z něj odvodí);
    #: ``from``: opačně; ``both``: oběma směry. Bez zadání ``both`` u posunu významu a ``from``
    #: u odvození (druhý pojem je základ vlastního). Kolexifikace je vždy oboustranná.
    direction: Literal["to", "from", "both"] | None = None
    #: Síla dokladu v jednotkách dat (počet rodin, resp. jazyků); ``None`` = typická hodnota dat
    #: (``vocabulary.DEFAULT_WEIGHT``).
    weight: int | None = Field(default=None, ge=1, le=100000)


class ConceptSpec(_Model):
    """Vlastní pojem autora světa, vymyšlený nebo reálný (``vocabulary.CustomConcept``)."""

    id: str = Field(min_length=1, pattern=ID_PATTERN.pattern)
    #: Anglický glos. Shoduje-li se s glosem Concepticonu či názvem významu WOLD,
    #: převezmou se data jako při vazbě; jinak je to jen popisek.
    gloss: str | None = None
    #: Vazba na význam WOLD (např. ``"6-1"``) nebo Concepticon (ID); jen jedna.
    #: S vazbou se doména, půjčitelnost, frekvence a slovní druh převezmou z dat.
    wold: str | None = None
    concepticon: int | None = Field(default=None, ge=1)
    #: Doména (``DOMAINS``); bez ní z vazby, jinak ``core``.
    domain: Literal["core", "learned", "culture", "religion", "power"] | None = None
    #: Frekvence na stupnici enginu (``FREQUENCY_RANGE``); bez ní z vazby,
    #: jinak průměr katalogu (domény pojmu, je-li zadaná).
    frequency: float | None = Field(default=None, ge=FREQUENCY_RANGE[0],
                                    le=FREQUENCY_RANGE[1])
    #: Slovní druh; bez něj z vazby (kategorie WOLD), jinak podstatné jméno.
    word_class: Literal["noun", "verb", "uninflected"] | None = None
    #: Půjčitelnost 0 až 1; bez ní z vazby, jinak průměr katalogu (domény pojmu).
    borrowed: float | None = Field(default=None, ge=0.0, le=1.0)
    related: list[RelatedSpec] = Field(default_factory=list)



class _Event(_Model):
    year: float
    # Studijní případ: krátký štítek; běh zapíše záznam `study_case` (dok. 36).
    study_case: str | None = None


class StateSpec(_Event):
    kind: Literal["state"]
    id: str = Field(min_length=1)
    #: Jméno státu (jen popis; engine ho nese do exportu).
    name: str | None = None
    regions: list[str] = Field(min_length=1)
    capital: str
    centralization: str = "moderate"
    policy: str = "tolerant"
    border: str = "normal"
    #: Úřední jazyk (jméno linie); ``None`` = jazyk největší vesnice hlavního regionu.
    language: str | None = None



class LanguagePolicySpec(_Event):
    kind: Literal["language_policy"]
    state: str
    policy: str



class AnnexationSpec(_Event):
    kind: Literal["annexation"]
    state: str
    regions: list[str] = Field(min_length=1)



class SecessionSpec(_Event):
    kind: Literal["secession"]
    id: str = Field(min_length=1)
    name: str | None = None
    regions: list[str] = Field(min_length=1)
    capital: str
    centralization: str = "moderate"
    policy: str = "tolerant"
    border: str = "normal"
    #: Úřední jazyk (jméno linie); ``None`` = jazyk největší vesnice hlavního regionu.
    language: str | None = None



class CollapseSpec(_Event):
    kind: Literal["collapse"]
    state: str



class BorderPolicySpec(_Event):
    kind: Literal["border_policy"]
    state: str
    border: str



class LinguaFrancaSpec(_Event):
    kind: Literal["lingua_franca"]
    #: Region (jeho největší vesnice), odkud lingua franca pochází.
    source: str
    regions: list[str] = Field(min_length=1)
    spread: str = "common"
    nativize: bool = False



class StandardSpec(_Event):
    kind: Literal["standard"]
    #: ID státu nebo regionu.
    of: str
    literacy: str = "elite"



class SchoolsSpec(_Event):
    kind: Literal["schools"]
    of: str
    coverage: str = "mass"
    printing: bool = True
    diglossic: bool = False



class RevivalSpec(_Event):
    kind: Literal["revival"]
    regions: list[str] = Field(min_length=1)
    language: str | None = None
    strength: str = "movement"



class PreserveSpec(_Event):
    kind: Literal["preserve"]
    regions: list[str] = Field(min_length=1)
    language: str | None = None
    preserved: bool = True



class IdentitySpec(_Event):
    kind: Literal["identity"]
    regions: list[str] = Field(min_length=1)
    #: ``shared``, ``distinct``, ``strong`` (tabulka ``identity_loyalty``).
    identity: str



class ImmigrationSpec(_Event):
    kind: Literal["immigration"]
    regions: list[str] = Field(min_length=1)
    #: Podíl přistěhovalců za generaci; 0 příchod zastaví.
    immigration: float = Field(ge=0.0, le=1.0)



class SettlementSpec(_Event):
    """Lidé z regionu ``from`` se usadí v regionu ``to`` (migrace, nové osady)."""

    kind: Literal["settlement"]
    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    share: float = Field(default=0.2, gt=0.0, lt=1.0)
    settlements: int = Field(default=1, ge=1)
    prestige: float | None = None



class EliteSpec(_Event):
    """Elita z regionu ``from`` ovládne region ``seat`` (dobytí, superstrát)."""

    kind: Literal["elite"]
    from_: str = Field(alias="from", min_length=1)
    seat: str = Field(min_length=1)
    #: Jazyk elity (linie); elitou je největší skupina toho jazyka v regionu ``from`` v roce události.
    language: str | None = None
    subjects: list[str] | None = None
    population: float = Field(default=100.0, gt=0.0)
    prestige: float = 2.0
    strength: float = Field(default=0.5, gt=0.0)
    #: Síla vazby elity k domovině; ``None`` = polovina ``strength``, 0 = elita se od domova odtrhne.
    homeland: float | None = Field(default=None, ge=0.0)



class SoundShiftSpec(_Event):
    """Zadaná hlásková změna se rozběhne u jazyka ``language`` (dok. 26): rodina a popis
    kandidáta jako v ``LanguageSpec.processes`` (např. ``spirantization``,
    ``"řada neznělých okluziv → frikativy"``). Engine ji jen nastartuje."""

    kind: Literal["sound_shift"]
    language: str = Field(min_length=1)
    #: Jen v těchto regionech; prázdné = všude, kde jazykem mluví.
    regions: list[str] = Field(default_factory=list)
    family: str = Field(min_length=1)
    label: str = Field(min_length=1)
    share: float = Field(default=0.2, gt=0.0, lt=1.0)
    #: Výhoda změny ve skupinách jazyka, dokud v nich nemá většinu mluvčích; 0 = jen start.
    pull: float = Field(default=1.0, ge=0.0)


EventSpec = Annotated[
    Union[
        StateSpec, LanguagePolicySpec, AnnexationSpec, SecessionSpec, CollapseSpec, BorderPolicySpec,
        LinguaFrancaSpec, StandardSpec, SchoolsSpec, RevivalSpec, PreserveSpec, IdentitySpec, ImmigrationSpec,
        SettlementSpec, EliteSpec, SoundShiftSpec,
    ],
    Field(discriminator="kind"),
]
EVENT_KINDS = (
    "state", "language_policy", "annexation", "secession", "collapse", "border_policy",
    "lingua_franca", "standard", "schools", "revival", "preserve", "identity", "immigration",
    "settlement", "elite", "sound_shift",
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
    #: Kolik pojmů se simuluje: 149 výchozích (beze změny výsledků) až celý katalog WOLD
    #: (``vocabulary.max_size()``); větší slovník = výchozí pojmy + další z katalogu v pořadí
    #: pořadí katalogu WOLD. Jiný slovník dá jiné výsledky (varování v ``runner.check``).
    vocabulary: int = Field(default=DEFAULT_VOCABULARY, ge=DEFAULT_VOCABULARY)
    #: Vlastní pojmy autora (vymyšlené i reálné), navíc ke slovníku.
    concepts: list[ConceptSpec] = Field(default_factory=list)
    #: Posun významu slov (sémantický graf); vypnutí běh zrychlí.
    semantics: bool = True
    #: Vzdálenost vesnic v regionu (km) a délka generace (roky).
    village_spacing: float = Field(default=10.0, gt=0.0)
    generation_years: float = Field(default=25.0, ge=25.0, le=1000.0)
    #: Přepisy metaparametrů (kalibrační konstanty, tabulky úrovní).
    parameters: dict[str, Any] = Field(default_factory=dict)
    #: Míra pozadí dějin (tabulka ``background_levels``): drobné události,
    #: které svět generuje sám (mor, přesídlení, obchod, prestiž, cizí elita).
    background: str = "none"

    @model_validator(mode="after")
    def _ordered_years(self) -> WorldSpec:
        if self.end_year <= self.start_year:
            raise ValueError("end_year musí být později než start_year")
        return self


@dataclass(frozen=True)
class Issue:
    """Chyba nebo varování popisu světa: cesta k poli (``events.2.capital``) a zpráva.

    ``severity``: ``error`` svět nepustí, ``warning`` jen upozorní (svět jde postavit).
    """

    path: str
    message: str
    severity: Literal["error", "warning"] = "error"


def errors(issues: list[Issue]) -> list[Issue]:
    """Jen chyby ze seznamu :func:`check`."""
    return [issue for issue in issues if issue.severity == "error"]


def warnings(issues: list[Issue]) -> list[Issue]:
    """Jen varování ze seznamu :func:`check`."""
    return [issue for issue in issues if issue.severity == "warning"]


class SpecError(ValueError):
    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{issue.path}: {issue.message}" for issue in issues))


def levels() -> dict[str, list[str]]:
    """Možnosti slovních úrovní (pro výběr v UI) podle výchozích tabulek metaparametrů."""
    return default_levels()


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
    "string_pattern_mismatch": "smí obsahovat jen písmena, číslice, _ . - a začít písmenem nebo číslicí",
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


def check_parameters(spec: WorldSpec) -> list[Issue]:
    """Přepisy parametrů ověřené podle ``v2_parameters.json`` (jméno, druh, meze)."""
    return [
        Issue(path, message)
        for name, value in spec.parameters.items()
        for path, message in check_override(name, value)
    ]


def vocabulary_options(max_size: int) -> dict[str, Any]:
    """Možnosti slovníku pro UI: výchozí a největší velikost, předvolby, domény, druhy vztahů.

    ``max_size`` (výchozí pojmy a celý katalog WOLD) zná Rust: ``cee_engine_py.vocabulary_max_size()``.
    """
    return {
        "default": DEFAULT_VOCABULARY, "max": max_size, "presets": list(PRESET_SIZES),
        "domains": list(DOMAINS), "word_classes": list(WORD_CLASSES),
        "relation_kinds": list(RELATION_KINDS), "relation_directions": list(RELATION_DIRECTIONS),
        "default_weight": dict(DEFAULT_WEIGHT), "frequency_range": list(FREQUENCY_RANGE),
    }
