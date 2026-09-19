"""Výchozí slovní zásoba pro nové worldbuildingové projekty.

CLICS4 je výborný referenční korpus, ale jeho tisíce konceptů nejsou vhodnou
výchozí velikostí simulace. Tento seznam je záměrně malý a kurátorovaný:
Swadeshovo jádro plus několik významů potřebných pro běžný svět, společnost a
základní gramatiku. Plný sémantický korpus se načítá jen na výslovnou volbu.
"""

from __future__ import annotations

from typing import Any

# V pramenech existuje několik mírně odlišných verzí Swadeshova seznamu.
# Záměrně držíme konzervativní společné jádro místo předstírání jedné kanonické
# číslované verze.
SWADESH_CORE = """
i you we this that who what not all many one two big long small woman man person fish bird dog
louse tree seed leaf root bark skin flesh blood bone grease egg horn tail feather hair head ear eye nose
mouth tooth tongue fingernail foot leg knee hand belly neck breasts heart liver drink eat bite see hear know
sleep die kill swim fly walk come lie sit stand give say sun moon star water rain stone sand earth cloud
smoke fire ash burn path mountain red green yellow white black night hot cold full new good round dry name
""".split()

# Není to pokus o univerzální seznam kultury. Jsou to významy, které dávají
# malé simulaci dost materiálu pro kontakt, registr, derivaci a worldbuilding.
CORE_EXTENSION = """
father mother child family house village town road river sea forest field wind thunder day year morning
food grain salt animal horse boat trade king law war peace god spirit ritual write read speak language
friend enemy work make carry open close near far old young fast slow
""".split()

_VERBS = {
    "drink", "eat", "bite", "see", "hear", "know", "sleep", "die", "kill", "swim", "fly", "walk",
    "come", "lie", "sit", "stand", "give", "say", "burn", "write", "read", "speak", "work", "make",
    "carry", "open", "close",
}
_ADJECTIVES = {
    "big", "long", "small", "many", "hot", "cold", "full", "new", "good", "round", "dry", "red",
    "green", "yellow", "white", "black", "near", "far", "old", "young", "fast", "slow",
}
_PRONOUNS = {"i", "you", "we", "who", "what", "this", "that"}
_PARTICLES = {"not", "all", "one", "two"}


def _entry(concept_id: str) -> dict[str, Any]:
    normalized = concept_id.strip().lower().replace(" ", "_")
    if normalized in _PRONOUNS:
        pos = "pronoun"
    elif normalized in _PARTICLES:
        pos = "particle"
    elif normalized in _VERBS:
        pos = "verb"
    elif normalized in _ADJECTIVES:
        pos = "adj"
    else:
        pos = "noun"
    return {"id": normalized, "pos": pos, "meaning": normalized.replace("_", " ")}


def core_concepts(custom_concepts: list[str] | None = None) -> list[dict[str, Any]]:
    """Vrátí stabilní základ a případná uživatelsky zadaná specifická slova."""
    ids = [*SWADESH_CORE, *CORE_EXTENSION]
    if custom_concepts:
        ids.extend(custom_concepts)
    seen: set[str] = set()
    concepts: list[dict[str, Any]] = []
    for concept_id in ids:
        normalized = concept_id.strip().lower().replace(" ", "_")
        if normalized and normalized not in seen:
            seen.add(normalized)
            concepts.append(_entry(normalized))
    return concepts
