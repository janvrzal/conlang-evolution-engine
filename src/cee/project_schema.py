"""Stabilní, verzovaný kontrakt persistentního projektu.

Vnější objekt projektu smí nést neznámá pole, aby novější klient data
neztratil. Vstupy, které mají význam pro simulátor, jsou naproti tomu malé
a přísně typované modely. Migrace jsou čisté funkce: načtení nikdy samo
nepřepisuje soubor na disku.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CURRENT_PROJECT_SCHEMA = 3
MIN_YEAR = -100_000
MAX_YEAR = 100_000


class ContractModel(BaseModel):
    """Kritické vnitřní struktury neakceptují překlepy ani tiché aliasy."""

    model_config = ConfigDict(extra="forbid")


class Point(ContractModel):
    x: float
    y: float


class ProtoLexeme(ContractModel):
    id: str = Field(min_length=1)
    ipa: str = Field(min_length=1)
    polysemy: list[str] = Field(default_factory=list)
    frequency: float | None = Field(default=None, ge=0.0, le=1.0)
    grammatical_features: dict[str, str] = Field(default_factory=dict)
    is_grammatical: bool = False


class LanguageNodeData(BaseModel):
    """Nastavení jazyka. Další engine parametry jsou zatím transparentní."""

    model_config = ConfigDict(extra="allow")

    label: str = "Jazyk"
    year: int = Field(default=0, ge=MIN_YEAR, le=MAX_YEAR)
    isProto: bool = False
    endonym: str | None = None
    exonym: str | None = None
    communityId: str | None = None


class LanguageNode(ContractModel):
    id: str = Field(min_length=1)
    type: Literal["language"] = "language"
    position: Point = Field(default_factory=lambda: Point(x=0, y=0))
    data: LanguageNodeData = Field(default_factory=LanguageNodeData)


class InheritanceEdge(ContractModel):
    id: str | None = None
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    type: Literal["straight"] = "straight"
    animated: bool | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ContactEdgeData(ContractModel):
    year: int | None = Field(default=None, ge=MIN_YEAR, le=MAX_YEAR)
    direction: Literal["both", "ab", "ba"] = "both"
    volume: int = Field(default=5, ge=1, le=10_000)
    intensity: float = Field(default=50.0, ge=0.0, le=100.0)
    contactType: str = "neighborhood"
    prestige: float = Field(default=1.0, ge=0.0, le=100.0)
    calqueRate: float = Field(default=0.0, ge=0.0, le=1.0)
    adapt: bool = True
    mutual: bool = False
    layer: str = "folk"
    transferMorphology: bool = False
    resolveHomophony: bool = False
    constructionIds: list[str] = Field(default_factory=list)


class ContactEdge(ContractModel):
    id: str | None = None
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    type: Literal["contact"] = "contact"
    animated: bool | None = None
    data: ContactEdgeData = Field(default_factory=ContactEdgeData)


class TimelineSnapshot(ContractModel):
    nodes: list[LanguageNode] = Field(default_factory=list)
    edges: list[InheritanceEdge | ContactEdge] = Field(default_factory=list)


class Community(ContractModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    share: float = Field(default=1.0, ge=0.0, le=1.0)
    languageIds: list[str] = Field(default_factory=list)
    varietyIds: list[str] = Field(default_factory=list)


class Variety(ContractModel):
    id: str = Field(min_length=1)
    languageId: str = Field(min_length=1)
    communityId: str | None = None
    name: str = Field(min_length=1)
    intensity: float = Field(default=0.0, ge=0.0, le=1.0)


class SocialTie(ContractModel):
    sourceCommunityId: str = Field(min_length=1)
    targetCommunityId: str = Field(min_length=1)
    intensity: float = Field(ge=0.0, le=1.0)
    kind: str = "contact"


class Polity(ContractModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    territory: list[Point] = Field(default_factory=list)
    institutions: dict[str, float] = Field(default_factory=dict)
    languageIds: list[str] = Field(default_factory=list)

    @field_validator("institutions")
    @classmethod
    def institution_intensities(cls, value: dict[str, float]) -> dict[str, float]:
        for key, intensity in value.items():
            if not 0 <= intensity <= 1:
                raise ValueError(f"institutions.{key} musí být v intervalu 0–1")
        return value


class TradeRoute(ContractModel):
    id: str = Field(min_length=1)
    kind: Literal["land", "sea", "river"] = "land"
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    languageIds: list[str] = Field(default_factory=list, min_length=2)
    startYear: int = Field(default=0, ge=MIN_YEAR, le=MAX_YEAR)
    endYear: int | None = Field(default=None, ge=MIN_YEAR, le=MAX_YEAR)
    waypoints: list[Point] = Field(default_factory=list)

    @model_validator(mode="after")
    def ordered_window(self):
        if self.endYear is not None and self.endYear < self.startYear:
            raise ValueError("endYear obchodní trasy nesmí předcházet startYear")
        return self


class HistoricalEvent(ContractModel):
    id: str = Field(min_length=1)
    kind: str = Field(default="migration", min_length=1)
    startYear: int = Field(default=0, ge=MIN_YEAR, le=MAX_YEAR)
    duration: int = Field(default=0, ge=0, le=MAX_YEAR - MIN_YEAR)
    targetLanguageIds: list[str] = Field(default_factory=list)
    targetPolityId: str | None = None
    effects: dict[str, Any] = Field(default_factory=dict)
    endonym: str = ""
    exonym: str = ""


class LanguageName(ContractModel):
    languageId: str = Field(min_length=1)
    endonym: str | None = None
    exonym: str | None = None
    startYear: int = Field(default=0, ge=MIN_YEAR, le=MAX_YEAR)
    sourceEventId: str | None = None


class CalibrationSettings(ContractModel):
    sound_changes_per_millennium: float = Field(default=8.0, ge=0.0, le=1_000.0)
    change_spread_years: float = Field(default=120.0, ge=0.0, le=MAX_YEAR - MIN_YEAR)
    isolation: float = Field(default=0.5, ge=0.0, le=1.0)
    replacement_rate: float = Field(default=0.01, ge=0.0, le=1.0)
    loss_rate: float = Field(default=0.005, ge=0.0, le=1.0)
    homophony_resolution_rate: float = Field(default=0.3, ge=0.0, le=1.0)


class SimulationSettings(ContractModel):
    seed: int = 42
    schemaProfileId: str = "heuristic-default"
    empiricalPhonology: bool = False
    calibration: CalibrationSettings = Field(default_factory=CalibrationSettings)


class SavedRun(ContractModel):
    id: str = Field(min_length=1)
    createdAt: str | None = None


class MapBackground(ContractModel):
    dataUrl: str = Field(min_length=1)
    scale: float = Field(default=100.0, gt=0.0, le=10_000.0)
    opacity: float = Field(default=0.35, ge=0.0, le=1.0)


class ProjectData(BaseModel):
    """Kanonický V3 obsah projektu; extra jsou uchována jen na této hraně."""

    model_config = ConfigDict(extra="allow")

    generatedProtoLexicon: list[ProtoLexeme] = Field(default_factory=list)
    timeSteps: list[int] = Field(default_factory=lambda: [0, 500, 1000, 1500])
    snapshots: dict[str, TimelineSnapshot] = Field(default_factory=dict)
    communities: list[Community] = Field(default_factory=list)
    varieties: list[Variety] = Field(default_factory=list)
    socialTies: list[SocialTie] = Field(default_factory=list)
    polities: list[Polity] = Field(default_factory=list)
    tradeRoutes: list[TradeRoute] = Field(default_factory=list)
    historicalEvents: list[HistoricalEvent] = Field(default_factory=list)
    languageNames: list[LanguageName] = Field(default_factory=list)
    protoLanguages: list[dict[str, Any]] = Field(default_factory=list)
    simulation: SimulationSettings = Field(default_factory=SimulationSettings)
    savedRun: SavedRun | None = None
    mapBackground: MapBackground | None = None

    @field_validator("timeSteps")
    @classmethod
    def canonical_timeline(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("timeSteps nesmí být prázdná")
        if any(not MIN_YEAR <= year <= MAX_YEAR for year in value):
            raise ValueError(f"Rok musí být v intervalu {MIN_YEAR}–{MAX_YEAR}")
        if value != sorted(set(value)):
            raise ValueError("timeSteps musí být vzestupné a bez duplicit")
        return value

    @model_validator(mode="after")
    def references_exist(self):
        snapshot_years: set[int] = set()
        for key in self.snapshots:
            try:
                snapshot_years.add(int(key))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Neplatný klíč snímku: {key!r}") from exc
        if not snapshot_years.issubset(set(self.timeSteps)):
            raise ValueError("Každý snímek musí patřit do timeSteps")
        # Snímek je stav téže časové osy, ne samostatný jazykový registr:
        # proto se identita jazyka přirozeně opakuje napříč roky. Duplicitní
        # uzel je neplatný pouze uvnitř jednoho snímku.
        language_ids: set[str] = set()
        for snapshot_year, snapshot in self.snapshots.items():
            snapshot_language_ids = [node.id for node in snapshot.nodes]
            _unique(f"jazyk ve snímku {snapshot_year}", set(snapshot_language_ids), snapshot_language_ids)
            language_ids.update(snapshot_language_ids)
        community_ids = {community.id for community in self.communities}
        polity_ids = {polity.id for polity in self.polities}
        event_ids = {event.id for event in self.historicalEvents}
        _unique("komunita", community_ids, [item.id for item in self.communities])
        _unique("varieta", {item.id for item in self.varieties}, [item.id for item in self.varieties])
        _unique("stát", polity_ids, [item.id for item in self.polities])
        _unique("událost", event_ids, [item.id for item in self.historicalEvents])
        for snapshot in self.snapshots.values():
            for edge in snapshot.edges:
                _require_refs("hrana", [edge.source, edge.target], language_ids)
            for node in snapshot.nodes:
                if node.data.communityId is not None:
                    _require_refs(f"jazyk {node.id}", [node.data.communityId], community_ids)
        for collection in (self.communities, self.polities, self.tradeRoutes):
            for item in collection:
                _require_refs(f"{type(item).__name__} {item.id}", item.languageIds, language_ids)
        for variety in self.varieties:
            _require_refs(f"varieta {variety.id}", [variety.languageId], language_ids)
            if variety.communityId is not None:
                _require_refs(f"varieta {variety.id}", [variety.communityId], community_ids)
        variety_ids = {item.id for item in self.varieties}
        for community in self.communities:
            _require_refs(f"komunita {community.id}", community.varietyIds, variety_ids)
        for tie in self.socialTies:
            _require_refs("sociální vazba", [tie.sourceCommunityId, tie.targetCommunityId], community_ids)
        for event in self.historicalEvents:
            _require_refs(f"událost {event.id}", event.targetLanguageIds, language_ids)
            if event.targetPolityId is not None:
                _require_refs(f"událost {event.id}", [event.targetPolityId], polity_ids)
        for name in self.languageNames:
            _require_refs("název jazyka", [name.languageId], language_ids)
            if name.sourceEventId is not None:
                _require_refs("název jazyka", [name.sourceEventId], event_ids)
        return self


def _unique(kind: str, ids: set[str], original: list[str]) -> None:
    if len(ids) != len(original):
        raise ValueError(f"Duplicitní ID: {kind}")


def _require_refs(owner: str, refs: list[str], available: set[str]) -> None:
    missing = sorted(set(refs) - available)
    if missing:
        raise ValueError(f"{owner} odkazuje na neexistující ID: {', '.join(missing)}")


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(data)
    result.setdefault("generatedProtoLexicon", [])
    result.setdefault("timeSteps", [0, 500, 1000, 1500])
    result.setdefault("snapshots", {})
    result.setdefault("protoLanguages", [])
    result.setdefault("simulationRunAt", None)
    result.setdefault("simulationRunId", None)
    result["timeSteps"] = sorted({int(year) for year in result["timeSteps"]})
    result["snapshots"] = {str(int(year)): value for year, value in result["snapshots"].items()}
    return result


def _migrate_v2_to_v3(data: dict[str, Any]) -> dict[str, Any]:
    """Převede volná historická a prostorová pole na explicitní V3 sekce."""
    result = deepcopy(data)
    for key in ("communities", "varieties", "socialTies", "polities", "tradeRoutes", "historicalEvents", "languageNames"):
        result.setdefault(key, [])
    if "simulation" not in result:
        result["simulation"] = {
            "seed": 42,
            "schemaProfileId": result.get("schemaProfileId", "heuristic-default"),
            "empiricalPhonology": result.get("empiricalPhonology", False),
            "calibration": result.get("calibration", {}),
        }
    if "savedRun" not in result and result.get("simulationRunId"):
        result["savedRun"] = {"id": result["simulationRunId"], "createdAt": result.get("simulationRunAt")}
    # Legacy aliasy zůstávají jako extra pole; simulátor čte jen V3 sekce.
    return result


def migrate_data(version: int, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Provede každou podporovanou migraci zvlášť, bez změny vstupu."""
    if version > CURRENT_PROJECT_SCHEMA:
        raise ValueError(f"Projekt má novější schéma {version}; tato verze CEE umí nejvýše {CURRENT_PROJECT_SCHEMA}.")
    if version < 1:
        raise ValueError(f"Projekt má nepodporované schéma {version}.")
    current, migrated = version, deepcopy(data)
    while current < CURRENT_PROJECT_SCHEMA:
        if current == 1:
            migrated = _migrate_v1_to_v2(migrated)
        elif current == 2:
            migrated = _migrate_v2_to_v3(migrated)
        current += 1
    return current, migrated


def normalize_data(version: int, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Migruje a přísně ověří data před jejich použitím nebo zápisem."""
    migrated_version, migrated = migrate_data(version, data)
    return migrated_version, ProjectData.model_validate(migrated).model_dump(mode="json", round_trip=True, exclude_unset=True)


def validate_simulation_topology(topology: dict[str, Any]) -> ProjectData:
    """Ověří stejný kontrakt i pro přímý vstup do simulace."""
    payload = deepcopy(topology)
    snapshots = payload.get("snapshots")
    if isinstance(snapshots, list):
        payload["snapshots"] = {str(item["year"]): {"nodes": item.get("nodes", []), "edges": item.get("edges", [])} for item in snapshots}
        payload.setdefault("timeSteps", sorted(int(item["year"]) for item in snapshots))
    elif "nodes" in payload:
        nodes = []
        for node_id, config in payload.pop("nodes", {}).items():
            config = dict(config)
            position = config.pop("position", {}) or {}
            position = {"x": position.get("x", 0), "y": position.get("y", 0)}
            nodes.append({"id": node_id, "position": position, "data": config})
        edges = []
        for edge in payload.pop("edges", []):
            converted = dict(edge)
            kind = converted.pop("kind", None)
            if kind == "contact":
                converted["type"] = "contact"
                converted["data"] = {"volume": converted.pop("volume", 5), "prestige": converted.pop("prestige", 1.0), "mutual": converted.pop("mutual", True)}
            else:
                converted["type"] = "straight"
                converted.setdefault("data", {})
            edges.append(converted)
        payload["snapshots"] = {"0": {"nodes": nodes, "edges": edges}}
        payload.setdefault("timeSteps", [0])
    return ProjectData.model_validate(payload)
