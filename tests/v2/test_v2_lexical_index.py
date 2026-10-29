"""Průběžná lexikální jasnost proti výpočtu celé mapy od začátku."""

from types import SimpleNamespace

from cee.v2.language.lexicon import UnitForm
from cee.v2.pressures.lexical import _clarity_map, _clarity_map_reference
from cee.v2.scenarios import village_grid
from cee.v2.semantics import ConceptGraph
from cee.v2.simulation import Simulation
from cee.v2.world import World


def _scores(world, group_id, pairs):
    batch = SimpleNamespace(world=world)
    actual = _clarity_map(batch, group_id)
    reference = _clarity_map_reference(batch, group_id)
    for root, concept in pairs:
        assert actual(root, concept) == reference(root, concept)


def test_zmeny_kolize_polysemie_a_externi_mutace():
    world = village_grid(1, seed=8, semantics=True)
    simulation = Simulation(world)
    group_id = world.group_ids()[0]
    code = world.groups[group_id].main_code
    state = code.phonology
    concepts = list(state.dominant)[:4]
    roots = [state.dominant[concept] for concept in concepts]
    pairs = [(root, concept) for root in roots for concept in concepts]
    _scores(world, group_id, pairs)
    index = state.cache["lexical-clarity-index"][1]
    untouched = (roots[3], concepts[3])
    previous = index.scores[untouched]

    # Dominantní i nedominantní kandidát získají stejný tvar.
    form = world.form_of(code, roots[0])
    code.forms.set(roots[1], UnitForm(form, None, None))
    state.version += 1
    _clarity_map(SimpleNamespace(world=world), group_id)
    assert index.scores[untouched] == previous
    _scores(world, group_id, pairs)

    # Přímá mutace mimo deník: sdílený kořen a následný odchod pojmu.
    state.dominant[concepts[2]] = roots[0]
    state.version += 1
    state.lexicon_version += 1
    _scores(world, group_id, pairs)
    del state.dominant[concepts[0]]
    state.version += 1
    state.lexicon_version += 1
    _scores(world, group_id, pairs)
    code.forms.set(roots[2], UnitForm(form, None, None))
    state.version += 1
    _scores(world, group_id, pairs)

    point = simulation.checkpoint()
    resumed = Simulation.resume(point).world
    _scores(resumed, group_id, pairs)
    restored = resumed.groups[group_id].main_code
    restored.forms.set(roots[0], UnitForm(world.table.parse("pata"), None, None))
    restored.phonology.version += 1
    _scores(resumed, group_id, pairs)
    _scores(world, group_id, pairs)


def test_nezmeneny_kandidat_se_znovu_necte_ani_neposuzuje(monkeypatch):
    world = village_grid(1, seed=9, semantics=True)
    Simulation(world)
    group_id = world.group_ids()[0]
    code = world.groups[group_id].main_code
    concept, root = next(iter(code.phonology.dominant.items()))
    original = world.form_of(code, root)
    other = next(item for item in code.phonology.dominant.values()
                 if world.form_of(code, item) != original)
    new_form = next(world.table.parse(word) for word in ("pata", "kita", "musu")
                    if world.table.parse(word) != original)
    batch = SimpleNamespace(world=world)
    read = World.form_of
    related = ConceptGraph.related
    reads: list[str] = []
    relations: list[tuple[str, str]] = []

    def counted_read(instance, code, morpheme):
        if instance is world:
            reads.append(morpheme)
        return read(instance, code, morpheme)

    def counted_related(graph, first, second):
        relations.append((first, second))
        return related(graph, first, second)

    monkeypatch.setattr(World, "form_of", counted_read)
    monkeypatch.setattr(ConceptGraph, "related", counted_related)
    score = _clarity_map(batch, group_id)
    expected = score(root, concept)
    code.forms.set(other, UnitForm(new_form, None, None))
    code.phonology.version += 1
    score = _clarity_map(batch, group_id)
    reads.clear()
    relations.clear()
    assert score(root, concept) == expected
    assert reads == [] and relations == []

