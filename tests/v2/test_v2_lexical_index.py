"""Lexikální jasnost nad poli proti definici z řetězců (výpočet po jedné dvojici)."""

import numpy as np

from cee.v2.language.lexical_index import _clarity_reference, clarity_scores, related_keys
from cee.v2.language.lexicon import UnitForm
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation


def oracle(world, code, morpheme, concept):
    """Skóre přímo z definice: erodovaný tvar a homofonie s nepříbuzným pojmem."""
    form = world.form_of(code, morpheme)
    eroded = len(form) <= 2 and len(form) < len(world.morphemes[morpheme].form)
    value = -0.5 if eroded else 0.0
    for other, root in code.phonology.dominant.items():
        if root != morpheme and other != concept and world.form_of(code, root) == form and not (
            world.semantics is not None and world.semantics.related(concept, other)
        ):
            return value - 0.4
    return value


def _check(world, codes, pairs_by_group):
    groups, morphemes, concepts, expected = [], [], [], []
    for position, (code, pairs) in enumerate(zip(codes, pairs_by_group)):
        for root, concept in pairs:
            groups.append(position)
            morphemes.append(world.registry.morphemes.numbers[root])
            concepts.append(world.registry.concepts.intern(concept))
            expected.append(oracle(world, code, root, concept))
    arguments = [np.array(values, dtype=np.int64) for values in (groups, morphemes, concepts)]
    found = clarity_scores(world, codes, *arguments)
    assert found.tolist() == expected
    # Python reference dává totéž, co jádro (v Rustu nebo v Pythonu).
    assert _clarity_reference(world, codes, *arguments, related_keys(world)).tolist() == expected


def test_zmeny_kolize_polysemie_a_externi_mutace():
    world = village_grid(1, seed=8, semantics=True)
    simulation = Simulation(world)
    code = world.groups[world.group_ids()[0]].main_code
    state = code.phonology
    concepts = list(state.dominant)[:4]
    roots = [state.dominant[concept] for concept in concepts]
    pairs = [(root, concept) for root in roots for concept in concepts]
    _check(world, [code], [pairs])

    # Dominantní i nedominantní kandidát získají stejný tvar.
    form = world.form_of(code, roots[0])
    code.forms.set(roots[1], UnitForm(form, None, None))
    state.version += 1
    _check(world, [code], [pairs])

    # Přímá mutace mimo deník: sdílený kořen a následný odchod pojmu.
    state.dominant[concepts[2]] = roots[0]
    state.version += 1
    state.lexicon_version += 1
    _check(world, [code], [pairs])
    del state.dominant[concepts[0]]
    state.version += 1
    state.lexicon_version += 1
    _check(world, [code], [pairs])
    code.forms.set(roots[2], UnitForm(form, None, None))
    state.version += 1
    _check(world, [code], [pairs])

    point = simulation.checkpoint()
    resumed = Simulation.resume(point).world
    restored = resumed.groups[world.group_ids()[0]].main_code
    _check(resumed, [restored], [pairs])
    restored.forms.set(roots[0], UnitForm(world.table.parse("pata"), None, None))
    restored.phonology.version += 1
    _check(resumed, [restored], [pairs])
    _check(world, [code], [pairs])


def test_vice_skupin_najednou_a_erodovany_tvar():
    world = village_grid(2, seed=9, semantics=True)
    Simulation(world)
    codes = [world.groups[group].main_code for group in world.group_ids()]
    pairs = [
        [(root, concept) for concept, root in sorted(code.phonology.dominant.items())] for code in codes
    ]
    _check(world, codes, pairs)
    # Zkrácení slova na dvě hlásky je eroze, ne krátkost odjakživa.
    code = codes[0]
    concept, root = next(iter(code.phonology.dominant.items()))
    short = world.table.parse("pa")
    assert len(world.morphemes[root].form) > len(short)
    code.forms.set(root, UnitForm(short, None, None))
    _check(world, codes, pairs)
    assert oracle(world, code, root, concept) <= -0.5
