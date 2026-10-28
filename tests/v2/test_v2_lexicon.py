"""Graf pojmů, lexikální změny a tlaky enginu v2 (milník M3b)."""

import numpy as np
import pytest

from cee.v2.changes.base import InnovationContext
from cee.v2.changes.lexicon import BackFormation, Compounding, Derivation, SemanticShift
from cee.v2.language.lexicon import Morpheme, UnitForm
from cee.v2.pressures.base import PressureBatch
from cee.v2.pressures.lexical import Entrenchment, LexicalClarity
from cee.v2.repertoire import Distribution, Origin, Variable, Variant
from cee.v2.semantics import core_graph
from cee.v2.world import Code, SpeechGroup, Territory, World


def test_graf_pojmu_je_pribaleny_a_ma_dolozene_vztahy():
    graph = core_graph()
    assert any(relation.source == "tongue" and relation.polysemy > 0 for relation in graph.into("language"))
    assert graph.related("sun", "day")
    assert graph.compounds["rain"]


def _world(words, frequencies=None, taboo=()):
    world = World(seed=11)
    world.semantics = core_graph()
    world.add_territory(Territory("world", "world"))
    world.add_territory(Territory("v", "settlement", parent="world"))
    base = world.seed_lexicon(list(words), dict(words), frequencies)
    world.derivational_suffix = world.table.parse("ka")
    group = world.add_group(SpeechGroup("v", "v", 500, [Code("main", base.branch())], taboo=frozenset(taboo)))
    state = group.main_code.phonology
    for morpheme in world.morphemes.values():
        state.dominant[morpheme.meaning] = morpheme.id
        state.uses[morpheme.id] = 1
        state.vocabulary.add(morpheme.id)
    return world, group


def _context(world, group):
    return InnovationContext(world, group, group.main_code, 1, 25.0)


def _render(world, group, payload):
    return world.table.render(world.form_of(group.main_code, payload["morpheme"]))


def test_posun_vyznamu_prevezme_koren_doloze_zdrojoveho_pojmu():
    world, group = _world({"tongue": "lasu", "language": "meto", "water": "pa"})
    context = _context(world, group)
    change = SemanticShift()
    assert "lexical:language" in change.sites(context)
    options = change.options(context, "language")
    assert any(option["from"] == "tongue" for _, option in options)
    variant = change.propose(context, "lexical:language", np.random.default_rng(0), 0)
    assert variant.payload["origin"] == "shift"
    assert world.morphemes[variant.payload["morpheme"]].meaning in {"tongue", "mouth"}


def test_odvozenina_slozenina_a_zpetne_tvoreni():
    world, group = _world({"sun": "sol", "day": "dia", "sky": "nebe", "water": "voda", "rain": "dest"})
    context = _context(world, group)
    rng = np.random.default_rng(0)

    derived = Derivation().propose(context, "lexical:day", rng, 0)
    assert _render(world, group, derived.payload) == "solka"
    compound = Compounding().propose(context, "lexical:rain", rng, 0)
    assert _render(world, group, compound.payload) == "nebevoda"

    # Slunce dostalo jiné slovo; odvozenina „solka“ (den) pořád žije, takže
    # z ní lze zpětně vytvořit „sol“ pro slunce.
    state = group.main_code.phonology
    state.dominant["day"] = derived.payload["morpheme"]
    other = Morpheme("other-sun", "sun", world.table.parse("tuma"))
    world.morphemes[other.id] = other
    state.dominant["sun"] = other.id
    state.version += 1
    back = BackFormation().propose(context, "lexical:sun", rng, 0)
    assert back is not None and _render(world, group, back.payload) == "sol"


def _batch(world, group, variable, variants, freqs):
    return PressureBatch(
        world=world, variable_ids=[variable], group_ids=[group.id], freqs=np.array([[freqs]]),
        slots=[variants], tick=0, heard=np.array([[freqs]]),
    )


def test_erodovane_a_homofonni_slovo_je_nevyhodne_kratke_odjakziva_ne():
    world, group = _world({"water": "patu", "fire": "kos", "stone": "mesi", "louse": "ti"})
    code = group.main_code
    by_concept = {m.meaning: m for m in world.morphemes.values()}
    code.forms.set(by_concept["water"].id, UnitForm(world.table.parse("pa"), None, None))  # patu → pa
    code.forms.set(by_concept["stone"].id, UnitForm(world.table.parse("kos"), None, None))  # mesi → kos
    code.phonology.version += 1
    clarity = LexicalClarity()

    def score(concept):
        variant = Variant(f"v-{concept}", f"lexical:{concept}", {"morpheme": by_concept[concept].id},
                          Origin(None, 0, 0, None))
        world.variants[variant.id] = variant
        return clarity.scores(_batch(world, group, f"lexical:{concept}", [variant.id], [1.0]))[0, 0, 0]

    assert score("water") == pytest.approx(-0.5)  # eroze na dvě hlásky
    assert score("stone") == pytest.approx(-0.4)  # splynulo s „fire“
    assert score("fire") == pytest.approx(-0.4)
    assert score("louse") == 0.0  # krátké odjakživa, bez homofonu


def test_zazite_slovo_casteho_pojmu_ma_vetsi_vyhodu():
    world, group = _world({"water": "patu", "louse": "mesi"}, {"water": 0.9, "louse": 0.05})
    entrenchment = Entrenchment()
    values = {}
    for concept in ("water", "louse"):
        morpheme = next(m for m in world.morphemes.values() if m.meaning == concept)
        variant = Variant(f"v-{concept}", f"lexical:{concept}", {"morpheme": morpheme.id}, Origin(None, 0, 0, None))
        world.variants[variant.id] = variant
        values[concept] = entrenchment.scores(_batch(world, group, f"lexical:{concept}", [variant.id], [1.0]))[0, 0, 0]
    assert values["water"] > values["louse"] > 0


def test_slovo_ziska_frekvenci_kdyz_ziska_vyznam():
    world, group = _world({"tongue": "lasu", "language": "meto"}, {"tongue": 0.4, "language": 0.3})
    code = group.main_code
    tongue = next(m for m in world.morphemes.values() if m.meaning == "tongue")
    before = world.usage_frequency(code, tongue.id)
    code.phonology.dominant["language"] = tongue.id
    assert world.usage_frequency(code, tongue.id) == pytest.approx(before + 0.3)


def test_svet_bez_tvaru_lexikalni_tlaky_ignoruje():
    world = World(seed=1)
    world.add_territory(Territory("world", "world"))
    world.add_territory(Territory("v", "settlement", parent="world"))
    base = world.seed_lexicon(["water"])
    group = world.add_group(SpeechGroup("v", "v", 500, [Code("main", base.branch())]))
    variable = Variable("lexical", "water").id
    variant = world.stored("v", variable).variants[0]
    batch = _batch(world, group, variable, [variant], [1.0])
    assert not Entrenchment().scores(batch).any()
    assert Distribution.fixed(variant).is_fixed
