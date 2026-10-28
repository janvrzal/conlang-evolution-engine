"""Instituce: písmo, gramotnost a škola (iterace 4, oddíl Instituce; milník M6a).

Psaný kód je zmrazený obraz řeči elity v roce kodifikace. Mluvená řeč se
mění dál, psaný kód stojí, a rozdíl mezi nimi roste (diglosie vzniká sama).
Na mluvčí působí dvěma kanály:

- **Čtení**: gramotní dospělí z něj přejímají slova (učené výpůjčky a
  návraty starých slov). Stavbu řeči čtení nemění.
- **Škola**: děti se učí i z psaného kódu, a to všechno, a tlak `Norm`
  zvýhodní kodifikovanou variantu úměrně školní docházce. Rozdíl mezi
  mluvenou a psanou řečí se pak zmenšuje.

Bez písma a školy jsou oba kanály i tlak nulové.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cee.v2.world import World

#: Jak velkou část vstupu gramotného mluvčího tvoří psaný kód (jen slova).
READING_WEIGHT = 0.1
READING = {"lexical": 1.0}
#: Jak velkou část vstupu dětí při plné školní docházce tvoří psaný kód.
#: Škola učí slova, tvary a konstrukce; výslovnost si děti nesou z domova a
#: podle písma se mění jen výjimečně (výslovnost podle pravopisu).
SCHOOL_WEIGHT = 0.3
SCHOOL = {"lexical": 1.0, "process": 0.1, "construction": 1.0, "form": 1.0}


def reading_factor(world: World, variable_id: str) -> float:
    return READING.get(world.variables[variable_id].kind, 0.0)


def school_factor(world: World, variable_id: str) -> float:
    return SCHOOL.get(world.variables[variable_id].kind, 0.0)


def standard_of(world: World, group_id: str) -> str | None:
    """Psaný kód, který skupina zná, je-li ve světě."""
    standard = world.groups[group_id].standard
    return standard if standard in world.groups else None
