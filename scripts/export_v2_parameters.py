"""Jednorázový převod metaparametrů enginu v2 do ``src/cee/data/v2_parameters.json``.

Soubor je od tohoto převodu **jediný zdroj** výchozích hodnot, českých popisů,
skupin pro UI a mezí: čte ho Rust (``include_str!``), Python (``cee.v2.parameters``,
``cee.v2.spec``) i server (``GET /api/v2/schema``). Skript slouží jen k prvnímu
převodu z hodnot a komentářů ``#:`` dřívějšího ``parameters.py``; po převodu
``parameters.py`` hodnoty z JSON bere, takže skript už nemá co číst. Při změně
parametru se upravuje přímo JSON (a popis formátu v ``19-engine-v-rustu.md``).

Meze se zapisují jen tam, kde je dosavadní kód vynucoval: kanály a domény
(``CHANNELS``, ``DOMAINS``) a nezáporné váhy domén, pole gramatiky
(``GRAMMAR_FIELDS``). Jinde jsou prázdné.

Použití (jen proti dřívější verzi ``parameters.py``):
    PYTHONPATH=src python scripts/export_v2_parameters.py
"""

from __future__ import annotations

import ast
import json
from dataclasses import fields
from pathlib import Path

from cee.v2 import parameters as P

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "cee" / "data" / "v2_parameters.json"

GROUPS = [
    ("sound", "Zvukové změny"),
    ("morphology", "Morfologie a syntax"),
    ("transfer", "Přenos mezi generacemi a populace"),
    ("lexicon", "Výměna slov"),
    ("contact", "Kontakt a výpůjčky"),
    ("institutions", "Instituce, písmo a škola"),
    ("society", "Společnost, stát a jazyková politika"),
    ("background", "Pozadí dějin"),
    ("tuning", "Váhy tlaků a tempa změn"),
]

GROUP_OF = {
    "sound": ["functional_load_scale", "stress_strength_multiplier", "coda_tolerance_scale",
              "clarity_short_factor", "dispersion_factor"],
    "morphology": ["learnability_strength", "economy_word_cost", "fusion_bonus", "order_rigidity",
                   "emergence_need_scale", "category_loss_l2_boost", "analogy_l2_boost",
                   "grammar_threshold", "conserved_frequency", "analogy_threshold",
                   "restructure_threshold", "word_bias_sd", "frequency_lead", "closure_generations",
                   "activation_share", "paradigm_merge_weight", "redundant_merge_weight", "grammar"],
    "transfer": ["population_per_density", "village_openness", "border_link_scale", "interference_weight",
                 "child_threshold", "shift_rate", "shift_exponent", "standing_variation", "variation_cap"],
    "lexicon": ["entrenchment_strength", "entrenchment_frequency_exponent", "entrenchment_base",
                "lexical_appeal_sd"],
    "contact": ["channel_domains", "borrowability_strength"],
    "institutions": ["school_correction", "reading_weight", "reading_core_resistance", "school_weight",
                     "liturgy_weight", "literacy_levels", "schooling_levels", "standard_prestige"],
    "society": ["capital_prestige", "capital_link_strength", "capital_reach", "centralization_levels",
                "policy_levels", "lingua_franca_levels", "lingua_franca_link", "lingua_franca_pull",
                "revival_levels", "border_levels", "terrain_access", "identity_loyalty"],
    "background": ["background_levels", "background_spans", "background_elite_prestige",
                   "background_elite_link", "background_elite_share", "background_rates"],
    "tuning": ["pressure_weights", "change_rates"],
}

#: Komentáře, které v ``parameters.py`` stojí nad víc poli nebo je mají smíšené; popis
#: jednotlivého pole se tu zapíše ručně (obsah je z dřívějších komentářů).
DESCRIPTION_OVERRIDES = {
    "capital_prestige": (
        "Kolikrát vyšší prestiž mají vesnice hlavního města. Prestiž řídí, od koho se děti učí "
        "(mixing matrix), i status jazyka při přechodu."
    ),
    "centralization_levels": (
        "Slovní úrovně centralizace státu (``State(centralization=...)``) a jejich násobky síly "
        "vazby vesnice k sídlu státu (``capital_link_strength``)."
    ),
    "background_spans": (
        "Rozsahy náhodných veličin pozadí dějin (rovnoměrně mezi mezemi ``low`` a ``high``): podíl "
        "zemřelých při moru, podíl přesídlených, násobek obchodu a prestiže a doby v krocích po 25 "
        "letech (obnova po moru, trvání obchodní cesty, splynutí cizí elity s místními)."
    ),
    "background_rates": (
        "Kolikrát za století v jednom kraji nastane událost pozadí při míře ``normal``: mor, "
        "přesídlení části lidí k sousedům, vzestup obchodní cesty k sousednímu kraji, změna "
        "prestiže kraje, cizí elita od souseda jiného jazyka. Autorský odhad, kalibruje se v M7 "
        "(retence slovní zásoby)."
    ),
}

LEVELS = set(P.LEVEL_TABLES)


def comments() -> dict[str, str]:
    """Popis pole = souvislý blok ``#:`` nad ním (nebo nad první skupinou polí, která ho sdílí)."""
    path = Path(P.__file__)
    lines = path.read_text(encoding="utf-8").splitlines()
    tree = ast.parse("\n".join(lines))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Parameters")
    out: dict[str, str] = {}
    last = ""
    for node in cls.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        block: list[str] = []
        index = node.lineno - 2
        while index >= 0 and lines[index].strip().startswith("#:"):
            block.insert(0, lines[index].strip()[2:].strip())
            index -= 1
        if block:
            paragraphs, current = [], []
            for line in block:
                if line:
                    current.append(line)
                elif current:
                    paragraphs.append(" ".join(current))
                    current = []
            if current:
                paragraphs.append(" ".join(current))
            last = " ".join(paragraphs)
        out[node.target.id] = last  # type: ignore[union-attr]
    return out


def plain(value):
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: plain(item) for key, item in value.items()}
    return float(value)


def depth(value) -> int:
    return 0 if isinstance(value, float) else 1 + depth(next(iter(value.values()))) if value else 1


def main() -> None:
    texts = comments()
    defaults = P.Parameters()
    group_of = {name: group for group, names in GROUP_OF.items() for name in names}
    items = []
    for field in fields(P.Parameters):
        name = field.name
        value = plain(getattr(defaults, name))
        nested = depth(value) == 2 or name in {"grammar", "channel_domains"} or (
            name in LEVELS and any(isinstance(v, dict) for v in value.values())
        )
        if name in LEVELS:
            kind = "level_table2" if nested else "level_table"
        elif isinstance(value, float):
            kind = "number"
        else:
            kind = "table2" if nested else "table"
        description = DESCRIPTION_OVERRIDES.get(name, texts[name])
        item = {"name": name, "kind": kind, "default": value, "description": description,
                "group": group_of[name]}
        if name == "channel_domains":
            item.update(keys=list(P.CHANNELS), inner_keys=list(P.DOMAINS), min=0.0)
        elif name == "grammar":
            item.update(inner_keys=sorted(P.GRAMMAR_FIELDS))
        items.append(item)
    missing = set(group_of) ^ {f.name for f in fields(P.Parameters)}
    assert not missing, missing
    document = {
        "format": "cee-v2-parameters/1",
        "groups": [{"id": key, "title": title} for key, title in GROUPS],
        "parameters": items,
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(items)} parametrů -> {OUT}")


if __name__ == "__main__":
    main()
