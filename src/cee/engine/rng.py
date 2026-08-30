"""
Odvozování seedů.

Reprodukovatelnost (CEE_master.md 5.5) neznamená, že se všechno chová stejně —
znamená, že se táž konfigurace chová stejně *pokaždé*. Jeden sdílený seed pro
všechny uzly obojí zaměňoval: tři jazyky se stejným biomem dostaly identickou
chronologii, což je vlastnost losování, ne jazykové skutečnosti.

Seed uzlu se proto odvozuje z globálního seedu a identity uzlu. Výsledek je
deterministický, ale pro každý uzel jiný.
"""

import hashlib
from typing import Iterable

# Seed musí zůstat v rozsahu, který přijme random.Random napříč platformami.
_SEED_BYTES = 8


def derive_seed(base_seed: int, *parts: str) -> int:
    """
    Odvodí seed z globálního seedu a libovolného počtu rozlišujících částí
    (typicky ID uzlu, případně i fáze běhu).

    Táž kombinace dá vždy týž seed; změna kterékoli části dá jiný.
    """
    digest = hashlib.blake2b(digest_size=_SEED_BYTES)
    digest.update(str(base_seed).encode("utf-8"))

    for part in parts:
        # Oddělovač brání tomu, aby ("ab", "c") a ("a", "bc") splynuly.
        digest.update(b"\x1f")
        digest.update(str(part).encode("utf-8"))

    return int.from_bytes(digest.digest(), "big")


def derive_seeds(base_seed: int, keys: Iterable[str]) -> dict:
    """Seedy pro celou sadu uzlů naráz."""
    return {key: derive_seed(base_seed, key) for key in keys}
