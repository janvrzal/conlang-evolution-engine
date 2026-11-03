"""API změn světa: jediná cesta, kterou události, státy a pozadí dějin mění svět (A8).

Události (``events``), státy (``polity``) a pozadí dějin (``background``) jsou
vzácné a nejsou horké, takže zůstanou nejdéle v Pythonu. Až stav světa přejde do
Rustu, smí je měnit jen přes malou sadu **operací** s jasným účinkem, které Rust
umí přijmout. Tento modul je ta sada: každá změna světa v těchto třech modulech
je volání metody :class:`Edits`.

Operace
-------
Operace je jméno a pojmenované argumenty z čísel, řetězců, ``True``/``False``
a ``None`` (seznam čísel či řetězců jen pro polohu a oblasti státu). Žádné
objekty modelu. Stejná funkce operaci provede při běhu i při přehrání deníku,
takže deník nemůže popsat něco jiného, než co se stalo.

==================  =========================================================
operace             účinek
==================  =========================================================
add_territory       nové území (id, úroveň, rodič, poloha, rok zjemnění);
                    zařadí se k potomkům rodiče
add_group           nová skupina s jedním kódem (``codes="main"``) nebo všemi
                    kódy (``"all"``) skupiny ``code_from``, odvozenými
                    ``branch()``. Nejdřív se živé proměnné dárce zapíšou do
                    jeho repertoáru (``World.materialize``)
remove_group        skupina zmizí, s ní všechny vazby a obchodní podíly
set_group           jedno skalární pole skupiny (populace, prestiž, gramotnost,
                    škola, liturgie, příznak elity, ...; viz ``GROUP_FIELDS``)
set_code            ``acquisition``, ``l1_source`` a ``l2_share`` hlavního
                    kódu skupiny
fix_code            hlavní kód skupiny dostane v každé nezafixované proměnné
                    jen dominantní variantu (zmrazení psaného kódu)
connect             oboustranná vazba (síla se ořízne na 0 až 1)
set_link            jednosměrná vazba bez ořezu
drop_link           jednosměrná vazba zanikne (nic, když nebyla)
set_trade           obchodní podíl vazby dvojice (``None`` = zrušit)
set_border_factor   násobek oslabení vazby hranicí (``None`` = bez hranice)
set_base_prestige   základní prestiž skupiny před vlivem států (``None`` = smazat)
set_prestige_mirror skupina přebírá prestiž jiné (``None`` = zrušit)
add_state           nový stát (``Polity``) ve ``World.states``
set_state           ``regions``, ``policy`` nebo ``border`` státu
set_state_link      vazba státu na sídlo skupiny (``Polity.links``)
remove_state        stát zanikne
set_standard        spisovný jazyk státu či regionu (``None`` = smazat)
==================  =========================================================

Operace, která nic nezměnila (zrušení neexistující vazby, nastavení stejné
hodnoty), se nezapíše.

Pořadí a determinismus
----------------------
Operace se provádějí v pořadí volání. Tam, kde výsledek závisí na pořadí
(vkládání do slovníků, číslování v registru, pořadí vazeb), je pořadí dané
volajícím a tedy kódem události; ``Edits`` nic neřadí ani nepřeskládává.
Složené změny (gravitační vazby, oslabení hranicí) se rozloží na operace
jednotlivě, včetně vypočtených hodnot, takže Rust nepotřebuje znát vzorec.

Deník změn
----------
Každá provedená operace se zapíše do ``World.edit_log`` jako :class:`Edit`
(tik, operace, argumenty). Deník patří světu, kopíruje se s ním
(checkpointy, ``copy.deepcopy``, pickle) a jde uložit jako řádky JSON
(:func:`journal_lines`, :func:`load_journal`). Přehrání do kopie světa
(:class:`cee.v2.events.ReplayEdits`) provede stejné operace ve stejných
ticích, a dá tedy stejný stav a stejný deník jako běh s událostmi.

Co z toho převezme Rust
-----------------------
Operace nad skupinami, vazbami, obchodem, hranicemi, prestiží, státy
a spisovnými jazyky přejdou do Rustu jako zápisy do sloupců a CSR vazeb světa
(A4). Rozhodnutí, *kdy a jaké* operace volat (události, politika států, pozadí
dějin), zůstává v Pythonu. ``add_group`` a ``fix_code`` jsou složené: předají
Rustu dárce kódu (kopie repertoáru, tvarů a fonologického stavu) a pravidlo
„dominantní varianta, shodu rozhoduje první podle ID“.
"""

from __future__ import annotations

import json
import numbers
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Iterable, Iterator, Sequence

from cee.v2.repertoire import Distribution
from cee.v2.world import (
    TERRITORY_LEVELS,
    Link,
    LinkKind,
    SpeechGroup,
    Territory,
    TerritoryLevel,
    World,
    gravity_pairs,
)

if TYPE_CHECKING:
    from cee.v2.polity import Polity

#: Skalární pole skupiny, která operace smějí nastavit, a jejich druh hodnoty.
GROUP_FIELDS: dict[str, str] = {
    "population": "int",
    "generation_years": "float",
    "prestige": "float",
    "openness": "float",
    "literacy": "float",
    "schooling": "float",
    "community": "text?",
    "immigration": "float",
    "written": "bool",
    "standard": "text?",
    "liturgy": "text?",
    "devotion": "float",
    "loyalty": "float",
    "domain": "domain",
    "home_pull": "float",
    "preserved": "bool",
    "revival": "float",
    "elite": "bool",
}

#: Pole kódu, která smí ``set_code`` nastavit.
CODE_FIELDS = ("acquisition", "l1_source", "l2_share")

#: Pole státu, která smí ``set_state`` nastavit.
STATE_FIELDS = ("regions", "policy", "border")


@dataclass(frozen=True, slots=True)
class Edit:
    """Jedna zapsaná operace: tik, jméno operace a její argumenty."""

    tick: int
    op: str
    args: dict[str, Any]

    def line(self) -> str:
        return json.dumps({"tick": self.tick, "op": self.op, "args": self.args}, ensure_ascii=False)

    @classmethod
    def from_line(cls, line: str) -> Edit:
        found = json.loads(line)
        return cls(int(found["tick"]), str(found["op"]), dict(found["args"]))


def journal_lines(world: World) -> list[str]:
    """Deník změn světa jako řádky JSON (jedna operace na řádek)."""
    return [edit.line() for edit in world.edit_log]


def load_journal(lines: Iterable[str]) -> list[Edit]:
    return [Edit.from_line(line) for line in lines if line.strip()]


def by_tick(journal: Iterable[Edit]) -> Iterator[tuple[int, tuple[Edit, ...]]]:
    """Deník rozdělený po tících v pořadí zápisu (tik se v deníku nevrací zpět)."""
    current: list[Edit] = []
    for edit in journal:
        if current and edit.tick != current[0].tick:
            yield current[0].tick, tuple(current)
            current = []
        current.append(edit)
    if current:
        yield current[0].tick, tuple(current)


def _plain(value: Any) -> Any:
    """Hodnota argumentu v čisté podobě (čísla numpy → Python, seznamy), jiné typy ne."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    raise TypeError(f"Argument operace musí být číslo, řetězec, bool nebo None, ne {type(value).__name__}.")


def _check_value(name: str, kind: str, value: Any) -> None:
    ok = {
        "int": isinstance(value, int) and not isinstance(value, bool),
        "float": isinstance(value, (int, float)) and not isinstance(value, bool),
        "bool": isinstance(value, bool),
        "text?": value is None or isinstance(value, str),
        "domain": value in ("home", "public"),
    }[kind]
    if not ok:
        raise TypeError(f"Pole skupiny '{name}' nemůže mít hodnotu {value!r}.")


def _check_fields(fields: dict[str, Any]) -> None:
    for name, value in fields.items():
        if name not in GROUP_FIELDS:
            raise KeyError(f"Pole skupiny '{name}' operace nemění.")
        _check_value(name, GROUP_FIELDS[name], value)


def _same(old: Any, new: Any) -> bool:
    return old == new and type(old) is type(new)


# --- operace: každá je funkce (svět, argumenty) a vrací False, když nic nezměnila ---


def _add_territory(
    world: World, territory: str, level: str, parent: str | None = None,
    position: Sequence[float] | None = None, refined_from_year: float | None = None,
) -> None:
    if level not in TERRITORY_LEVELS:
        raise ValueError(f"Neznámá úroveň území '{level}'.")
    world.add_territory(Territory(
        territory, level, parent,  # type: ignore[arg-type]
        position=None if position is None else (position[0], position[1]),
        refined_from_year=refined_from_year,
    ))


def _add_group(
    world: World, group: str, territory: str, population: int, code_from: str, codes: str = "main",
    **fields: Any,
) -> None:
    _check_fields(fields)
    if codes not in ("main", "all"):
        raise ValueError(f"Kódy dárce: 'main' nebo 'all', ne '{codes}'.")
    donor = world.groups[code_from]
    world.materialize(code_from)
    chosen = donor.codes if codes == "all" else donor.codes[:1]
    world.add_group(SpeechGroup(
        id=group, territory=territory, population=population, codes=[code.branch() for code in chosen],
        **fields,
    ))


def _remove_group(world: World, group: str) -> None:
    world.remove_group(group)


def _set_group(world: World, group: str, field: str, value: Any) -> bool:
    _check_fields({field: value})
    found = world.groups[group]
    if _same(getattr(found, field), value):
        return False
    setattr(found, field, value)
    return True


def _set_code(world: World, group: str, **changes: Any) -> bool:
    code = world.groups[group].main_code
    changed = False
    for name, value in changes.items():
        if name not in CODE_FIELDS:
            raise KeyError(f"Pole kódu '{name}' operace nemění.")
        if name == "acquisition" and value not in ("L1", "L2"):
            raise ValueError(f"Způsob osvojení: 'L1' nebo 'L2', ne {value!r}.")
        if not _same(getattr(code, name), value):
            setattr(code, name, value)
            changed = True
    return changed


def _fix_code(world: World, group: str) -> None:
    code = world.groups[group].main_code
    for variable_id in sorted(world.variables):
        distribution = code.repertoire.get(variable_id)
        if distribution is not None and not distribution.is_fixed:
            code.repertoire.set(variable_id, Distribution.fixed(distribution.dominant()[0]))


def _connect(world: World, first: str, second: str, strength: float, kind: str = "weak") -> None:
    world.connect(first, second, strength, kind)  # type: ignore[arg-type]


def _check_groups(world: World, *group_ids: str) -> None:
    for group_id in group_ids:
        if group_id not in world.groups:
            raise ValueError(f"Skupina '{group_id}' neexistuje.")


def _set_link(world: World, source: str, target: str, strength: float, kind: str = "weak") -> None:
    _check_groups(world, source, target)
    world.links[(source, target)] = Link(source, target, strength, kind)  # type: ignore[arg-type]


def _drop_link(world: World, source: str, target: str) -> bool:
    return world.links.pop((source, target), None) is not None


def _set_trade(world: World, first: str, second: str, value: float | None) -> bool:
    key = (first, second) if first < second else (second, first)
    if value is None:
        return world.trade.pop(key, None) is not None
    world.trade[key] = value
    return True


def _set_border_factor(world: World, source: str, target: str, factor: float | None) -> bool:
    if factor is None:
        return world.border_factors.pop((source, target), None) is not None
    world.border_factors[(source, target)] = factor
    return True


def _set_base_prestige(world: World, group: str, value: float | None) -> bool:
    if value is None:
        return world.base_prestige.pop(group, None) is not None
    world.base_prestige[group] = value
    return True


def _set_prestige_mirror(world: World, group: str, model: str | None) -> bool:
    if model is None:
        return world.prestige_mirror.pop(group, None) is not None
    world.prestige_mirror[group] = model
    return True


def _add_state(
    world: World, state: str, regions: Sequence[str], capital: str, seat: str, language: str,
    centralization: str, policy: str, border: str, name: str | None = None,
) -> None:
    from cee.v2.polity import Polity

    if state in world.states:
        raise ValueError(f"Stát '{state}' už existuje.")
    world.states[state] = Polity(
        state, tuple(regions), capital, seat, language, centralization, policy, border, name=name,
    )


def _state(world: World, state: str) -> Polity:
    found: Polity | None = world.states.get(state)
    if found is None:
        raise KeyError(state)
    return found


def _set_state(world: World, state: str, field: str, value: Any) -> bool:
    if field not in STATE_FIELDS:
        raise KeyError(f"Pole státu '{field}' operace nemění.")
    found = _state(world, state)
    new = tuple(value) if field == "regions" else value
    if getattr(found, field) == new:
        return False
    setattr(found, field, new)
    return True


def _set_state_link(world: World, state: str, group: str, strength: float | None) -> bool:
    links = _state(world, state).links
    if strength is None:
        return links.pop(group, None) is not None
    links[group] = strength
    return True


def _remove_state(world: World, state: str) -> None:
    _state(world, state)
    del world.states[state]


def _set_standard(world: World, of: str, written: str | None) -> bool:
    if written is None:
        return world.standards.pop(of, None) is not None
    world.standards[of] = written
    return True


OPERATIONS: dict[str, Callable[..., bool | None]] = {
    "add_territory": _add_territory,
    "add_group": _add_group,
    "remove_group": _remove_group,
    "set_group": _set_group,
    "set_code": _set_code,
    "fix_code": _fix_code,
    "connect": _connect,
    "set_link": _set_link,
    "drop_link": _drop_link,
    "set_trade": _set_trade,
    "set_border_factor": _set_border_factor,
    "set_base_prestige": _set_base_prestige,
    "set_prestige_mirror": _set_prestige_mirror,
    "add_state": _add_state,
    "set_state": _set_state,
    "set_state_link": _set_state_link,
    "remove_state": _remove_state,
    "set_standard": _set_standard,
}


class Edits:
    """Změny světa v jednom ticku: provede operaci a zapíše ji do deníku světa."""

    __slots__ = ("world", "tick")

    def __init__(self, world: World, tick: int) -> None:
        self.world = world
        self.tick = tick

    def do(self, op: str, **args: Any) -> bool:
        """Provede operaci podle jména a zapíše ji; vrací, zda něco změnila."""
        plain = {name: _plain(value) for name, value in args.items()}
        changed = OPERATIONS[op](self.world, **plain)
        if changed is False:
            return False
        self.world.edit_log.append(Edit(self.tick, op, plain))
        return True

    def replay(self, edit: Edit) -> bool:
        """Přehraje zapsanou operaci; musí patřit do tohoto ticku."""
        if edit.tick != self.tick:
            raise ValueError(f"Změna z ticku {edit.tick} se nedá přehrát v ticku {self.tick}.")
        return self.do(edit.op, **edit.args)

    # --- území a skupiny ---

    def add_territory(
        self, territory: str, level: TerritoryLevel, parent: str | None = None,
        position: tuple[float, float] | None = None, refined_from_year: float | None = None,
    ) -> None:
        self.do("add_territory", territory=territory, level=level, parent=parent, position=position,
                refined_from_year=refined_from_year)

    def add_group(
        self, group: str, territory: str, population: int, code_from: str, *, codes: str = "main",
        **fields: Any,
    ) -> None:
        """Nová skupina s kódem (kódy) odvozeným z ``code_from``; ``fields`` jsou pole z ``GROUP_FIELDS``."""
        self.do("add_group", group=group, territory=territory, population=population, code_from=code_from,
                codes=codes, **fields)

    def remove_group(self, group: str) -> None:
        self.do("remove_group", group=group)

    def set_group(self, group: str, field: str, value: Any) -> bool:
        return self.do("set_group", group=group, field=field, value=value)

    def set_code(self, group: str, **changes: Any) -> bool:
        return self.do("set_code", group=group, **changes)

    def fix_code(self, group: str) -> None:
        self.do("fix_code", group=group)

    # --- vazby a obchod ---

    def connect(self, first: str, second: str, strength: float, kind: LinkKind = "weak") -> None:
        self.do("connect", first=first, second=second, strength=strength, kind=kind)

    def connect_gravity(
        self, groups: Sequence[str], *, max_distance: float | None = None, scale: float = 1.0,
        reference_population: float = 1_000.0, reference_distance: float = 10.0,
    ) -> int:
        """Gravitační vazby mezi skupinami (Trudgill); zapíše se každá vazba s vypočtenou silou."""
        pairs = gravity_pairs(
            self.world, scale=scale, reference_population=reference_population,
            reference_distance=reference_distance, max_distance=max_distance, groups=groups,
        )
        for first, second, strength in pairs:
            self.connect(first, second, strength)
        return len(pairs)

    def set_link(self, source: str, target: str, strength: float, kind: LinkKind = "weak") -> None:
        self.do("set_link", source=source, target=target, strength=strength, kind=kind)

    def drop_link(self, source: str, target: str) -> bool:
        return self.do("drop_link", source=source, target=target)

    def set_trade(self, first: str, second: str, value: float | None) -> bool:
        key = (first, second) if first < second else (second, first)
        return self.do("set_trade", first=key[0], second=key[1], value=value)

    def set_border_factor(self, source: str, target: str, factor: float | None) -> bool:
        return self.do("set_border_factor", source=source, target=target, factor=factor)

    # --- prestiž ---

    def set_base_prestige(self, group: str, value: float | None) -> bool:
        return self.do("set_base_prestige", group=group, value=value)

    def set_prestige_mirror(self, group: str, model: str | None) -> bool:
        return self.do("set_prestige_mirror", group=group, model=model)

    # --- státy a spisovné jazyky ---

    def add_state(
        self, state: str, regions: Sequence[str], capital: str, seat: str, language: str,
        centralization: str, policy: str, border: str, name: str | None = None,
    ) -> None:
        self.do("add_state", state=state, regions=list(regions), capital=capital, seat=seat,
                language=language, centralization=centralization, policy=policy, border=border, name=name)

    def set_state(self, state: str, field: str, value: Any) -> bool:
        return self.do("set_state", state=state, field=field, value=value)

    def set_state_link(self, state: str, group: str, strength: float | None) -> bool:
        return self.do("set_state_link", state=state, group=group, strength=strength)

    def remove_state(self, state: str) -> None:
        self.do("remove_state", state=state)

    def set_standard(self, of: str, written: str | None) -> bool:
        return self.do("set_standard", of=of, written=written)
