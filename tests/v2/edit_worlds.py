"""Světy s událostmi pro test API změn světa (``cee.v2.edits``) a otisk stavu světa.

Světy pokrývají všechny druhy událostí z ``events``, ``polity`` a ``background``.
Otisk stavu (:func:`fingerprint`) je hash všeho, co události mění: území,
skupiny s kódy a rozděleními, vazby, obchod, státy, spisovné jazyky, hranice
a prestiž, včetně pořadí vložení do slovníků.
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Callable

from cee.v2.background import EliteAssimilation, ForeignElite, TradeShift, generate
from cee.v2.events import (
    Border,
    Codification,
    Conquest,
    Contact,
    Epidemic,
    LanguageShift,
    Migration,
    Printing,
    RefineTerritory,
    ReligiousChange,
    Schooling,
    SettlementSpec,
    StateCollapse,
    War,
    WorldEvent,
)
from cee.v2.polity import (
    Annexation,
    BorderPolicy,
    Collapse,
    Identity,
    Immigration,
    LanguagePolicy,
    LinguaFranca,
    Preserve,
    Revival,
    Schools,
    Secession,
    Standard,
    State,
)
from cee.v2.scenarios import (
    Language,
    Place,
    ProtoLanguage,
    Region,
    conquest,
    contact_world,
    language_shift,
    region_world,
    village_grid,
)
from cee.v2.world import Code, SpeechGroup, Territory, World


def fingerprint(world: World) -> str:
    """Otisk stavu světa, který mění události (včetně pořadí vložení)."""
    lines: list[object] = [("order", list(world.groups), list(world.links), list(world.trade),
                            list(world.states), list(world.standards), list(world.border_factors),
                            list(world.base_prestige), list(world.prestige_mirror))]
    for territory_id in sorted(world.territories):
        territory = world.territories[territory_id]
        lines.append(("territory", dataclasses.astuple(territory)))
    for group_id in world.group_ids():
        group = world.groups[group_id]
        scalars = [(field.name, getattr(group, field.name)) for field in dataclasses.fields(group)
                   if field.name != "codes"]
        codes = [(code.id, code.language, code.acquisition, code.l1_source, code.l2_share, code.usage_share,
                  code.stress_rule, code.stress_strength) for code in group.codes]
        lines.append(("group", group_id, scalars, codes))
        for variable_id in sorted(world.variables):
            distribution = world.distribution(group_id, variable_id)
            if distribution is not None:
                lines.append(("dist", group_id, variable_id, distribution.variants,
                              distribution.freqs.tolist(), distribution.previous.tolist()))
    for key, link in world.links.items():
        lines.append(("link", key, dataclasses.astuple(link)))
    lines.append(("trade", sorted(world.trade.items())))
    for state_id in sorted(world.states):
        lines.append(("state", dataclasses.astuple(world.states[state_id])))
    lines.append(("standards", sorted(world.standards.items())))
    lines.append(("border", sorted(world.border_factors.items())))
    lines.append(("prestige", sorted(world.base_prestige.items()), sorted(world.prestige_mirror.items())))
    return hashlib.sha256(repr(lines).encode("utf-8")).hexdigest()


def _regions(villages: int = 2) -> tuple[Region, ...]:
    return tuple(
        Region(f"r{i}", (60.0 * (i % 3), 60.0 * (i // 3)), language="b" if i >= 3 else "a", villages=villages,
               neighbours=tuple(f"r{j}" for j in range(6)
                                if j != i and abs(j % 3 - i % 3) + abs(j // 3 - i // 3) == 1))
        for i in range(6)
    )


def trade_elite() -> tuple[World, list[WorldEvent], float]:
    """Pozadí dějin (mor, přesídlení, obchod, prestiž, cizí elita) a ručně zadaná elita a obchod."""
    regions = _regions()
    world = region_world(regions, seed=3, languages=(ProtoLanguage("a"), ProtoLanguage("b")), semantics=True)
    events = list(generate([(r.id, r.neighbours, r.language) for r in regions], start=0.0, end=600.0,
                           level_name="turbulent", seed=3))
    events += [ForeignElite(50.0, "r3", "r0"), TradeShift(60.0, ("r1", "r4"), 2.0),
               TradeShift(300.0, ("r1", "r4"), 0.5), EliteAssimilation(300.0, "r3", "r0")]
    return world, events, 600.0


def church_school() -> tuple[World, list[WorldEvent], float]:
    """Kodifikace, liturgie, vlastní kodifikace a škola (přímá i diglosní s tiskem)."""
    world = contact_world([
        Language("v", tuple(Place(f"v{i}", (i * 10.0, 0.0), population=600) for i in range(4))),
        Language("r", (Place("r0", (500.0, 0.0), population=5000, prestige=1.0),),
                 consonants=("t", "k", "s", "n", "m", "l", "r", "f", "x", "kʷ", "j", "d")),
    ], seed=2)
    villages = tuple(f"v{i}" for i in range(4))
    events: list[WorldEvent] = [
        Codification(100.0, "r0", ("r0",), 0.1), ReligiousChange(150.0, "written:r0", villages, 0.3, 0.2),
        Codification(200.0, "v1", villages, 0.2), Schooling(400.0, villages[:2], 0.5, 0.5),
        Schooling(450.0, villages[2:], 0.5, 0.5, diglossic=True), Printing(500.0, "written:v1", 0.4),
    ]
    return world, events, 700.0


def shift_trade() -> tuple[World, list[WorldEvent], float]:
    """Přesun jazyka (domácí i veřejný), obchodní a obecný kontakt."""
    world, events = language_shift(2, start=300.0)
    events += [Contact(200.0, (("x0", "y2"),), 0.4, trade=True), Contact(250.0, (("x0", "y2"),), 0.3),
               Contact(260.0, (("x1", "y1"),), 0.4, trade=True),
               LanguageShift(270.0, "y1", "x0", initial_share=0.2, domain="public")]
    return world, events, 800.0


def conquest_shift() -> tuple[World, list[WorldEvent], float]:
    """Dobytí s cizí elitou, která později přejde na jazyk poddaných."""
    world, events = conquest(1, year=200.0)
    return world, events, 600.0


def society() -> tuple[World, list[WorldEvent], float]:
    """Hranice, válka, mor, kolaps, migrace (nové sídlo i existující), dobytí, tisk, škola."""
    world = village_grid(4, 2, seed=1, link_reach=4.0)
    events: list[WorldEvent] = [
        Border(100.0, ("v00-00", "v01-00"), ("v00-03", "v01-03"), 0.3),
        War(150.0, ("v00-00", "v01-00"), ("v00-02", "v01-02"), 0.5, 0.2),
        Epidemic(200.0, ("v00-03",), 0.4),
        Migration(250.0, (("v00-00", 0.2), ("v01-01", 0.1)), "colony", position=(15.0, 25.0), reach=40.0),
        Migration(300.0, (("v00-01", 0.3),), "v00-02"),
        Codification(350.0, "v00-01", ("v00-00", "v00-01", "v01-01"), 0.1),
        Schooling(400.0, ("v00-00", "v00-01"), 0.6, 0.6),
        Conquest(450.0, "v00-00", "v01-03", ("v01-03", "v01-02"), population=80, prestige=1.5),
        Contact(500.0, (("colony", "v01-03"),), 0.4, trade=True),
        StateCollapse(550.0, ("v00-00", "v00-01"), reach=15.0),
    ]
    return world, events, 700.0


def refinement() -> tuple[World, list[WorldEvent], float]:
    """Zjemnění souhrnné skupiny na sídla."""
    world = World(seed=1)
    world.add_territory(Territory("world", "world"))
    world.add_territory(Territory("coast", "region", parent="world", position=(0.0, 0.0)))
    base = world.seed_lexicon([f"c{index}" for index in range(30)])
    world.add_group(SpeechGroup("coast", "coast", population=4_000, aggregate=True,
                                codes=[Code("main", base.branch())], literacy=0.1))
    world.add_territory(Territory("hills", "settlement", parent="world", position=(15.0, 0.0)))
    world.add_group(SpeechGroup("hills", "hills", population=500, codes=[Code("main", base.branch())]))
    world.connect("coast", "hills", 0.5)
    settlements = (SettlementSpec("port", 3.0, (0.0, 0.0)), SettlementSpec("cove", 1.0, (5.0, 0.0)))
    return world, [RefineTerritory(250, "coast", settlements)], 500.0


def polity() -> tuple[World, list[WorldEvent], float]:
    """Státy, spisovné jazyky, školy, politika, identita, odtržení, obrození, lingua franca, zánik."""
    regions = (
        Region("capital", (0.0, 0.0), density=2.0, neighbours=("plain", "mountains", "south"), language="a",
               villages=3),
        Region("plain", (60.0, 0.0), neighbours=("capital",), language="b", villages=3),
        Region("mountains", (0.0, 60.0), density=0.5, neighbours=("capital",), language="c", villages=3,
               terrain="mountains", identity="strong"),
        Region("south", (0.0, -60.0), neighbours=("capital",), language="d", villages=3, identity="distinct"),
    )
    languages = (
        ProtoLanguage("a"),
        ProtoLanguage("b", consonants=("t", "k", "q", "s", "n", "m", "l", "ʃ", "x", "r", "j")),
        ProtoLanguage("c", consonants=("p", "t", "k", "s", "n", "m", "l", "f", "v", "r", "j")),
        ProtoLanguage("d", consonants=("b", "d", "g", "s", "n", "m", "l", "r", "w")),
    )
    world = region_world(regions, seed=1, languages=languages)
    everything = ("capital", "plain", "mountains", "south")
    events: list[WorldEvent] = [
        LinguaFranca(0.0, "capital", ("south",), "common", nativize=True),
        State(50.0, "kingdom", everything, "capital", policy="promoted", centralization="strong"),
        Standard(75.0, "kingdom", "elite"),
        Standard(75.0, "plain", "elite"),
        Schools(100.0, "kingdom", "towns", printing=True),
        Schools(100.0, "plain", "towns", printing=False),
        LanguagePolicy(150.0, "kingdom", "enforced"),
        Identity(160.0, ("south",), "strong"),
        Immigration(170.0, ("capital",), 0.1),
        Preserve(180.0, ("mountains",)),
        Secession(250.0, "free", ("plain",), "plain", policy="tolerant"),
        Revival(250.0, ("plain",), strength="national"),
        BorderPolicy(300.0, "free", "closed"),
        Schools(320.0, "kingdom", "mass", diglossic=True),
        Annexation(400.0, "kingdom", ("plain",)),
        Collapse(500.0, "kingdom"),
    ]
    return world, events, 700.0


SCENARIOS: dict[str, Callable[[], tuple[World, list[WorldEvent], float]]] = {
    "trade-elite": trade_elite,
    "church-school": church_school,
    "shift-trade": shift_trade,
    "conquest-shift": conquest_shift,
    "society": society,
    "refinement": refinement,
    "polity": polity,
}
