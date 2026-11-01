"""Hláskové tvary protojazyka a nových kořenů.

Protojazyk se generuje ze slabičné šablony a inventáře. Nový kořen (M2:
expresivní tvoření) se skládá ze slabik, které jazyk *právě teď* užívá:
podle jeho skutečné fonotaktiky, ne z náhodného pytle hlásek jako v legacy.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from cee.v2.language.segments import Form, SegmentTable
from cee.v2.rng import generator

DEFAULT_CONSONANTS = ("p", "t", "k", "b", "d", "ɡ", "m", "n", "s", "l", "r", "w", "j", "h")
DEFAULT_VOWELS = ("a", "e", "i", "o", "u")


def protolanguage(
    concepts: Sequence[str],
    *,
    seed: int,
    consonants: Sequence[str] = DEFAULT_CONSONANTS,
    vowels: Sequence[str] = DEFAULT_VOWELS,
    syllables: tuple[int, int] = (1, 3),
    coda_share: float = 0.25,
    fixed: Mapping[str, str] | None = None,
    tones: Sequence[str] = (),
) -> tuple[dict[str, str], dict[str, float]]:
    """Tvary a frekvence pojmů; stejný seed dá stejný protojazyk.

    Hlásky mají Zipfovské rozdělení četnosti (první v seznamu nejčastější),
    jako v reálných inventářích. Homofony se v protojazyce nepřipouštějí.
    Frekvence pojmů je log-rovnoměrná; prvních 20 pojmů (zájmena a základní
    slova Swadeshova seznamu) má frekvenci vysokou.

    ``fixed`` jsou slova, která zadal autor (pojem → IPA). Generátor pro ně
    náhodu spotřebuje stejně, takže ostatní slova zůstanou, jak by byla; liší
    se jen tehdy, když by se s autorovým slovem shodovala (homofon).
    """
    fixed = dict(fixed or {})
    # ``tones``: tóny tónového jazyka (tónové značky); každá samohláska dostane
    # jeden, první v seznamu nejčastěji. Bez tónů se náhoda na tóny nespotřebuje.
    rng = generator(seed, "protolanguage")
    consonant_weights = _zipf(len(consonants))
    vowel_weights = _zipf(len(vowels))
    tone_weights = _zipf(len(tones)) if tones else None
    forms: dict[str, str] = {}
    used: set[str] = set(fixed.values())
    for concept in dict.fromkeys(concepts):
        for _ in range(100):
            count = int(rng.integers(syllables[0], syllables[1] + 1))
            word = ""
            for position in range(count):
                if position == 0 and rng.random() < 0.15:
                    pass  # slovo začínající samohláskou
                else:
                    word += consonants[int(rng.choice(len(consonants), p=consonant_weights))]
                word += vowels[int(rng.choice(len(vowels), p=vowel_weights))]
                if tones:
                    word += tones[int(rng.choice(len(tones), p=tone_weights))]
            if rng.random() < coda_share:
                word += consonants[int(rng.choice(len(consonants), p=consonant_weights))]
            if len(word) >= 2 and word not in used:
                break
        word = fixed.get(concept, word)
        used.add(word)
        forms[concept] = word
    frequencies = {
        concept: float(0.9 if index < 20 else np.exp(rng.uniform(np.log(0.05), np.log(0.8))))
        for index, concept in enumerate(dict.fromkeys(concepts))
    }
    return forms, frequencies


def _zipf(count: int) -> np.ndarray:
    weights = 1.0 / np.arange(1, count + 1) ** 0.7
    return weights / weights.sum()


def coin(
    table: SegmentTable,
    vocabulary: Mapping[str, Form],
    rng: np.random.Generator,
    avoid: set[Form],
) -> Form | None:
    """Nový kořen ze slabik, které jazyk užívá, a délky běžného slova.

    Vezme kostru (pořadí souhlásek a samohlásek) náhodného existujícího slova
    a naplní ji hláskami podle jejich četnosti v jazyce. Vrátí ``None``, když
    se nepodaří vyhnout homofonu.
    """
    forms = [vocabulary[key] for key in sorted(vocabulary)]
    if not forms:
        return None
    consonants = [segment for form in forms for segment in form if not table.is_vowel(segment)]
    vowels = [segment for form in forms for segment in form if table.is_vowel(segment)]
    if not consonants or not vowels:
        return None
    for _ in range(12):
        skeleton = forms[int(rng.integers(len(forms)))]
        candidate = tuple(
            vowels[int(rng.integers(len(vowels)))] if table.is_vowel(segment)
            else consonants[int(rng.integers(len(consonants)))]
            for segment in skeleton
        )
        if candidate not in avoid:
            return candidate
    return None
