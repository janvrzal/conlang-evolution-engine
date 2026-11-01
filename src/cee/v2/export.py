"""Export běhu pro UI (iterace 5, oddíl Historie a export; milník M6c).

Jeden JSON dokument popisuje svět, jak ho UI potřebuje: území, skupiny a
vazby (mapa), snímky dialektů a jazyků (časová osa), strom linií jazyků
(genealogie), dnešní slova každé skupiny s původem (slovník) a gramatiku
skupin. Události běhu jsou zkrácené na ty, které má smysl ukázat na časové
ose; úplný log je v :meth:`cee.v2.history.History.write_jsonl`.

Formát má verzi ``FORMAT``; mění se jen přidáváním polí.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cee.v2 import polity

if TYPE_CHECKING:
    from cee.v2.simulation import Simulation
    from cee.v2.world import World

FORMAT = "cee-v2/1"

#: Události pro časovou osu UI; ostatní (inovace, milníky šíření…) jsou šum.
TIMELINE = frozenset({
    "border", "contact", "migration", "conquest", "war", "epidemic", "state_collapse",
    "religious_change", "codification", "printing", "schooling", "bilingualism",
    "transmission_stopped", "language_shift", "language_emerged", "language_split",
    "language_ended", "grammaticalized", "exapted", "refinement",
    # státy, jazyková politika a obrození (M6f)
    "state", "language_policy", "annexation", "secession", "collapse", "border_policy", "lingua_franca",
    "standard", "schools", "nativization", "revival_movement", "revival", "transmission_resumed", "preserve",
    "identity", "immigration",
})


def export(simulation: Simulation, *, events: frozenset[str] | None = TIMELINE) -> dict[str, Any]:
    """Stav a historie běhu jako slovník připravený k převodu na JSON.

    ``events`` vybere druhy událostí (``None`` = všechny).
    """
    world = simulation.world
    history = simulation.history
    observed = _observed_languages(simulation)
    return {
        "format": FORMAT,
        "seed": world.seed,
        "start_year": world.start_year,
        "year": simulation.year,
        "tick": simulation.tick,
        "territories": [
            {"id": territory.id, "level": territory.level, "parent": territory.parent,
             "position": territory.position, "terrain": territory.terrain,
             "native_language": territory.native_language}
            for _, territory in sorted(world.territories.items())
        ],
        "groups": [_group(world, group_id, observed.get(group_id)) for group_id in world.group_ids()],
        "links": [
            {"source": link.source, "target": link.target, "strength": link.strength, "kind": link.kind}
            for _, link in sorted(world.links.items())
        ],
        "snapshots": [
            {"tick": snapshot.tick, "year": snapshot.year,
             "dialects": [list(cluster) for cluster in snapshot.dialects],
             "languages": {lineage: list(groups) for lineage, groups in sorted(snapshot.languages.items())}}
            for snapshot in history.snapshots
        ],
        "lineages": lineages(simulation),
        "lexicon": {group_id: lexicon(world, group_id) for group_id in world.group_ids()},
        "grammar": {group_id: grammar(world, group_id) for group_id in world.group_ids()},
        "states": polity.states(world),
        "borders": polity.borders(world),
        "standards": dict(sorted(world.standards.items())),
        "census": polity.language_census(world),
        "events": [event for event in history.events if events is None or event["kind"] in events],
    }


def frame(simulation: Simulation) -> dict[str, Any]:
    """Lehký snímek pro průběžné kreslení během běhu (každý krok).

    Jen to, co se mění rychle a co UI kreslí na mapě: rok, populace, podíl
    L2 mluvčích, poslední pozorované dialekty a jazyky, jazyky regionů doma
    a mimo domov a území států.
    """
    world = simulation.world
    snapshot = simulation.history.snapshots[-1] if simulation.history.snapshots else None
    observed = _observed_languages(simulation)
    return {
        "year": simulation.year,
        "tick": simulation.tick,
        "groups": [
            {"id": group_id, "population": world.groups[group_id].population,
             "l2_share": world.groups[group_id].main_code.l2_share,
             "observed_language": observed.get(group_id)}
            for group_id in world.group_ids()
        ],
        "dialects": [] if snapshot is None else [list(cluster) for cluster in snapshot.dialects],
        "languages": {} if snapshot is None else {
            lineage: list(groups) for lineage, groups in sorted(snapshot.languages.items())
        },
        "census": polity.language_census(world),
        "states": [{"id": item["id"], "name": item["name"], "regions": item["regions"]} for item in polity.states(world)],
    }


def write_json(simulation: Simulation, path: str | Path, **options: Any) -> None:
    Path(path).write_text(
        json.dumps(export(simulation, **options), ensure_ascii=False, sort_keys=True, indent=1),
        encoding="utf-8",
    )


def _observed_languages(simulation: Simulation) -> dict[str, str]:
    if not simulation.history.snapshots:
        return {}
    last = simulation.history.snapshots[-1]
    return {group: lineage for lineage, groups in last.languages.items() for group in groups}


def _group(world: World, group_id: str, lineage: str | None) -> dict[str, Any]:
    group = world.groups[group_id]
    code = group.main_code
    return {
        "id": group.id, "territory": group.territory, "position": world.position_of(group_id),
        "population": group.population, "prestige": group.prestige, "openness": group.openness,
        "generation_years": group.generation_years, "community": group.community or group.id,
        "domain": group.domain, "written": group.written, "aggregate": group.aggregate,
        "code_language": code.language, "observed_language": lineage,
        "l2_share": code.l2_share, "literacy": group.literacy, "schooling": group.schooling,
        "standard": group.standard, "liturgy": group.liturgy,
        "loyalty": group.loyalty, "home_pull": group.home_pull, "preserved": group.preserved,
        "revival": group.revival,
    }


def lineages(simulation: Simulation) -> list[dict[str, Any]]:
    """Strom jazyků: linie, jejich rodiče a doba trvání (z událostí pozorování)."""
    found: dict[str, dict[str, Any]] = {}
    for event in simulation.history.events:
        kind = event["kind"]
        if kind in ("language_emerged", "language_split"):
            found[event["lineage"]] = {
                "id": event["lineage"], "parent": event["parent"], "start_year": event["year"],
                "end_year": None, "groups_at_start": event["groups"],
            }
        elif kind == "language_ended" and event["lineage"] in found:
            found[event["lineage"]]["end_year"] = event["year"]
    last = simulation.history.snapshots[-1].languages if simulation.history.snapshots else {}
    for lineage, item in found.items():
        item["groups"] = list(last.get(lineage, ()))
    return sorted(found.values(), key=lambda item: (item["start_year"], item["id"]))


def lexicon(world: World, group_id: str) -> dict[str, dict[str, Any]]:
    """Dnešní slova skupiny: tvar (IPA), lexém a jeho původ."""
    code = world.groups[group_id].main_code
    result: dict[str, dict[str, Any]] = {}
    if world.table is None:
        return result
    for concept, root in sorted(code.phonology.dominant.items()):
        morpheme = world.morphemes[root]
        origin = morpheme.etymology or ("inherited" if morpheme.origin_group is None else "coinage")
        result[concept] = {
            "form": world.table.render(world.form_of(code, root)),
            "root": root,
            "language": morpheme.language,
            "loan": morpheme.language != code.language,
            "origin": origin,
            "sources": list(morpheme.sources),
            "base": morpheme.base,
            "since": None if morpheme.origin_group is None else morpheme.origin_tick,
        }
    return result


def grammar(world: World, group_id: str) -> dict[str, dict[str, Any]]:
    """Převládající konstrukce každé gramatické funkce skupiny."""
    from cee.v2 import syntax

    result: dict[str, dict[str, Any]] = {}
    for entry in syntax.functions(world):
        construction = syntax.dominant(world, group_id, entry.id)
        if construction is None:
            continue
        result[entry.id] = {
            "kind": construction.kind, "source": construction.source, "stage": construction.stage,
            "order": construction.order, "reinforcer": construction.reinforcer,
            "donor": construction.donor,
            "exponent": None if construction.exponent is None or world.table is None else
            world.table.render(world.morphemes[construction.exponent].form),
        }
    return result
