"""Slovník světa: kolik a které pojmy se simulují (nástroje pro autora světa).

Engine dosud simuloval pevných 149 pojmů ``scenarios.DEFAULT_CONCEPTS`` (a šest
zdrojů gramatikalizace). Autor světa teď dostane dva nástroje:

1. **Velikost slovníku** (``size``): výchozí slovník ``DEFAULT_CONCEPTS``
   (149) se rozšíří o pojmy katalogu WOLD (:func:`concept_data.catalog_order`:
   nejdřív základní slovní zásoba Swadeshova seznamu, pak sestupně podle
   frekvence). Slovník o ``n`` pojmech je vždy začátkem slovníku o ``n + 1``
   a tvary slov stávajících pojmů se nemění (zdroje gramatikalizace jsou
   hned za výchozími pojmy).
2. **Vlastní pojmy** (:class:`CustomConcept`), vymyšlené i reálné: povinné je
   ID; volitelně anglický glos nebo vazba na WOLD či Concepticon (pak se
   doména, půjčitelnost, frekvence, slovní druh i sémantické vztahy převezmou
   z dat), doména, frekvence, slovní druh, půjčitelnost a příbuzné pojmy
   pro posuny významu. Co autor nezadá, doplní engine (viz níže).

Výchozí slovník (149 pojmů, bez vlastních pojmů) je přesně dnešní: stejné
pořadí pojmů, graf ``core_graph()``, žádné doplňky.

**Pořadí pojmů** je deterministické a nezávisí na pořadí ve specifikaci:
výchozí pojmy, zdroje gramatikalizace (které nejsou mezi nimi), pojmy
katalogu podle :func:`concept_data.catalog_order`, nakonec vlastní pojmy
podle ID.

**Co doplní engine** vlastnímu pojmu bez vazby na data (zapisuje se do
:attr:`Concept.defaulted`):

- doména ``core``;
- půjčitelnost: průměr katalogu WOLD (domény pojmu, je-li ji autor zadal);
- frekvence: průměr frekvencí katalogu (domény pojmu, je-li ji autor zadal),
  na stupnici enginu (:data:`concept_data.FREQUENCY_RANGE`);
- slovní druh: podstatné jméno.

Pojem s vazbou na data si doménu, půjčitelnost, frekvenci a slovní druh
(podle kategorie WOLD) vezme z nich; co autor zadal, má přednost.

**Sémantické vztahy**: pro slovník větší než výchozí se graf pojmů staví
z ``v2_core_semantics.json`` (vztahy mezi výchozími pojmy beze změny)
a z ``v2_catalog_semantics.json`` (vztahy, kde je aspoň jeden pojem
z katalogu nebo vlastní s vazbou; DatSemShift a CLICS⁴, CC BY 4.0,
``scripts/build_v2_catalog_semantics.py``). Příbuzné pojmy zadané autorem
mají u dané dvojice a druhu vztahu přednost před daty.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Sequence

from cee.v2 import concept_data
from cee.v2.semantics import ConceptGraph, Relation, core_graph

#: Velikost výchozího slovníku: ``DEFAULT_CONCEPTS``.
DEFAULT_SIZE = 149
#: Velikosti, které UI nabízí jako předvolby (jiné čtení je povolené).
PRESET_SIZES = (149, 200, 500, 1000)
#: Slovní druhy vlastního pojmu.
WORD_CLASSES = ("noun", "verb", "uninflected")
#: Druhy vztahu mezi pojmy: posun významu, odvození a kolexifikace.
RELATION_KINDS = ("polysemy", "derivation", "colexification")
#: Směr vztahu od vlastního pojmu: ``to`` (slovo vlastního pojmu se posune k druhému
#: pojmu, resp. druhý se z něj odvodí), ``from`` (opačně), ``both``. Bez zadání platí
#: ``both`` u posunu významu a ``from`` u odvození (druhý pojem je základ vlastního);
#: kolexifikace je vždy oboustranná.
RELATION_DIRECTIONS = ("to", "from", "both")
DEFAULT_DIRECTION = {"polysemy": "both", "derivation": "from", "colexification": "both"}
#: Váha vztahu bez zadání, ve stejných jednotkách jako data (počet rodin, resp. jazyků):
#: posun a odvození 2 (data: medián 1, průměr 1,8 a 1,5), kolexifikace 9 (medián dat 9).
DEFAULT_WEIGHT = {"polysemy": 2, "derivation": 2, "colexification": 9}

#: ID vlastního pojmu: písmena, číslice, ``_``, ``.`` a ``-``; začíná písmenem nebo číslicí.
ID_PATTERN = re.compile(r"^\w[\w.-]*$")
CATALOG_SEMANTICS = Path(__file__).resolve().parents[1] / "data" / "v2_catalog_semantics.json"

ConceptOrigin = Literal["default", "engine", "catalog", "custom"]


@dataclass(frozen=True)
class Related:
    """Příbuzný pojem vlastního pojmu: druh vztahu, směr a váha."""

    concept: str
    kind: str = "polysemy"
    direction: str | None = None
    weight: int | None = None


@dataclass(frozen=True)
class CustomConcept:
    """Vlastní pojem autora světa (viz modul)."""

    id: str
    gloss: str | None = None
    wold: str | None = None
    concepticon: int | None = None
    domain: str | None = None
    frequency: float | None = None
    word_class: str | None = None
    borrowed: float | None = None
    related: tuple[Related, ...] = ()


@dataclass(frozen=True)
class Concept:
    """Pojem světa s tím, co o něm engine ví."""

    id: str
    origin: ConceptOrigin
    domain: str
    borrowed: float
    #: Frekvence na stupnici enginu; ``None`` = engine ji vygeneruje (zdroje
    #: gramatikalizace bez dat).
    frequency: float | None
    word_class: str
    gloss: str | None = None
    wold_id: str | None = None
    concepticon_id: int | None = None
    #: Pole, která engine doplnil výchozí hodnotou (autor je nezadal a vazba na data je nemá).
    defaulted: tuple[str, ...] = ()


@dataclass(frozen=True)
class Problem:
    """Chyba nebo varování ověření: cesta uvnitř specifikace (``concepts.0.id``) a zpráva."""

    path: str
    message: str
    severity: Literal["error", "warning"] = "error"


@lru_cache(maxsize=1)
def catalog_semantics() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(CATALOG_SEMANTICS.read_text(encoding="utf-8"))
    return loaded


def max_size() -> int:
    """Největší slovník: výchozí pojmy a všechny pojmy katalogu."""
    return DEFAULT_SIZE + len(concept_data.catalog_order())


def _default_ids() -> tuple[str, ...]:
    from cee.v2.scenarios import DEFAULT_CONCEPTS

    return tuple(DEFAULT_CONCEPTS)


def _base(size: int) -> list[tuple[str, ConceptOrigin]]:
    """Pojmy bez vlastních v pořadí simulace: výchozí, zdroje gramatikalizace, pojmy katalogu."""
    from cee.v2.language.constructions import GRAMMATICAL_SOURCES

    defaults = _default_ids()
    found: list[tuple[str, ConceptOrigin]] = [(concept, "default") for concept in defaults]
    found += [(concept, "engine") for concept in GRAMMATICAL_SOURCES if concept not in defaults]
    found += [(concept, "catalog") for concept in concept_data.catalog_order()[:max(0, size - DEFAULT_SIZE)]]
    return found


def base_ids(size: int) -> tuple[str, ...]:
    return tuple(concept for concept, _ in _base(size))


def _engine_class(word_class: str) -> str | None:
    return None if word_class == "uninflected" else word_class


def _data_class(entry: dict[str, Any]) -> str:
    """Slovní druh pojmu z kategorie WOLD: jména a slovesa se ohýbají, ostatní ne."""
    return {"Noun": "noun", "Verb": "verb"}.get(entry["category"], "uninflected")


def _link(item: CustomConcept) -> dict[str, Any] | None:
    """Význam katalogu, na který je vlastní pojem navázán (WOLD, Concepticon, glos, nebo ID katalogu)."""
    if item.wold is not None:
        return concept_data.find(wold=item.wold)
    if item.concepticon is not None:
        return concept_data.find(concepticon=item.concepticon)
    if item.gloss is not None:
        found = concept_data.find(gloss=item.gloss)
        if found is not None:
            return found
    return concept_data.catalog_ids().get(item.id)


def validate(size: int = DEFAULT_SIZE, custom: Sequence[CustomConcept] = ()) -> list[Problem]:
    """Chyby a varování slovníku; chyby s cestou ``vocabulary`` nebo ``concepts.<index>.<pole>``."""
    problems: list[Problem] = []
    top = max_size()
    if not DEFAULT_SIZE <= size <= top:
        problems.append(Problem("vocabulary", f"velikost slovníku musí být {DEFAULT_SIZE} až {top} pojmů"))
        size = min(max(size, DEFAULT_SIZE), top)
    base = base_ids(size)
    present = set(base)
    seen: dict[str, int] = {}
    for index, item in enumerate(custom):
        if not ID_PATTERN.match(item.id):
            problems.append(Problem(f"concepts.{index}.id",
                                    "ID smí obsahovat jen písmena, číslice, _ . - a začít písmenem nebo číslicí"))
        elif item.id in seen:
            problems.append(Problem(f"concepts.{index}.id", f"pojem '{item.id}' je v seznamu vícekrát"))
        elif item.id in present:
            problems.append(Problem(
                f"concepts.{index}.id",
                f"pojem '{item.id}' už ve slovníku je; zvol jiné ID (nebo vazbu na WOLD, "
                "chceš-li stejný význam podruhé)"))
        seen.setdefault(item.id, index)
    world = present | set(seen)
    known_domains = set(concept_data.DOMAINS)
    for index, item in enumerate(custom):
        where = f"concepts.{index}"
        if item.wold is not None and item.concepticon is not None:
            problems.append(Problem(where, "zadej jen jednu vazbu na data: wold, nebo concepticon"))
        elif item.wold is not None and concept_data.find(wold=item.wold) is None:
            problems.append(Problem(f"{where}.wold", f"neznámý význam WOLD '{item.wold}' (není v katalogu)"))
        elif item.concepticon is not None and concept_data.find(concepticon=item.concepticon) is None:
            problems.append(Problem(f"{where}.concepticon",
                                    f"Concepticon {item.concepticon} nemá v katalogu WOLD žádný význam"))
        if item.domain is not None and item.domain not in known_domains:
            problems.append(Problem(f"{where}.domain", "neznámá doména '%s'; možnosti: %s"
                                    % (item.domain, ", ".join(concept_data.DOMAINS))))
        low, high = concept_data.FREQUENCY_RANGE
        if item.frequency is not None and not low <= item.frequency <= high:
            problems.append(Problem(f"{where}.frequency", f"frekvence musí být {low} až {high}"))
        if item.borrowed is not None and not 0.0 <= item.borrowed <= 1.0:
            problems.append(Problem(f"{where}.borrowed", "půjčitelnost musí být 0 až 1"))
        if item.word_class is not None and item.word_class not in WORD_CLASSES:
            problems.append(Problem(f"{where}.word_class", "neznámý slovní druh '%s'; možnosti: %s"
                                    % (item.word_class, ", ".join(WORD_CLASSES))))
        pairs: set[tuple[str, str, str]] = set()
        for position, related in enumerate(item.related):
            path = f"{where}.related.{position}"
            if related.concept == item.id:
                problems.append(Problem(f"{path}.concept", "pojem nemůže být příbuzný sám sobě"))
            elif related.concept not in world:
                hint = (" (pojem katalogu je ve větším slovníku)"
                        if related.concept in concept_data.catalog_ids() else "")
                problems.append(Problem(f"{path}.concept",
                                        f"neznámý pojem '{related.concept}' (není ve slovníku){hint}"))
            if related.kind not in RELATION_KINDS:
                problems.append(Problem(f"{path}.kind", "neznámý druh vztahu '%s'; možnosti: %s"
                                        % (related.kind, ", ".join(RELATION_KINDS))))
            if related.direction is not None and related.direction not in RELATION_DIRECTIONS:
                problems.append(Problem(f"{path}.direction", "neznámý směr '%s'; možnosti: %s"
                                        % (related.direction, ", ".join(RELATION_DIRECTIONS))))
            if related.weight is not None and related.weight < 1:
                problems.append(Problem(f"{path}.weight", "váha musí být aspoň 1"))
            key = (related.concept, related.kind, related.direction or DEFAULT_DIRECTION.get(related.kind, ""))
            if key in pairs:
                problems.append(Problem(path, f"vztah k '{related.concept}' je zadaný vícekrát"))
            pairs.add(key)
    problems.extend(_warnings(size, custom, base))
    return problems


def _warnings(size: int, custom: Sequence[CustomConcept], base: tuple[str, ...]) -> list[Problem]:
    """Varování: jiný slovník dá jiné výsledky, vlastní pojem může zdvojit význam."""
    found: list[Problem] = []
    if size != DEFAULT_SIZE:
        found.append(Problem(
            "vocabulary",
            f"slovník o {size} pojmech dá jiné výsledky než výchozí svět ({DEFAULT_SIZE} pojmů): slova "
            "nových pojmů soutěží se stávajícími a kalibrace bran platí jen pro výchozí slovník",
            "warning"))
    if custom:
        found.append(Problem(
            "concepts", "vlastní pojmy dají jiné výsledky než výchozí svět: jejich slova soutěží se "
            "stávajícími a kalibrace bran platí jen pro výchozí slovník", "warning"))
    meanings = {entry["wold_id"]: concept for concept in base if (entry := concept_data.info(concept)) is not None}
    for index, item in enumerate(custom):
        linked = _link(item)
        if linked is not None and linked["wold_id"] in meanings and meanings[linked["wold_id"]] != item.id:
            found.append(Problem(
                f"concepts.{index}", f"stejný význam WOLD ('{linked['name']}') už má pojem "
                f"'{meanings[linked['wold_id']]}'; slova obou pojmů budou soutěžit", "warning"))
    return found


@dataclass(frozen=True)
class Vocabulary:
    """Pojmy světa v pořadí simulace a vlastní vztahy; staví ho :func:`resolve`."""

    size: int
    concepts: tuple[Concept, ...]
    custom: tuple[CustomConcept, ...] = ()

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(concept.id for concept in self.concepts)

    @property
    def is_default(self) -> bool:
        """Výchozí slovník: bez rozšíření a bez vlastních pojmů (výsledky jako dřív)."""
        return self.size == DEFAULT_SIZE and not self.custom

    def concept(self, concept_id: str) -> Concept:
        return self._index[concept_id]

    def domain(self, concept_id: str) -> str:
        return self._index[concept_id].domain

    def borrowed(self, concept_id: str) -> float:
        return self._index[concept_id].borrowed

    @property
    def _index(self) -> dict[str, Concept]:
        index: dict[str, Concept] | None = self.__dict__.get("_by_id")
        if index is None:
            index = {concept.id: concept for concept in self.concepts}
            object.__setattr__(self, "_by_id", index)
        return index

    def word_classes(self) -> dict[str, str | None]:
        """Pojem → třída slova světa (``None`` = neohebné)."""
        return {concept.id: _engine_class(concept.word_class) for concept in self.concepts}

    def known_frequencies(self) -> dict[str, float]:
        """Frekvence, které protojazyk nemá brát z dat podle ID: vlastní pojmy."""
        return {concept.id: concept.frequency for concept in self.concepts
                if concept.origin == "custom" and concept.frequency is not None}

    def describe(self) -> list[dict[str, Any]]:
        """Vlastní pojmy se všemi hodnotami (zadanými i doplněnými) pro UI."""
        return [
            {"id": concept.id, "gloss": concept.gloss, "domain": concept.domain, "frequency": concept.frequency,
             "borrowed": concept.borrowed, "word_class": concept.word_class, "wold": concept.wold_id,
             "concepticon": concept.concepticon_id, "defaulted": list(concept.defaulted)}
            for concept in self.concepts if concept.origin == "custom"
        ]

    def graph(self) -> ConceptGraph:
        """Graf pojmů pro posun významu, odvozování a skládání (viz modul)."""
        core = core_graph()
        if self.is_default:
            return core
        cached: ConceptGraph | None = self.__dict__.get("_graph")
        if cached is not None:
            return cached
        ids = set(self.ids)
        defaults = set(_default_ids())
        values: dict[tuple[str, str], dict[str, int]] = {}
        for relation in core.relations:
            if relation.source in ids and relation.target in ids:
                values[(relation.source, relation.target)] = {
                    "polysemy": relation.polysemy, "derivation": relation.derivation,
                    "colexification": relation.colexification,
                }
        owners = self._owners()
        data = catalog_semantics()["relations"]
        for source, target, polysemy, derivation, colexification in data:
            for first in owners.get(source, ()):
                for second in owners.get(target, ()):
                    if first == second or (first in defaults and second in defaults):
                        continue
                    item = values.setdefault((first, second), {})
                    for kind, value in (("polysemy", polysemy), ("derivation", derivation),
                                        ("colexification", colexification)):
                        item[kind] = max(item.get(kind, 0), value)
        for own in self.custom:
            for related in own.related:
                weight = related.weight or DEFAULT_WEIGHT[related.kind]
                chosen = related.direction or DEFAULT_DIRECTION[related.kind]
                directions = ("to", "from") if chosen == "both" or related.kind == "colexification" else (chosen,)
                for direction in directions:
                    pair = (own.id, related.concept) if direction == "to" else (related.concept, own.id)
                    values.setdefault(pair, {})[related.kind] = weight
        relations = tuple(
            Relation(source, target, item.get("polysemy", 0), item.get("derivation", 0),
                     item.get("colexification", 0))
            for (source, target), item in sorted(values.items()) if any(item.values())
        )
        built = ConceptGraph(relations, core.compounds)
        object.__setattr__(self, "_graph", built)
        return built

    def _owners(self) -> dict[int, list[str]]:
        """ID Concepticonu → pojmy světa s tímto významem (pojem enginu má i druhé ID z výřezu)."""
        aliases: dict[str, int] = catalog_semantics()["aliases"]
        owners: dict[int, list[str]] = {}
        for concept in self.concepts:
            ids = [concept.concepticon_id] if concept.concepticon_id is not None else []
            if concept.id in aliases:
                ids.append(aliases[concept.id])
            for found in ids:
                owners.setdefault(found, []).append(concept.id)
        return owners


def _concept(concept_id: str, origin: ConceptOrigin) -> Concept:
    from cee.v2.scenarios import word_class

    entry = concept_data.info(concept_id)
    kind = (word_class(concept_id) or "uninflected") if entry is None or origin == "default" else _data_class(entry)
    if entry is None:  # zdroj gramatikalizace bez dat: frekvenci vygeneruje protojazyk, jako vždy
        return Concept(concept_id, origin, "core", concept_data.mean_borrowed(), None, kind,
                       defaulted=("domain", "borrowed", "frequency"))
    return Concept(
        concept_id, origin, str(entry["domain"]), concept_data.borrowed(concept_id),
        concept_data.frequency(concept_id), kind,
        gloss=entry["name"], wold_id=entry["wold_id"], concepticon_id=entry["concepticon_id"],
    )


def _custom(item: CustomConcept) -> Concept:
    linked = _link(item)
    defaulted: list[str] = []
    domain = item.domain
    if domain is None:
        domain = "core" if linked is None else str(linked["domain"])
        if linked is None:
            defaulted.append("domain")
    scope = item.domain if item.domain is not None else (str(linked["domain"]) if linked is not None else None)
    if item.borrowed is not None:
        borrowed = item.borrowed
    elif linked is not None and linked["borrowed"] is not None:
        borrowed = float(linked["borrowed"])
    else:
        borrowed = concept_data.mean_borrowed(scope)
        defaulted.append("borrowed")
    if item.frequency is not None:
        frequency = item.frequency
    else:
        known = None if linked is None else concept_data.item_frequency(linked)
        if known is None:
            frequency = concept_data.mean_frequency(scope)
            defaulted.append("frequency")
        else:
            frequency = known
    if item.word_class is not None:
        word_class = item.word_class
    elif linked is not None:
        word_class = _data_class(linked)
    else:
        word_class = "noun"
        defaulted.append("word_class")
    return Concept(
        item.id, "custom", domain, borrowed, frequency, word_class,
        gloss=item.gloss if item.gloss is not None else (None if linked is None else linked["name"]),
        wold_id=None if linked is None else linked["wold_id"],
        concepticon_id=None if linked is None else linked["concepticon_id"],
        defaulted=tuple(defaulted),
    )


def resolve(size: int = DEFAULT_SIZE, custom: Sequence[CustomConcept] = ()) -> Vocabulary:
    """Slovník o ``size`` pojmech a s vlastními pojmy; chybný vstup vyhodí ``ValueError``."""
    errors = [problem for problem in validate(size, custom) if problem.severity == "error"]
    if errors:
        raise ValueError("; ".join(f"{problem.path}: {problem.message}" for problem in errors))
    concepts = [_concept(concept_id, origin) for concept_id, origin in _base(size)]
    ordered = tuple(sorted(custom, key=lambda item: item.id))
    concepts.extend(_custom(item) for item in ordered)
    return Vocabulary(size, tuple(concepts), ordered)


