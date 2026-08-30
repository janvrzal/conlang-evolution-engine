"""
Generátor zvukových změn (CEE_master.md 4.4).

Skládá chronologii pravidel ze tří vrstev:

1. **Inventář schémat** — `schemas.SCHEMA_REGISTRY`.
2. **Priory** — váhy z presetu, modifikované biomem uzlu.
3. **Filtr věrohodnosti** — prostředí musí být v aktuálním inventáři neprázdné
(řeší `Schema.generate_rule`) a sekvence nesmí obsahovat zvrácení už proběhlé
změny (řeší `_reverses` níže).

Inventář se mezi pravidly průběžně aktualizuje, takže pozdější změna vidí to,
co jí předchozí připravila.
"""
import random
import warnings
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

from cee.core.models import State
from cee.engine.inventory import InventoryView
from cee.engine.rules import Rule
from cee.engine.schemas import SCHEMA_REGISTRY

# Kolikrát se pro jeden slot v chronologii zkusí jiné schéma, než to vzdáme.
MAX_ATTEMPTS_PER_SLOT = 25

# Jedna instance širokého schématu (např. synkopa) má být dějinná inovace,
# ne opakovaný tah stejného automatu v několika sousedních slotech. Kratší
# interval zejména dovoloval cyklus epenteze/geminace → synkopa, který uměle
# nafukoval jak formy, tak následné mazání.
MIN_SCHEMA_REUSE_YEARS = 500

# Schémata, která ukrajují konce slov — na ně sahá makro-parametr eroze.
CODA_SCHEMAS = ("coda_loss", "syncope")

# Všechna schémata, jejichž běžnou operací je skutečné odstranění segmentu.
# Regulují se zvlášť: délka vývoje a poměr deletivních změn nejsou tatáž věc.
DELETION_SCHEMAS = (
    "syncope",
    "coda_loss",
    "monophthongization",
    "apocope",
    "compensatory_lengthening",
)


@dataclass
class MacroParams:
    """
    Uživatelské makro-parametry generátoru (CEE_master.md 4.4).

    Tohle je ta „black-box" vrstva pro worldbuildera: místo vah schémat se
    nastavuje několik srozumitelných čísel, která se do vah propíšou.
    """

    #: Násobí počet zvukových změn za období. 2.0 = dvakrát bouřlivější vývoj.
    change_rate: float = 1.0

    #: 0.0 až 1.0. Konzervativní jazyk mění méně, i když je rychlost vysoká.
    conservatism: float = 0.0

    #: Násobí váhu schémat ukrajujících konce slov (coda_loss, syncope).
    coda_erosion: float = 1.0

    #: Násobí šanci zákonů, které skutečně mažou segment. Konzervativní
    #: výchozí hodnota chrání slovník před náhodnou erozivní kaskádou.
    deletion_rate: float = 0.4

    #: Rozptyl roku uvnitř slotu. 0 = pravidelný takt, 0.5 = pořádně rozházené.
    timing_jitter: float = 0.35

    @classmethod
    def from_config(cls, *sources: Optional[Dict[str, Any]]) -> "MacroParams":
        """
        Poskládá parametry z několika zdrojů; pozdější přebíjí dřívější.
        Typicky: výchozí hodnoty -> preset -> nastavení uzlu.
        """
        values: Dict[str, Any] = {}
        for source in sources:
            if not source:
                continue
            for field_name in (
                "change_rate", "conservatism", "coda_erosion", "deletion_rate", "timing_jitter"
            ):
                if field_name in source:
                    values[field_name] = float(source[field_name])

        params = cls(**values)
        # Konzervativnost je podíl, mimo 0–1 nedává smysl.
        params.conservatism = max(0.0, min(1.0, params.conservatism))
        params.change_rate = max(0.0, params.change_rate)
        params.coda_erosion = max(0.0, params.coda_erosion)
        params.deletion_rate = max(0.0, params.deletion_rate)
        params.timing_jitter = max(0.0, min(1.0, params.timing_jitter))
        return params

    @property
    def activity(self) -> float:
        """Výsledná míra změny po započtení konzervativnosti."""
        return self.change_rate * (1.0 - self.conservatism)

    def slots_for(self, base_slots: int) -> int:
        """Kolik pokusů o změnu se v daném období vůbec udělá."""
        return max(0, round(base_slots * self.activity))


def _changed_features(rule: Rule) -> Dict[str, str]:
    """Rysy, které pravidlo skutečně překlápí (jsou v terči i v akci a liší se)."""
    return {
        feature: value
        for feature, value in rule.action.items()
        if feature in rule.target and rule.target[feature] != value
    }


def _reverses(previous: Optional[Rule], candidate: Rule) -> bool:
    """
    True, pokud kandidát okamžitě ruší předchozí změnu (např. lenice -> ztráta
    znělosti týchž hlásek). Takové dvojici se má generátor vyhnout — v reálných
    dějinách jazyků je to krajně vzácné a ve výsledku není po změně stopa.
    """
    if previous is None:
        return False
    if previous.action.get("delete") == "+" or candidate.action.get("delete") == "+":
        return False

    changed = _changed_features(previous)
    if not changed:
        return False

    return all(
        candidate.action.get(feature) == previous.target.get(feature)
        and candidate.target.get(feature) == previous.action.get(feature)
        for feature in changed
    )


def _undoes_insertion(previous: Optional[Rule], candidate: Rule) -> bool:
    """
    True, když kandidát maže právě to, co předchozí pravidlo vložilo
    (nebo naopak vkládá to, co se právě smazalo).

    Epenteze následovaná synkopou téže třídy je kmitání, ne dějiny — po dvojici
    nezbude ve slově žádná stopa.
    """
    if previous is None:
        return False

    def _maze(rule: Rule) -> bool:
        return rule.action.get("delete") == "+"

    if previous.insert and _maze(candidate):
        vlozene = previous.insert_features or {}
        return all(vlozene.get(f) == v for f, v in candidate.target.items()
                   if not f.startswith("_"))

    if _maze(previous) and candidate.insert:
        vlozene = candidate.insert_features or {}
        return all(vlozene.get(f) == v for f, v in previous.target.items()
                   if not f.startswith("_"))

    return False


def _is_duplicate(previous: Optional[Rule], candidate: Rule) -> bool:
    """Totožné pravidlo hned po sobě nepřináší nic nového."""
    if previous is None:
        return False
    return (
        previous.target == candidate.target
        and previous.action == candidate.action
        and previous.env_before == candidate.env_before
        and previous.env_after == candidate.env_after
    )


def _reuses_schema_too_soon(history: Optional[List[Rule]], candidate: Rule) -> bool:
    """Zabrání rychlému opakování jedné široké historické inovace."""
    if not candidate.schema_id or candidate.year is None:
        return False
    return any(
        earlier.schema_id == candidate.schema_id
        and earlier.year is not None
        and 0 <= candidate.year - earlier.year < MIN_SCHEMA_REUSE_YEARS
        for earlier in history or []
    )


class SoundChangeGenerator:
    """Vážený generátor zvukových změn na základě šablon, priorů a biomů."""

    def __init__(self, preset: Dict[str, Any], seed: int = 42,
                 macro: Optional[MacroParams] = None,
                 inventory_validator=None,
                 schema_multipliers: Optional[Mapping[str, float]] = None):
        self.preset = preset
        self.random = random.Random(seed)
        self.macro = macro or MacroParams.from_config(preset.get("macro"))
        self.inventory_validator = inventory_validator
        # Kalibrace je jen násobek nad explicitním presetem. Uživatel má
        # nadále poslední slovo: schéma s nulovou vahou zůstane vypnuté.
        self.schema_multipliers = dict(schema_multipliers or {})

    def _weighted_schemas(self, biome: Optional[str]):
        """
        Váhy schémat pro daný biom, upravené makro-parametry.
        Schémata mimo registr se přeskočí.
        """
        schemas = self.preset.get("schemas", {})
        modifiers = self.preset.get("biomes", {}).get(biome, {}).get("modifiers", {})

        choices, weights = [], []
        for schema_id, schema_cfg in schemas.items():
            if schema_id not in SCHEMA_REGISTRY:
                continue

            weight = schema_cfg.get("base_weight", 0) * modifiers.get(schema_id, 1.0)
            weight *= self.schema_multipliers.get(schema_id, 1.0)
            if schema_id in CODA_SCHEMAS:
                weight *= self.macro.coda_erosion
            if schema_id in DELETION_SCHEMAS:
                weight *= self.macro.deletion_rate

            if weight > 0:
                choices.append(SCHEMA_REGISTRY[schema_id])
                weights.append(weight)

        return choices, weights

    def year_for_slot(self, start_year: int, end_year: int, slot: int, total: int) -> int:
        """
        Rok pro daný slot, rozptýlený kolem pravidelného taktu.

        Bez rozptylu padají změny v přesných intervalech, což na časové ose
        vypadá jako strojový takt, ne jako dějiny.
        """
        span = max(1, end_year - start_year)
        step = span / (total + 1)
        center = start_year + step * (slot + 1)

        if self.macro.timing_jitter <= 0:
            return int(round(center))

        wobble = step * self.macro.timing_jitter
        year = center + self.random.uniform(-wobble, wobble)
        return int(round(min(max(year, start_year + 1), end_year)))

    def generate_rules_for_edge(
        self,
        state: State,
        start_year: int,
        end_year: int,
        num_rules: int = 2,
        inventory: Optional[InventoryView] = None,
    ) -> List[Rule]:
        """
        Vygeneruje chronologii pravidel pro hranu mezi `start_year` a `end_year`.

        `inventory` je stav na začátku hrany. Bez něj generátor nemůže ověřit
        obsazenost tříd a schémata by mířila naslepo.
        """
        biome = (state.map or {}).get("biome")
        choices, weights = self._weighted_schemas(biome)

        if not choices:
            return []

        if inventory is None or not inventory:
            warnings.warn(
                f"Uzel '{state.node_id}' nemá inventář, generátor nemůže ověřit "
                f"obsazenost tříd a nevygeneruje žádná pravidla.",
                stacklevel=2,
            )
            return []

        rules: List[Rule] = []
        previous: Optional[Rule] = None
        slots = self.macro.slots_for(num_rules)

        for i in range(slots):
            year = self.year_for_slot(start_year, end_year, i, slots)
            candidate = self.generate_one(state, year, inventory, previous=previous, history=rules)
            if candidate is None:
                continue

            rules.append(candidate)
            previous = candidate
            inventory = inventory.apply(candidate)

        return rules

    def generate_one(
        self,
        state: State,
        year: int,
        inventory: InventoryView,
        previous: Optional[Rule] = None,
        history: Optional[List[Rule]] = None,
        accepts: Optional[Callable[[Rule], bool]] = None,
    ) -> Optional[Rule]:
        """
        Vylosuje jedno pravidlo pro daný rok, nebo vrátí None.

        `accepts` je poslední síto — dostane hotové pravidlo a může ho odmítnout.
        Volající tak může ověřit, že změna na aktuálním lexikonu opravdu něco
        udělá; inventář sám o sobě pozici ve slově nezná, takže třeba fortici
        na začátku slova z něj vyčíst nelze.
        """
        biome = (state.map or {}).get("biome")
        choices, weights = self._weighted_schemas(biome)
        if not choices or not inventory:
            return None

        for _ in range(MAX_ATTEMPTS_PER_SLOT):
            schema = self.random.choices(choices, weights=weights, k=1)[0]
            candidate = schema.generate_rule(inventory, year, rng=self.random)

            if candidate is None:
                continue  # třída je v inventáři prázdná
            candidate.schema_id = schema.name
            if self.inventory_validator is not None:
                report = self.inventory_validator.validate(inventory.apply(candidate))
                if not report.accepted:
                    continue
            if (
                any(_reverses(earlier, candidate) for earlier in (history or []))
                or _undoes_insertion(previous, candidate)
                or _is_duplicate(previous, candidate)
                or _reuses_schema_too_soon(history, candidate)
            ):
                continue
            if accepts is not None and not accepts(candidate):
                continue

            return candidate

        return None
