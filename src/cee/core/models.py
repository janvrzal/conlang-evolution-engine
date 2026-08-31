import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class Segment:
    """
    Represents a single phonological segment.
    Uses a feature matrix rather than just a character string.
    """

    features: Dict[str, str] = field(default_factory=dict)

    def matches(self, target_features: Dict[str, str]) -> bool:
        """
        Check if this segment matches a given feature bundle.
        Example: target_features = {'son': '-', 'voice': '+', 'cont': '-'}
        """
        for feature, value in target_features.items():
            if self.features.get(feature) != value:
                return False
        return True




@dataclass
class Word:
    """
    A single lexical item, which is a sequence of Segments.
    """

    concept_id: str
    segments: List[Segment]
    polysemy: Set[str] = field(default_factory=set)  # Dodatečné významy (sémantické posuny)
    origin_year: int = 0
    source_id: Optional[str] = None  # ID zdrojového uzlu v případě výpůjčky
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_word_id: Optional[str] = None
    origin_type: str = "inherited"  # inherited, mutated, borrowed
    origin_rule: Optional[str] = None  # if mutated, rule name
    is_grammatical: bool = False
    # Index přízvučného slabičného jádra v `segments`. Nejde o ortografii,
    # ale o prosodickou informaci, kterou mohou používat zvuková pravidla.
    stress_index: Optional[int] = None
    #: Relativní užívání (0–1). Historické procesy typicky chrání frekventní
    #: základní slova a naopak rychleji obměňují okrajový lexikon.
    frequency: float = 0.5
    #: Slot může zůstat v lexikonu jako historická stopa, aniž by byl živým
    #: kandidátem pro výpůjčku nebo analogii.
    active: bool = True
    #: Hranice mezi segmenty (index prvního segmentu následujícího morfému).
    #: Prázdná množina znamená jednoduchý kořen.
    morpheme_boundaries: Set[int] = field(default_factory=set)
    #: Jádra slabik nesoucí kontrastivní délku. Délka se drží mimo PanPhonovy
    #: segmentové rysy, protože IPA ː není samostatný segment.
    long_nuclei: Set[int] = field(default_factory=set)
    #: Členové jednoho paradigmatu sdílejí kmen a mohou podléhat analogii.
    paradigm: Optional[str] = None
    grammatical_features: Dict[str, str] = field(default_factory=dict)
    #: Stabilní identita lexému napříč jeho historickými verzemi. ``id`` se
    #: při každé doložené změně mění, zatímco lineage_id dovoluje dlouhotrvající
    #: inovaci najít i poté, co mezitím proběhla jiná změna nebo odštěpení.
    #: Je na konci kvůli kompatibilitě existujících pozičních konstruktorů.
    lineage_id: Optional[str] = None
    #: Tón přiřazený slabičnému jádru (index segmentu -> H/L/R). Drží se mimo
    #: PanPhonovy segmentové rysy, protože tón není samostatný segment.
    tones: Dict[int, str] = field(default_factory=dict)

    def ensure_stress(self) -> None:
        """Dá slovu deterministický výchozí přízvuk na první samohlásce."""
        # Tóny se vedle objektového pole otiskují i do běžných metadat slova.
        # Tím přežijí starší úložiště, která ještě neznají samostatný sloupec.
        if not self.tones and self.grammatical_features.get("phonology.tones"):
            parsed: Dict[int, str] = {}
            for item in self.grammatical_features["phonology.tones"].split(","):
                index, separator, tone = item.partition(":")
                if separator and index.isdigit() and tone in {"H", "L", "R"}:
                    parsed[int(index)] = tone
            self.tones = parsed
        nuclei = [
            i for i, segment in enumerate(self.segments) if segment.features.get("syl") == "+"
        ]
        if not nuclei:
            self.stress_index = None
        elif self.stress_index not in nuclei:
            self.stress_index = nuclei[0]
        self.long_nuclei.intersection_update(nuclei)
        self.tones = {index: tone for index, tone in self.tones.items() if index in nuclei}
        if self.tones:
            self.grammatical_features["phonology.tones"] = ",".join(
                f"{index}:{tone}" for index, tone in sorted(self.tones.items())
            )
        else:
            self.grammatical_features.pop("phonology.tones", None)
        self.morpheme_boundaries = {
            boundary for boundary in self.morpheme_boundaries if 0 < boundary < len(self.segments)
        }

    def syllable_nuclei(self) -> List[int]:
        """Indexy samohlásek, které tvoří jádra slabik."""
        return [i for i, segment in enumerate(self.segments) if segment.features.get("syl") == "+"]


@dataclass
class Lexicon:
    """
    A collection of words for a specific state.
    """

    words: List[Word] = field(default_factory=list)

    def get_word(self, concept_id: str) -> Optional[Word]:
        """Vrátí první živé slovo pokrývající tento koncept."""
        for word in self.words:
            if word.active and (word.concept_id == concept_id or concept_id in word.polysemy):
                return word
        return None

    def get_words(self, concept_id: str) -> List[Word]:
        """Vrátí všechna živá slova pokrývající koncept (synonyma)."""
        return [
            word
            for word in self.words
            if word.active and (word.concept_id == concept_id or concept_id in word.polysemy)
        ]


@dataclass
class Inventory:
    """
    The set of phonemes available in a given state.
    Serves as the phonotactic filter and state tracking for rules.
    """

    segments: Set[str] = field(default_factory=set)


@dataclass
class PopulationProfile:
    """Záměrně hrubá demografie: řád velikosti, nikoli falešná přesnost."""

    size: int = 0
    area: float = 0.0
    concentration: float = 0.5
    centers: int = 1


@dataclass
class SpeechCommunity:
    """Jedna sociální nebo regionální skupina mluvčích uvnitř jazyka."""

    id: str
    share: float = 1.0
    prestige: float = 0.5
    mobility: float = 0.5
    domains: Set[str] = field(default_factory=set)
    kind: str = "social"
    variety_id: Optional[str] = None


@dataclass
class VarietyState:
    """Lehká dialektní odchylka; lexikon se zde nekopíruje."""

    id: str
    community_id: str
    divergence: float = 0.0
    split_candidate: bool = False


@dataclass
class State:
    """Stav jazyka v určitém čase/uzlu."""

    node_id: str
    inventory: Inventory
    lexicon: Lexicon
    year: int = 0
    parent_id: Optional[str] = None
    map: Dict[str, Any] = field(default_factory=dict)

    # Morfologické / Typologické parametry
    affixation_strategy: str = "suffix"  # "prefix" nebo "suffix"
    compound_head: str = "final"  # "initial" nebo "final"
    #: Malý, vysvětlitelný sociolingvistický profil. Nejde o simulaci každého
    #: mluvčího, ale o parametry, které mění rychlost šíření inovací a kontakt.
    social: Dict[str, float] = field(default_factory=dict)
    population: PopulationProfile = field(default_factory=PopulationProfile)
    communities: Dict[str, SpeechCommunity] = field(default_factory=dict)
    varieties: Dict[str, VarietyState] = field(default_factory=dict)

    def __post_init__(self):
        if self.map is None:
            self.map = {}
        if "compound_head" in self.map:
            self.compound_head = self.map["compound_head"]
        if "affixation_strategy" in self.map:
            self.affixation_strategy = self.map["affixation_strategy"]
        raw_social = self.map.get("social", self.map.get("society", {}))
        if isinstance(raw_social, dict):
            self.social = {
                key: max(0.0, min(1.0, float(value)))
                for key, value in raw_social.items()
                if key in {"prestige", "mobility", "literacy", "standardization", "population"}
            }
        population = self.map.get("population", {})
        if isinstance(population, dict):
            try:
                self.population = PopulationProfile(
                    size=max(0, int(population.get("size", self.population.size))),
                    area=max(0.0, float(population.get("area", self.population.area))),
                    concentration=max(
                        0.0,
                        min(1.0, float(population.get("concentration", self.population.concentration))),
                    ),
                    centers=max(1, int(population.get("centers", self.population.centers))),
                )
            except (TypeError, ValueError):
                pass
        raw_communities = self.map.get("communities", [])
        if isinstance(raw_communities, list) and raw_communities:
            parsed: Dict[str, SpeechCommunity] = {}
            for index, item in enumerate(raw_communities):
                if not isinstance(item, dict):
                    continue
                identifier = str(item.get("id", f"community-{index + 1}")).strip()
                if not identifier:
                    continue
                parsed[identifier] = SpeechCommunity(
                    id=identifier,
                    share=max(0.0, float(item.get("share", 1.0))),
                    prestige=max(0.0, min(1.0, float(item.get("prestige", 0.5)))),
                    mobility=max(0.0, min(1.0, float(item.get("mobility", 0.5)))),
                    domains={str(value).strip().lower() for value in item.get("domains", []) if str(value).strip()},
                    kind=str(item.get("kind", "social")).strip().lower() or "social",
                    variety_id=(str(item["variety_id"]) if item.get("variety_id") else None),
                )
            if parsed:
                total = sum(item.share for item in parsed.values())
                if total > 0:
                    for item in parsed.values():
                        item.share /= total
                self.communities = parsed
        if self.communities and not self.varieties:
            for community in self.communities.values():
                if community.variety_id or community.kind in {"regional", "rural", "urban"}:
                    variety_id = community.variety_id or f"variety:{community.id}"
                    community.variety_id = variety_id
                    self.varieties[variety_id] = VarietyState(variety_id, community.id)
