"""Instituce: písmo, gramotnost a škola (iterace 4, oddíl Instituce; milník M6a).

Psaný kód je zmrazený obraz řeči elity v roce kodifikace. Mluvená řeč se
mění dál, psaný kód stojí, a rozdíl mezi nimi roste (diglosie vzniká sama).
Na mluvčí působí dvěma kanály:

- **Čtení**: gramotní dospělí z něj přejímají slova (učené výpůjčky a
  návraty starých slov). Stavbu řeči čtení nemění.
- **Škola**: děti se učí i z psaného kódu, a to všechno, a tlak `Norm`
  zvýhodní kodifikovanou variantu úměrně školní docházce. Rozdíl mezi
  mluvenou a psanou řečí se pak zmenšuje.

Třetí kanál je **liturgie** (náboženská změna, M6b): věřící slyší a čtou
liturgický kód, často cizí (latina, církevní slovanština, arabština,
sanskrt), a přejímají z něj učená slova, spíš vzácná než základní.

Bez písma, školy a liturgie jsou všechny kanály i tlak nulové.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cee.v2 import contact

if TYPE_CHECKING:
    from cee.v2.world import World

# Váhy vstupu psaného a liturgického kódu jsou data světa (``world.params``:
# ``reading_weight``, ``school_weight``, ``liturgy_weight``).
READING = {"lexical": 1.0}
SCHOOL = {"lexical": 1.0, "process": 0.1, "construction": 1.0, "form": 1.0}


def liturgy_factor(world: World, variable_id: str) -> float:
    variable = world.variables[variable_id]
    if variable.kind != "lexical":
        return 0.0
    # Liturgie přináší hlavně slova víry (kanál ``liturgy``, doména ``religion``)
    # a vzácná slova. Půjčitelnost ze WOLD (``contact.transfer``) se tu nepoužije:
    # podíl vstupu je omezený na 1 a ostrý poměr půjčitelností by ho nasytil.
    factor = 1.0 - world.concept_frequency(variable.key)
    weight = contact.domain_weight(world, "liturgy", variable.key)
    return factor if weight == 1.0 else factor * weight


def reading_factor(world: World, variable_id: str) -> float:
    variable = world.variables[variable_id]
    factor = READING.get(variable.kind, 0.0)
    if variable.kind == "lexical":
        # Čtení přináší hlavně učená slova; častá slova šetří podle
        # ``Parameters.reading_core_resistance`` (1 = jako liturgie) a doména
        # ``learned`` má v kanálu ``reading`` vyšší váhu.
        factor *= 1.0 - world.params.reading_core_resistance * world.concept_frequency(variable.key)
        weight = contact.domain_weight(world, "reading", variable.key)
        if weight != 1.0:
            factor *= weight
    return factor


def school_factor(world: World, variable_id: str) -> float:
    variable = world.variables[variable_id]
    factor = SCHOOL.get(variable.kind, 0.0)
    if variable.kind == "lexical":
        weight = contact.domain_weight(world, "school", variable.key)
        if weight != 1.0:
            factor *= weight
    return factor


def standard_of(world: World, group_id: str) -> str | None:
    """Psaný kód, který skupina zná, je-li ve světě."""
    standard = world.groups[group_id].standard
    return standard if standard in world.groups else None
