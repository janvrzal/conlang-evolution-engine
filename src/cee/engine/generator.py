"""
Generátor zvukových změn (CEE_master.md 4.4).

Skládá chronologii pravidel ze tří vrstev:

1. **Inventář schémat** — `schemas.SCHEMA_REGISTRY`.
2. **Priory** — váhy z presetu, modifikované biomem uzlu.
3. **Filtr věrohodnosti** — prostředí musí být v aktuálním inventáři neprázdné
   (řeší `Schema.generate_rule`) a sekvence nesmí obsahovat okamžité zvrácení
   předchozí změny (řeší `_reverses` níže).

Inventář se mezi pravidly průběžně aktualizuje, takže pozdější změna vidí to,
co jí předchozí připravila.
"""
import random
import warnings
from typing import Any, Callable, Dict, List, Optional

from cee.core.models import State
from cee.engine.inventory import InventoryView
from cee.engine.rules import Rule
from cee.engine.schemas import SCHEMA_REGISTRY

# Kolikrát se pro jeden slot v chronologii zkusí jiné schéma, než to vzdáme.
MAX_ATTEMPTS_PER_SLOT = 24


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


class SoundChangeGenerator:
    """Vážený generátor zvukových změn na základě šablon, priorů a biomů."""

    def __init__(self, preset: Dict[str, Any], seed: int = 42):
        self.preset = preset
        self.random = random.Random(seed)

    def _weighted_schemas(self, biome: Optional[str]):
        """Váhy schémat pro daný biom; schémata mimo registr se přeskočí."""
        schemas = self.preset.get("schemas", {})
        modifiers = self.preset.get("biomes", {}).get(biome, {}).get("modifiers", {})

        choices, weights = [], []
        for schema_id, schema_cfg in schemas.items():
            if schema_id not in SCHEMA_REGISTRY:
                continue
            weight = schema_cfg.get("base_weight", 0) * modifiers.get(schema_id, 1.0)
            if weight > 0:
                choices.append(SCHEMA_REGISTRY[schema_id])
                weights.append(weight)

        return choices, weights

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
        time_step = max(1, (end_year - start_year) // (num_rules + 1))

        for i in range(num_rules):
            year = start_year + time_step * (i + 1)
            candidate = self.generate_one(state, year, inventory, previous=previous)
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
            if _reverses(previous, candidate) or _is_duplicate(previous, candidate):
                continue
            if accepts is not None and not accepts(candidate):
                continue

            return candidate

        return None
