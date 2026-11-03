"""Lexikální jasnost jako výpočet nad poli (krok B5, Python reference).

Skóre dvojice (morfém ``m``, pojem ``c``) u jedné skupiny:

- ``-0,5``, když je tvar ``m`` erodovaný: má nejvýš dvě hlásky a je kratší než
  jeho výchozí tvar (krátké slovo odjakživa je stabilní);
- dalších ``-0,4``, když stejný tvar má jako dominantní kořen jiný morfém ``r``
  pro jiný pojem ``d``, který s ``c`` není doloženě příbuzný (polysémie
  příbuzných pojmů se za homofonii nepočítá).

Vstupem jsou jen pole: dominantní kořeny skupiny (pojem → kořen, ``DominantMap.roots``),
tvary kódu (``FormStore.raw()``), výchozí tvary světa (sloupec morfémů), banka tvarů
a seřazená pole příbuzných dvojic pojmů. Tabulka vlastníků tvarů (tvar → dvojice
(pojem, kořen)) se při každém volání staví znovu z dominantních kořenů: je to
stovka položek na skupinu, takže je to levnější než ji dorovnávat podle deníků,
a výsledek nemůže zastarat. Volání je jedno na dávku tlaků pro všechny skupiny
(Rust: ``cee_core.clarity_scores``, ``rust/cee_core/src/clarity.rs``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt

from cee.v2 import native

if TYPE_CHECKING:
    from cee.v2.world import Code, World

#: Pokuta za erodovaný tvar a za homofonii s nepříbuzným pojmem.
ERODED = -0.5
HOMOPHONE = -0.4

_RELATED: dict[tuple[int, int], tuple[Any, Any, npt.NDArray[np.int64]]] = {}


def related_keys(world: World) -> npt.NDArray[np.int64]:
    """Seřazené klíče příbuzných dvojic pojmů: ``min(a, b) << 32 | max(a, b)`` (čísla pojmů z registru)."""
    graph = world.semantics
    if graph is None:
        return np.zeros(0, dtype=np.int64)
    key = (id(graph), id(world.registry))
    found = _RELATED.get(key)
    if found is None:
        if len(_RELATED) >= 16:
            _RELATED.clear()
        intern = world.registry.concepts.intern
        keys = sorted(
            (min(a, b) << 32) | max(a, b)
            for a, b in ((intern(x), intern(y)) for x, y in (sorted(pair) for pair in getattr(graph, "_pairs") if len(pair) == 2))
        )
        found = _RELATED[key] = (graph, world.registry, np.array(keys, dtype=np.int64))
    return found[2]


def _default_form(world: World, number: int) -> int:
    """Číslo výchozího tvaru morfému v bance; při prvním použití ho do sloupce doplní."""
    column = world.columns.morphemes.form
    if number < len(column) and column[number] >= 0:
        return int(column[number])
    name = world.registry.morphemes.names[number]
    found = world.form_bank().id_of(world._default_unit(name).form)
    if number < len(column):
        column[number] = found
        world.columns.morphemes.version += 1
    return found


def _effective(world: World, code: Code, numbers: npt.NDArray[np.int64]) -> npt.NDArray[np.int64]:
    """Číslo tvaru každého z morfémů v kódu (uložený tvar, jinak výchozí)."""
    store = code.forms.raw()[0]
    found = np.empty(len(numbers), dtype=np.int64)
    for at, number in enumerate(numbers.tolist()):
        stored = store[number] if number < len(store) else -1
        found[at] = stored if stored >= 0 else _default_form(world, number)
    return found


def clarity_scores(
    world: World,
    codes: list[Code],
    groups: npt.NDArray[np.int64],
    morphemes: npt.NDArray[np.int64],
    concepts: npt.NDArray[np.int64],
) -> npt.NDArray[np.float64]:
    """Skóre jasnosti dvojic (morfém, pojem) u skupin ``codes[groups]``; Rust, nebo Python."""
    if not len(groups):
        return np.zeros(0, dtype=np.float64)
    related = related_keys(world)
    kernel = native.kernel("clarity_scores")
    bank = world.form_bank()._native
    if kernel is not None and bank is not None:
        roots = [code.phonology.dominant.roots for code in codes]
        forms = [code.forms.raw()[0] for code in codes]
        defaults = world.columns.morphemes.form
        while True:
            found = kernel(bank, roots, forms, defaults, related, groups, morphemes, concepts)
            if isinstance(found, list):  # chybějící výchozí tvary doplní Python
                for number in found:
                    _default_form(world, number)
                continue
            return found  # type: ignore[no-any-return]
    return _clarity_reference(world, codes, groups, morphemes, concepts, related)


def _clarity_reference(
    world: World,
    codes: list[Code],
    groups: npt.NDArray[np.int64],
    morphemes: npt.NDArray[np.int64],
    concepts: npt.NDArray[np.int64],
    related: npt.NDArray[np.int64],
) -> npt.NDArray[np.float64]:
    result = np.zeros(len(groups), dtype=np.float64)
    for group in np.unique(groups).tolist():
        code = codes[group]
        at = np.nonzero(groups == group)[0]
        roots = np.frombuffer(code.phonology.dominant.roots, dtype=np.int32).astype(np.int64)
        owners = np.nonzero(roots >= 0)[0]
        owner_roots = roots[owners]
        owner_forms = _effective(world, code, owner_roots)
        query = morphemes[at]
        forms = _effective(world, code, query)
        defaults = np.array([_default_form(world, number) for number in query.tolist()], dtype=np.int64)
        lengths = world.form_bank()._lengths  # až po zařazení tvarů: pole se při růstu banky nahrazuje
        length = lengths[forms]
        eroded = (length <= 2) & (length < lengths[defaults])
        value = np.where(eroded, ERODED, 0.0)
        if len(owners):
            same = (
                (owner_forms[None, :] == forms[:, None])
                & (owner_roots[None, :] != query[:, None])
                & (owners[None, :] != concepts[at][:, None])
            )
            low = np.minimum(owners[None, :], concepts[at][:, None])
            high = np.maximum(owners[None, :], concepts[at][:, None])
            keys = (low << 32) | high
            position = np.minimum(np.searchsorted(related, keys), max(len(related) - 1, 0))
            linked = (related[position] == keys) if len(related) else np.zeros(keys.shape, dtype=bool)
            value = np.where((same & ~linked).any(axis=1), value + HOMOPHONE, value)
        result[at] = value
    return result
