"""Prozodie v běžící simulaci (krok D2).

Sleduje prozodické proměnné skupin:
- ``prosody:stress_rule``: pravidlo pozice přízvuku (WALS 14A)
- ``prosody:stress_strength``: síla přízvuku (weak / strong, slabičně vs. přízvukově časované)

Změna dominantní varianty aktualizuje vlastnosti kódu a zneplatní keše
tvarů i hodnocení procesů.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal, cast

import numpy as np

from cee.v2 import phases
from cee.v2.history import History
from cee.v2.language.lexicon import next_token
from cee.v2.language.processes import StressRule
from cee.v2.repertoire import Origin, Variable, Variant
from cee.v2.rng import stable_id

if TYPE_CHECKING:
    from cee.v2.world import World

STRESS_RULES: tuple[StressRule, ...] = (
    "initial", "second", "antepenult", "penult", "final"
)
STRESS_STRENGTHS: tuple[Literal["weak", "strong"], ...] = ("weak", "strong")


def stress_rule_variable_id() -> str:
    return Variable("prosody", "stress_rule").id


def stress_strength_variable_id() -> str:
    return Variable("prosody", "stress_strength").id


def register_stress_rule(
    world: World, rule: StressRule, origin: Origin
) -> tuple[str, Variant]:
    var_id = stress_rule_variable_id()
    if var_id not in world.variables:
        world.variables[var_id] = Variable("prosody", "stress_rule", default=None)
    variant_id = stable_id("variant", "prosody", f"stress_rule:{rule}")
    if variant_id not in world.variants:
        world.variants[variant_id] = Variant(
            variant_id, var_id, {"rule": rule}, origin
        )
    return var_id, world.variants[variant_id]


def register_stress_strength(
    world: World, strength: Literal["weak", "strong"], origin: Origin
) -> tuple[str, Variant]:
    var_id = stress_strength_variable_id()
    if var_id not in world.variables:
        world.variables[var_id] = Variable("prosody", "stress_strength", default=None)
    variant_id = stable_id("variant", "prosody", f"stress_strength:{strength}")
    if variant_id not in world.variants:
        world.variants[variant_id] = Variant(
            variant_id, var_id, {"strength": strength}, origin
        )
    return var_id, world.variants[variant_id]


def dominant_rule(world: World, group_id: str) -> StressRule:
    found = world.dominant(group_id, stress_rule_variable_id())
    if found is None:
        return cast(StressRule, world.groups[group_id].main_code.stress_rule)
    dominant_id, _ = found
    return cast(StressRule, world.variants[dominant_id].payload["rule"])


def dominant_strength(world: World, group_id: str) -> Literal["weak", "strong"]:
    found = world.dominant(group_id, stress_strength_variable_id())
    if found is None:
        return cast(Literal["weak", "strong"], getattr(world.groups[group_id].main_code, "stress_strength", "weak"))
    dominant_id, _ = found
    return cast(Literal["weak", "strong"], world.variants[dominant_id].payload["strength"])


#: Nové pravidlo přízvuku a nová síla přízvuku skupiny (``None`` = beze změny).
StressPlan = tuple[StressRule | None, Literal["weak", "strong"] | None]


def _updates(
    world: World, group_ids: Sequence[str], variable_id: str, key: str, values: Sequence[Any], current: str
) -> dict[str, Any]:
    """Skupiny, kde převládající hodnota prozodické proměnné mění vlastnost kódu, a nová hodnota."""
    if variable_id not in world.variables:
        return {}
    shares, dominant, held = [], [], []
    for group_id in group_ids:
        found = world.dominant(group_id, variable_id)
        if found is None:
            shares.append(0.0)
            dominant.append(-1)
        else:
            shares.append(found[1])
            dominant.append(values.index(world.variants[found[0]].payload[key]))
        now = getattr(world.groups[group_id].main_code, current, None)
        held.append(values.index(now) if now in values else -2)
    changed = phases.stress_updates(
        np.array(shares, dtype=np.float64), np.array(dominant, dtype=np.intp), np.array(held, dtype=np.intp)
    )
    return {group_id: values[dominant[index]] for index, group_id in enumerate(group_ids) if changed[index]}


def plan(world: World, group_ids: Sequence[str]) -> dict[str, StressPlan]:
    """Skupiny, kde se mění pravidlo nebo síla přízvuku (ostatní ve výsledku chybí).

    Čte jen rozdělení prozodických proměnných a dnešní vlastnosti kódu, takže
    plán platí pro celý krok bez ohledu na pořadí skupin.
    """
    rules = _updates(world, group_ids, stress_rule_variable_id(), "rule", STRESS_RULES, "stress_rule")
    strengths = _updates(world, group_ids, stress_strength_variable_id(), "strength", STRESS_STRENGTHS, "stress_strength")
    return {
        group_id: (rules.get(group_id), strengths.get(group_id))
        for group_id in group_ids if group_id in rules or group_id in strengths
    }


def restructure(
    world: World, group_id: str, tick: int, history: History, year: float, planned: StressPlan | None = None
) -> None:
    """Převládající pravidlo a síla přízvuku se zapíšou do kódu.

    ``planned`` (:func:`plan`) smí volající spočítat předem pro všechny
    skupiny; bez něj se spočte jen pro tuto skupinu.
    """
    code = world.groups[group_id].main_code
    new_rule, new_strength = plan(world, [group_id]).get(group_id, (None, None)) if planned is None else planned
    if new_rule is not None:
        old_rule = code.stress_rule
        code.stress_rule = new_rule
        code.phonology.version += 1
        code.phonology.cache.clear()
        code.forms.token = next_token()
        history.record(
            "stress_rule_changed", tick, year,
            group=group_id, old=old_rule, new=new_rule
        )
    if new_strength is not None:
        old_strength = code.stress_strength
        code.stress_strength = new_strength
        history.record(
            "stress_strength_changed", tick, year,
            group=group_id, old=old_strength, new=new_strength
        )
