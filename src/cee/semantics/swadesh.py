"""Kurátorované, volitelné návrhy složenin pro Swadeshův seznam 100.

Nejde o tvrzení, že všechny reálné jazyky tvoří tyto významy stejně. Balíček
jen dává worldbuilderovi několik srozumitelných možností nad existujícím
mechanismem složenin; pro každou položku zůstává volbou i samostatný kořen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from cee.core.models import State
from cee.engine.morphology import MorphologyEvaluator

SWADESH_100 = (
    "I", "you", "we", "this", "that", "who", "what", "not", "all", "many", "one", "two",
    "big", "long", "small", "woman", "man", "person", "fish", "bird", "dog", "louse", "tree",
    "seed", "leaf", "root", "bark", "skin", "flesh", "blood", "bone", "grease", "egg", "horn",
    "tail", "feather", "hair", "head", "ear", "eye", "nose", "mouth", "tooth", "tongue",
    "fingernail", "foot", "leg", "knee", "hand", "belly", "neck", "breast", "heart", "liver",
    "drink", "eat", "bite", "see", "hear", "know", "sleep", "die", "kill", "swim", "fly",
    "walk", "come", "lie", "sit", "stand", "give", "say", "sun", "moon", "star", "water", "rain",
    "stone", "sand", "earth", "cloud", "smoke", "fire", "ash", "burn", "path", "mountain", "red",
    "green", "yellow", "white", "black", "night", "hot", "cold", "full", "new", "good", "round",
    "dry",
)


@dataclass(frozen=True)
class CompoundSuggestion:
    target: str
    head: str
    modifier: str
    label: str


# Zdrojové koncepty mohou být samostatné kořeny i mimo Swadeshův seznam.
# Formu neurčujeme: vznikne až z konkrétního lexikonu a typologie jazyka.
_OPTIONS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "we": (("person", "I", "já-lidé"), ("I", "you", "já-a-ty")),
    "all": (("person", "many", "mnoho-lidí"),),
    "woman": (("person", "female", "ženský-člověk"),),
    "man": (("person", "male", "mužský-člověk"),),
    "bird": (("animal", "fly", "létající-zvíře"),),
    "fish": (("animal", "water", "vodní-zvíře"),),
    "louse": (("animal", "head", "hlavové-zvíře"),),
    "seed": (("tree", "child", "dítě-stromu"), ("plant", "begin", "začátek-rostliny")),
    "leaf": (("tree", "green", "zelený-strom"),),
    "root": (("tree", "earth", "zemní-strom"),),
    "bark": (("tree", "skin", "kůže-stromu"),),
    "fingernail": (("nail", "finger", "nehet-prstu"), ("hand", "nail", "nehet-ruky")),
    "knee": (("leg", "joint", "kloub-nohy"),),
    "neck": (("head", "body", "hlava-těla"),),
    "breast": (("body", "front", "předek-těla"),),
    "heart": (("body", "inside", "vnitřek-těla"),),
    "liver": (("body", "inside", "vnitřní-orgán"),),
    "drink": (("water", "take", "brát-vodu"),),
    "swim": (("water", "walk", "chodit-ve-vodě"),),
    "fly": (("air", "walk", "chodit-vzduchem"),),
    "sun": (("sky", "fire", "nebeský-oheň"),),
    "moon": (("night", "sun", "noční-slunce"),),
    "star": (("sky", "light", "nebeské-světlo"),),
    "rain": (("sky", "water", "nebeská-voda"),),
    "cloud": (("sky", "smoke", "nebeský-kouř"),),
    "smoke": (("fire", "cloud", "ohnivý-mrak"),),
    "ash": (("fire", "dust", "prach-ohně"),),
    "path": (("walk", "place", "místo-chůze"),),
    "mountain": (("earth", "big", "velká-země"),),
    "night": (("sun", "not", "bez-slunce"),),
    "hot": (("fire", "like", "jako-oheň"),),
    "cold": (("fire", "not", "bez-ohně"),),
    "full": (("inside", "all", "všechno-uvnitř"),),
    "new": (("now", "begin", "nový-začátek"),),
    "round": (("circle", "like", "jako-kruh"),),
    "dry": (("water", "not", "bez-vody"),),
}


def suggestions_for(target: str) -> list[CompoundSuggestion]:
    """Vrátí více volitelných návrhů pro daný Swadeshův koncept."""
    return [CompoundSuggestion(target, head, modifier, label) for head, modifier, label in _OPTIONS.get(target, ())]


def available_suggestions(state: State, target: str) -> list[CompoundSuggestion]:
    """Filtruje návrhy na ty, pro něž má jazyk oba skutečné lexémy."""
    return [
        option
        for option in suggestions_for(target)
        if state.lexicon.get_word(option.head) and state.lexicon.get_word(option.modifier)
    ]


def automatic_suggestions(state: State) -> list[CompoundSuggestion]:
    """Recepty, které lze bezpečně nabídnout samotnému simulátoru.

    Složenina nenahrazuje existující kořen a nevzniká z neexistujících zdrojů.
    Tím je automatizace omezená na skutečnou lexikální mezeru; autor může
    mechanismus kdykoli vypnout přes ``morphology.recipe_compounds``.
    """
    return [
        suggestion
        for suggestion in all_suggestions()
        if state.lexicon.get_word(suggestion.target) is None
        and state.lexicon.get_word(suggestion.head) is not None
        and state.lexicon.get_word(suggestion.modifier) is not None
    ]


def swadesh_coverage() -> dict[str, list[CompoundSuggestion]]:
    """Úplné pokrytí: prázdný seznam znamená „ponech jako samostatný kořen“."""
    return {concept: suggestions_for(concept) for concept in SWADESH_100}


def apply_suggestion(state: State, suggestion: CompoundSuggestion):
    """Až po výslovném potvrzení vytvoří složeninu existujícím evaluátorem."""
    word = MorphologyEvaluator().compound(state, suggestion.head, suggestion.modifier, suggestion.target)
    if word is not None and word.origin_rule == "compounding":
        word.origin_rule = f"semantic_recipe:{suggestion.label}"
    return word


def all_suggestions() -> Iterable[CompoundSuggestion]:
    for target in SWADESH_100:
        yield from suggestions_for(target)
