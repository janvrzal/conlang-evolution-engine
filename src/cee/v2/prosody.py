"""Prozodie v běžící simulaci (krok D2).

Sleduje prozodické proměnné skupin:
- ``prosody:stress_rule``: pravidlo pozice přízvuku (WALS 14A)
- ``prosody:stress_strength``: síla přízvuku (weak / strong, slabičně vs. přízvukově časované)

Změna dominantní varianty aktualizuje vlastnosti kódu a zneplatní keše
tvarů i hodnocení procesů.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

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


def restructure(world: World, group_id: str, tick: int, history: History, year: float) -> None:
    code = world.groups[group_id].main_code
    rule_var = stress_rule_variable_id()
    if rule_var in world.variables:
        rule_found = world.dominant(group_id, rule_var)
        if rule_found is not None:
            var_id, share = rule_found
            if share >= 0.5:
                new_rule = cast(StressRule, world.variants[var_id].payload["rule"])
                if new_rule != code.stress_rule:
                    old_rule = code.stress_rule
                    code.stress_rule = new_rule
                    code.phonology.version += 1
                    code.phonology.cache.clear()
                    code.forms.token = next_token()
                    history.record(
                        "stress_rule_changed", tick, year,
                        group=group_id, old=old_rule, new=new_rule
                    )

    strength_var = stress_strength_variable_id()
    if strength_var in world.variables:
        strength_found = world.dominant(group_id, strength_var)
        if strength_found is not None:
            var_id, share = strength_found
            if share >= 0.5:
                new_strength = cast(Literal["weak", "strong"], world.variants[var_id].payload["strength"])
                if new_strength != code.stress_strength:
                    old_strength = code.stress_strength
                    code.stress_strength = new_strength
                    history.record(
                        "stress_strength_changed", tick, year,
                        group=group_id, old=old_strength, new=new_strength
                    )
