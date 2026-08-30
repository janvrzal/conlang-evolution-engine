"""Regrese pro společné diachronní jádro etapy 2."""

from cee.core.models import Inventory, Lexicon, State
from cee.engine.lexicon import LexicalEvaluator
from cee.engine.prosody import syllabify
from cee.engine.rules import Rule
from cee.engine.simulator import EvolutionSimulator
from cee.engine.topology import ContactEdge, EvolutionGraph, VerticalEdge


def _root(mapper, words):
    return State(
        node_id="proto",
        year=0,
        inventory=Inventory(),
        lexicon=Lexicon([mapper.parse_word(concept, ipa) for concept, ipa in words]),
    )


def test_slabiky_rozlisuji_kodu_a_pravidlo_na_ni_miri(mapper):
    word = mapper.parse_word("word", "anta")
    syllables = syllabify(word)
    assert len(syllables) == 2
    assert not syllables[0].is_open

    rule = Rule(
        name="ztráta kody",
        year=1,
        target={"cons": "+"},
        action={"delete": "+"},
        syllable_part="coda",
    )
    assert rule.apply_to_word(word)
    assert mapper.render_word(word) == "ata"


def test_slozenina_vznikne_pred_pozdejsi_fonologii(mapper):
    graph = EvolutionGraph(
        node_configs={
            "proto": {},
            "child": {
                "year": 0,
                "compounds": [{"head": "town", "modifier": "gold", "id": "gold_town"}],
            },
        },
        vertical_edges=[
            VerticalEdge(
                "proto",
                "child",
                [
                    Rule(
                        "finální apokopa",
                        {"syl": "+"},
                        {"delete": "+"},
                        env_after={"_boundary": "+"},
                        year=50,
                    ),
                ],
            )
        ],
    )
    states = EvolutionSimulator(graph, mapper).simulate(
        _root(mapper, [("town", "viku"), ("gold", "auru")])
    )
    compound = states["child"].lexicon.get_word("gold_town")
    assert compound is not None
    assert mapper.render_word(compound).endswith("vik")


def test_lexikalni_nahrada_je_volitelna_a_casovana(mapper):
    graph = EvolutionGraph(
        node_configs={
            "proto": {},
            "child": {"year": 0, "lexical": {"enabled": True, "replacement_rate": 1.0}},
        },
        vertical_edges=[VerticalEdge("proto", "child", [])],
    )
    state = EvolutionSimulator(graph, mapper, end_year=100).simulate(
        _root(mapper, [("one", "pata"), ("two", "kumi")])
    )["child"]
    replacements = [
        word for word in state.lexicon.words if word.origin_type == "lexical_replacement"
    ]
    assert replacements
    assert all(word.origin_year == 100 for word in replacements)


def test_adaptovana_vypujcka_respektuje_cilovy_inventar(mapper):
    graph = EvolutionGraph(
        node_configs={"proto": {}, "a": {"year": 0}, "b": {"year": 0}},
        vertical_edges=[
            VerticalEdge(
                "proto",
                "a",
                [
                    Rule(
                        "znělá labiala",
                        {"cons": "+", "lab": "+", "cont": "-", "voi": "-"},
                        {"voi": "+"},
                        year=1,
                    ),
                ],
            ),
            VerticalEdge("proto", "b", []),
        ],
        contact_edges=[ContactEdge(10, "a", "b", volume=1, adapt=True)],
    )
    states = EvolutionSimulator(graph, mapper).simulate(_root(mapper, [("one", "pata")]))
    loan = next(word for word in states["b"].lexicon.words if word.source_id == "a")
    target_inventory = {
        mapper.segment_to_ipa(segment)
        for word in states["b"].lexicon.words
        if word.source_id is None
        for segment in word.segments
    }
    assert all(mapper.segment_to_ipa(segment) in target_inventory for segment in loan.segments)


def test_paradigma_gramatikalizuje_afix_a_vznika_v_historickem_case(mapper):
    graph = EvolutionGraph(
        node_configs={
            "proto": {},
            "child": {
                "year": 0,
                "morphology": {
                    "grammaticalize": ["plural"],
                    "paradigms": [
                        {
                            "id": "noun",
                            "stem": "tree",
                            "forms": [
                                {
                                    "id": "tree.pl",
                                    "affix": "plural",
                                    "features": {"number": "plural"},
                                }
                            ],
                        }
                    ],
                },
            },
        },
        vertical_edges=[VerticalEdge("proto", "child", [])],
    )
    state = EvolutionSimulator(graph, mapper).simulate(
        _root(mapper, [("tree", "tara"), ("plural", "mi")])
    )["child"]
    plural = state.lexicon.get_word("tree.pl")
    assert plural is not None
    assert plural.paradigm == "noun"
    assert plural.grammatical_features == {"number": "plural"}
    assert plural.origin_year == 1
    plural_word = state.lexicon.get_word("plural")
    assert plural_word is not None
    assert plural_word.is_grammatical


def test_strukturalni_fonologicke_operace(mapper):
    word = mapper.parse_word("x", "pata")
    assert Rule("geminace", {"cons": "+"}, {}, operation="geminate").apply_to_word(word)
    assert mapper.render_word(word) == "ppatta"
    assert Rule("zkrácení", {"syl": "+"}, {}, operation="lengthen").apply_to_word(word)
    assert word.long_nuclei
    assert Rule("metateze", {"cons": "+"}, {}, operation="swap_next").apply_to_word(word)
    assert Rule("přízvuk", {"syl": "+"}, {}, operation="stress_final").apply_to_word(word)
    assert word.stress_index == word.syllable_nuclei()[-1]


def test_taboo_nahrada_a_rozliseni_homofonie_jsou_volitelne(mapper):
    graph = EvolutionGraph(
        node_configs={
            "proto": {},
            "child": {
                "year": 0,
                "lexical": {
                    "enabled": True,
                    "replacement_rate": 0.0,
                    "taboo_concepts": ["fire"],
                    "resolve_homophones": True,
                },
            },
        },
        vertical_edges=[VerticalEdge("proto", "child", [])],
    )
    state = EvolutionSimulator(graph, mapper, end_year=100).simulate(
        _root(mapper, [("fire", "pata"), ("water", "pata"), ("stone", "kumi")])
    )["child"]
    assert any(
        word.origin_type == "taboo_replacement" and word.concept_id == "fire"
        for word in state.lexicon.words
    )
    assert any(word.origin_type == "homophony_resolution" for word in state.lexicon.words)


def test_rozliseni_homofonie_prida_jeden_inventarni_marker_ne_duplikat_korene(mapper):
    graph = EvolutionGraph(
        node_configs={
            "proto": {},
            "child": {
                "year": 0,
                "lexical": {"enabled": True, "replacement_rate": 0.0, "resolve_homophones": True},
            },
        },
        vertical_edges=[VerticalEdge("proto", "child", [])],
    )
    state = EvolutionSimulator(graph, mapper, end_year=100).simulate(
        _root(mapper, [("one", "pata"), ("two", "pata"), ("three", "kumi")])
    )["child"]
    resolved = next(word for word in state.lexicon.words if word.origin_type == "homophony_resolution")

    assert len(resolved.segments) == 5
    assert resolved.morpheme_boundaries == {1}
    assert resolved.origin_rule == "lexical disambiguation prefix"
    active_forms = [mapper.render_word(word) for word in state.lexicon.words if word.active]
    assert len(active_forms) == len(set(active_forms))


def test_kontextova_kolize_ma_nizsi_tlak_nez_stejna_domena(mapper):
    high_a = mapper.parse_word("a", "pata")
    high_b = mapper.parse_word("b", "pata")
    low_a = mapper.parse_word("c", "pata")
    low_b = mapper.parse_word("d", "pata")
    for word in (high_a, high_b, low_a, low_b):
        word.frequency = 0.9
    high_a.grammatical_features = {"lexical.pos": "noun", "lexical.domains": "body"}
    high_b.grammatical_features = {"lexical.pos": "noun", "lexical.domains": "body"}
    low_a.grammatical_features = {"lexical.pos": "noun", "lexical.domains": "body"}
    low_b.grammatical_features = {"lexical.pos": "verb", "lexical.domains": "motion"}

    assert LexicalEvaluator._collision_pressure(high_a, high_b) == 0.9
    assert LexicalEvaluator._collision_pressure(low_a, low_b) < 0.2


def test_socialni_historie_meni_stav_v_konkretnim_roce(mapper):
    graph = EvolutionGraph(
        node_configs={
            "proto": {},
            "child": {
                "year": 0,
                "social_history": [
                    {"year": 80, "changes": {"prestige": 0.9, "standardization": 0.8}}
                ],
            },
        },
        vertical_edges=[VerticalEdge("proto", "child", [])],
    )
    state = EvolutionSimulator(graph, mapper, end_year=100).simulate(
        _root(mapper, [("one", "pata")])
    )["child"]
    assert state.social["prestige"] == 0.9
    assert state.social["standardization"] == 0.8


def test_analogie_se_nepreleva_mezi_paradigmaty(mapper):
    from cee.engine.morphology import MorphologyEvaluator

    state = _root(
        mapper,
        [("noun.model", "pata"), ("noun.rare", "kumi"), ("verb.rare", "seno")],
    )
    noun_model, noun_rare, verb_rare = state.lexicon.words
    noun_model.paradigm = noun_rare.paradigm = "noun"
    verb_rare.paradigm = "verb"
    noun_model.frequency = 0.9
    noun_rare.frequency = verb_rare.frequency = 0.1
    for word in state.lexicon.words:
        word.morpheme_boundaries = {2}
    verb_before = mapper.render_word(verb_rare)

    changed = MorphologyEvaluator().level_analogies(state)

    assert changed == 1
    assert mapper.render_word(verb_rare) == verb_before


def test_prozodicky_export_zobrazi_prizvuk_i_delku(mapper):
    word = mapper.parse_word("word", "pata")
    word.stress_index = 3
    word.long_nuclei = {3}

    assert mapper.render_word(word) == "pataː"
    assert mapper.render_word_prosodic(word) == "patˈaː"


def test_genealogie_uklada_finalni_tvar_po_prosodicke_oprave(mapper):
    from cee.engine.graph_builder import GraphBuilder

    graph = EvolutionGraph(
        node_configs={"proto": {}, "child": {"year": 0}},
        vertical_edges=[
            VerticalEdge(
                "proto",
                "child",
                [
                    Rule(
                        "synkopa",
                        {"syl": "+"},
                        {"delete": "+"},
                        env_before={"cons": "+"},
                        env_after={"cons": "+"},
                        year=50,
                    )
                ],
            )
        ],
    )
    builder = GraphBuilder()
    state = EvolutionSimulator(graph, mapper, graph_builder=builder).simulate(
        _root(mapper, [("word", "kapata")])
    )["child"]
    final_word = state.lexicon.get_word("word")
    assert final_word is not None
    stored = next(node for node in builder.nodes if node["id"] == final_word.id)

    assert stored["ipa"] == mapper.render_word(final_word)
    assert any(event["kind"] == "sound_change" for event in builder.events)


def test_budouci_pravidlo_se_vybira_az_po_vypujcce(mapper):
    """Nový foném z kontaktu musí ovlivnit ještě nevylosovanou fonologii."""
    preset = {
        "schemas": {"final_devoicing": {"base_weight": 1.0}},
        "biomes": {},
        "macro": {"change_rate": 1.0, "conservatism": 0.0, "timing_jitter": 0.0},
    }
    graph = EvolutionGraph(
        node_configs={"proto": {}, "source": {"year": 0}, "target": {"year": 0}},
        vertical_edges=[
            VerticalEdge(
                "proto",
                "source",
                [
                    Rule(
                        "p > b",
                        {"cons": "+", "lab": "+", "cont": "-", "voi": "-"},
                        {"voi": "+"},
                        year=1,
                    )
                ],
            ),
            VerticalEdge("proto", "target", []),
        ],
        contact_edges=[
            __import__("cee.engine.topology", fromlist=["ContactEdge"]).ContactEdge(
                30, "source", "target", volume=1
            )
        ],
    )

    state = EvolutionSimulator(graph, mapper, preset=preset, end_year=100).simulate(
        _root(mapper, [("word", "ap")])
    )["target"]
    loan = next(word for word in state.lexicon.words if word.source_id == "source")

    # V roce 30 vstoupí jako /ab/; finální odznělení se vybere až v
    # pozdějším slotu z inventáře, který už /b/ skutečně obsahuje.
    assert mapper.render_word(loan) == "ap"
