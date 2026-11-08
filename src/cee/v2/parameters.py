"""Metaparametry enginu v2: popis z ``v2_parameters.json`` pro UI a ověření přepisů.

Soubor ``cee/data/v2_parameters.json`` je jediný zdroj výchozích hodnot, druhů, popisů, skupin
pro UI a mezí; čte ho i Rust (``rust/cee_engine/src/parameters.rs``), který z něj skládá
kalibrační konstanty běhu. Python tu jen ověřuje přepisy z popisu světa (s cestou k poli)
a dává UI schéma. Formát: ``docs/engine-v2/19-engine-v-rustu.md``, oddíl „Metaparametry“.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

#: Soubor metaparametrů: jediný zdroj výchozích hodnot, druhů, popisů, skupin pro UI a mezí
#: (čte ho i Rust). Formát: ``docs/engine-v2/19-engine-v-rustu.md``, oddíl „Metaparametry“.
PARAMETERS_FILE = Path(__file__).resolve().parents[1] / "data" / "v2_parameters.json"
#: Druhy parametrů v souboru; ``level_table`` a ``level_table2`` jsou slovní úrovně.
KINDS = ("number", "table", "table2", "level_table", "level_table2")
#: Úlohy parametrů v modelu: nastavení světa, aktivně laděné páky, zafixované konstanty.
ROLES = ("world", "active", "fixed")


def _load() -> dict[str, Any]:
    return json.loads(PARAMETERS_FILE.read_text(encoding="utf-8"))


#: Obsah ``v2_parameters.json`` (``format``, ``groups``, ``parameters``).
SPECS: dict[str, Any] = _load()
#: Popis parametru podle jména.
SPEC_BY_NAME: dict[str, dict[str, Any]] = {item["name"]: item for item in SPECS["parameters"]}


def parameter_schema(role: str | None = None) -> dict[str, Any]:
    """Parametry pro UI: skupiny a seznam parametrů s výchozí hodnotou, druhem, popisem,
    skupinou, mezemi, rolí a (u slovních úrovní) výčtem úrovní."""
    if role is not None and role not in ROLES:
        raise ValueError(f"Neznámá role {role!r}; možnosti: {', '.join(ROLES)}")
    items = []
    for item in SPECS["parameters"]:
        if role is not None and item.get("role") != role:
            continue
        out = dict(item)
        if item["kind"] in {"level_table", "level_table2"}:
            out["levels"] = sorted(item["default"])
        items.append(out)
    return {"groups": SPECS["groups"], "items": items}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_override(name: str, value: Any) -> list[tuple[str, str]]:
    """Chyby přepisu parametru ``name`` podle souboru: dvojice (cesta, zpráva).

    Cesta je ``parameters.<jméno>`` a u tabulek pokračuje klíči. Kontroluje jméno,
    druh a meze, které soubor uvádí (``keys``, ``inner_keys``, ``min``, ``max``).
    """
    path = f"parameters.{name}"
    spec = SPEC_BY_NAME.get(name)
    if spec is None:
        return [(path, "neznámý parametr")]
    kind = spec["kind"]
    lo, hi = spec.get("min"), spec.get("max")

    def number(where: str, item: Any) -> list[tuple[str, str]]:
        if not _is_number(item):
            return [(where, "očekáváno číslo")]
        if lo is not None and item < lo:
            return [(where, f"nesmí být menší než {lo}")]
        if hi is not None and item > hi:
            return [(where, f"nesmí být větší než {hi}")]
        return []

    def names(where: str, table: Mapping[str, Any], allowed: list[str] | None) -> list[tuple[str, str]]:
        if allowed is None:
            return []
        return [
            (f"{where}.{key}", f"neznámé jméno; možnosti: {', '.join(allowed)}")
            for key in sorted(set(table) - set(allowed))
        ]

    if kind == "number":
        return number(path, value)
    if not isinstance(value, Mapping):
        what = "jméno → číslo" if kind in {"table", "level_table"} else "jméno → jméno → číslo"
        return [(path, f"očekávána tabulka {what}")]
    issues = names(path, value, spec.get("keys"))
    for key, item in value.items():
        where = f"{path}.{key}"
        if kind in {"table", "level_table"}:
            issues += number(where, item)
        elif not isinstance(item, Mapping):
            issues.append((where, "očekávána tabulka jméno → číslo"))
        else:
            issues += names(where, item, spec.get("inner_keys"))
            for inner, number_item in item.items():
                issues += number(f"{where}.{inner}", number_item)
    return issues


#: Tabulky slovních úrovní, které autor světa zadává jménem (výběr v UI).
LEVEL_TABLES = (
    "centralization_levels", "policy_levels", "lingua_franca_levels", "terrain_access", "identity_loyalty",
    "literacy_levels", "schooling_levels", "border_levels", "revival_levels", "background_levels",
)


def default_levels() -> dict[str, list[str]]:
    """Možnosti slovních úrovní podle výchozích tabulek v souboru."""
    return {name: sorted(SPEC_BY_NAME[name]["default"]) for name in LEVEL_TABLES}
