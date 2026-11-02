"""Velikost slovníku a vlastní pojmy (``cee.v2.vocabulary``, ``WorldSpec.vocabulary``, ``concepts``)."""

import json

import pytest

from cee.v2 import concept_data, vocabulary
from cee.v2.changes.base import InnovationContext
from cee.v2.changes.lexicon import Derivation, SemanticShift
from cee.v2.language.constructions import GRAMMATICAL_SOURCES
from cee.v2.scenarios import DEFAULT_CONCEPTS, word_class
from cee.v2.semantics import core_graph
from cee.v2.simulation import Simulation
from cee.v2.spec import ConceptSpec, WorldSpec, build, check, errors, vocabulary_options, warnings

#: Otisk historie světa `small` s výchozím slovníkem, změřený před zavedením slovníku
#: (tóny, vlastní slovo, plná gramatika, 500 let).
DEFAULT_DIGEST = "af9bf815cc7db8a009b97719ddfce0a3c7141344a538e50f25fd440b41c5de56"


def small(**extra):
    spec = {
        "seed": 3, "end_year": 120,
        "languages": [{"id": "a"}],
        "regions": [{"id": "r1", "position": [0, 0], "villages": 1}],
    }
    spec.update(extra)
    return spec


def test_vychozi_svet_ze_specifikace_ma_stejny_otisk_jako_pred_slovnikem():
    data = {
        "seed": 3, "end_year": 500,
        "languages": [{"id": "a"}, {"id": "b", "grammar": "full", "tones": ["˥", "˩"], "words": {"hand": "ruka"}}],
        "regions": [
            {"id": "r1", "position": [0, 0], "neighbours": ["r2"], "villages": 3, "language": "a"},
            {"id": "r2", "position": [50, 0], "neighbours": ["r1"], "villages": 3, "language": "b"},
        ],
    }
    world, events, spec = build(data)
    simulation = Simulation(world, events=events)
    simulation.run(spec.end_year)
    assert simulation.history.digest() == DEFAULT_DIGEST
    assert check(data) == []


def test_vychozi_slovnik_je_dnesni():
    default = vocabulary.resolve()
    assert default.is_default and default.graph() is core_graph()
    assert default.ids == (*DEFAULT_CONCEPTS, *GRAMMATICAL_SOURCES)
    assert default.word_classes() == {concept: word_class(concept) for concept in default.ids}
    assert default.known_frequencies() == {}
    assert default.domain("king") == "power" and default.concept("go").frequency is None
    # Zdroje gramatikalizace nemají data; frekvenci jim vygeneruje protojazyk jako dřív.
    assert default.concept("go").origin == "engine" and default.concept("hand").origin == "default"


def test_vetsi_slovnik_je_zacatkem_dalsiho_a_nemeni_poradi_stavajicich_pojmu():
    sizes = [vocabulary.resolve(size).ids for size in (149, 200, 500, 1000)]
    for smaller, larger in zip(sizes, sizes[1:]):
        assert larger[:len(smaller)] == smaller
    assert [len(ids) for ids in sizes] == [155, 206, 506, 1006]
    assert len(set(sizes[-1])) == len(sizes[-1])
    assert sizes[1][155:161] == concept_data.catalog_order()[:6]
    assert len(vocabulary.resolve(vocabulary.max_size()).ids) == vocabulary.max_size() + 6


def test_poradi_pojmu_nezavisi_na_poradi_vlastnich_pojmu():
    first = vocabulary.CustomConcept("b-pojem"), vocabulary.CustomConcept("a-pojem")
    assert vocabulary.resolve(200, first).ids == vocabulary.resolve(200, first[::-1]).ids
    assert vocabulary.resolve(200, first).ids[-2:] == ("a-pojem", "b-pojem")
    assert vocabulary.resolve(200, first).ids[:-2] == vocabulary.resolve(200).ids


def test_pojmy_katalogu_maji_slovni_druh_podle_kategorie_wold():
    big = vocabulary.resolve(1000)
    classes = big.word_classes()
    for concept in big.concepts:
        if concept.origin == "catalog":
            category = concept_data.info(concept.id)["category"]
            expected = {"Noun": "noun", "Verb": "verb"}.get(category)
            assert classes[concept.id] == expected
    assert classes["hand"] == "noun" and classes["eat"] == "verb" and classes["big"] is None
    assert big.concept("and").word_class == "uninflected" and big.concept("sing").word_class == "verb"
    assert big.concept("sky").word_class == "noun"
    # Výchozí pojmy si ponechají zatřídění z ručních množin.
    assert all(classes[concept] == word_class(concept) for concept in DEFAULT_CONCEPTS)


def test_vlastni_pojem_bez_dat_dostane_vychozi_hodnoty_a_zapamatuje_si_je():
    found = vocabulary.resolve(149, [vocabulary.CustomConcept("zork")]).concept("zork")
    assert found.domain == "core" and found.word_class == "noun" and found.origin == "custom"
    assert found.frequency == concept_data.mean_frequency()
    assert found.borrowed == concept_data.mean_borrowed()
    assert found.defaulted == ("domain", "borrowed", "frequency", "word_class")
    religion = vocabulary.resolve(149, [vocabulary.CustomConcept("zork", domain="religion")]).concept("zork")
    assert religion.frequency == concept_data.mean_frequency("religion")
    assert religion.borrowed == concept_data.mean_borrowed("religion") and "domain" not in religion.defaulted


def test_vlastni_pojem_s_vazbou_prevezme_data_a_zadane_hodnoty_maji_prednost():
    linked = vocabulary.resolve(149, [vocabulary.CustomConcept("rozhlas", wold="23-1")]).concept("rozhlas")
    item = concept_data.find(wold="23-1")
    assert (linked.domain, linked.borrowed) == (item["domain"], item["borrowed"])
    assert linked.frequency == concept_data.item_frequency(item) and linked.defaulted == ()
    by_gloss = vocabulary.resolve(149, [vocabulary.CustomConcept("noha", gloss="leg")]).concept("noha")
    assert by_gloss.wold_id == "4-35" and by_gloss.domain == "core" and by_gloss.defaulted == ()
    verb = vocabulary.resolve(149, [vocabulary.CustomConcept("ucit", concepticon=concept_data.find(gloss="teach")["concepticon_id"])])
    assert verb.concept("ucit").word_class == "verb"
    own = vocabulary.CustomConcept("rozhlas", wold="23-1", domain="power", frequency=0.8, borrowed=0.1,
                                   word_class="verb")
    chosen = vocabulary.resolve(149, [own]).concept("rozhlas")
    assert (chosen.domain, chosen.frequency, chosen.borrowed, chosen.word_class) == ("power", 0.8, 0.1, "verb")
    assert chosen.defaulted == ()
    # ID pojmu katalogu mimo vybraný slovník je totéž, co vazba na jeho význam.
    same = vocabulary.resolve(149, [vocabulary.CustomConcept("snake")]).concept("snake")
    assert same.wold_id == concept_data.catalog_ids()["snake"]["wold_id"] and same.defaulted == ()


def test_overeni_zamita_nesmysly_s_cestou_k_poli():
    custom = [
        vocabulary.CustomConcept("hand"),
        vocabulary.CustomConcept("x"), vocabulary.CustomConcept("x"),
        vocabulary.CustomConcept("y", domain="nic", frequency=2.0, borrowed=3.0, word_class="adverb"),
        vocabulary.CustomConcept("z", wold="1-99999"),
        vocabulary.CustomConcept("w", wold="4-35", concepticon=1297),
        vocabulary.CustomConcept("v", concepticon=999999),
        vocabulary.CustomConcept("ne mezery"),
        vocabulary.CustomConcept("u", related=(
            vocabulary.Related("u"), vocabulary.Related("neexistuje"), vocabulary.Related("hand", kind="nic"),
            vocabulary.Related("hand", direction="nahoru"), vocabulary.Related("hand", weight=0),
            vocabulary.Related("sun"), vocabulary.Related("sun"))),
    ]
    found = {problem.path: problem.message for problem in vocabulary.validate(149, custom) if problem.severity == "error"}
    assert "už ve slovníku" in found["concepts.0.id"]
    assert "vícekrát" in found["concepts.2.id"]
    assert "neznámá doména" in found["concepts.3.domain"]
    assert "frekvence" in found["concepts.3.frequency"] and "půjčitelnost" in found["concepts.3.borrowed"]
    assert "slovní druh" in found["concepts.3.word_class"]
    assert "neznámý význam WOLD" in found["concepts.4.wold"]
    assert "jen jednu vazbu" in found["concepts.5"] and "Concepticon" in found["concepts.6.concepticon"]
    assert "ID smí" in found["concepts.7.id"]
    assert "sám sobě" in found["concepts.8.related.0.concept"]
    assert "neznámý pojem" in found["concepts.8.related.1.concept"]
    assert "druh vztahu" in found["concepts.8.related.2.kind"] and "směr" in found["concepts.8.related.3.direction"]
    assert "váha" in found["concepts.8.related.4.weight"] and "vícekrát" in found["concepts.8.related.6"]
    with pytest.raises(ValueError, match="vícekrát"):
        vocabulary.resolve(149, custom)
    for size in (100, 148, vocabulary.max_size() + 1):
        assert vocabulary.validate(size)[0].path == "vocabulary"


def test_pojem_katalogu_mimo_slovnik_nejde_jako_pribuzny_ale_ve_vetsim_ano():
    custom = [vocabulary.CustomConcept("drak", related=(vocabulary.Related("snake"),))]
    found = vocabulary.validate(149, custom)
    assert any("větším slovníku" in problem.message for problem in found if problem.severity == "error")
    assert not [problem for problem in vocabulary.validate(500, custom) if problem.severity == "error"]


def test_varovani_ze_jiny_slovnik_da_jine_vysledky():
    assert vocabulary.validate() == []
    assert [problem.path for problem in vocabulary.validate(200)] == ["vocabulary"]
    assert vocabulary.validate(200)[0].severity == "warning"
    dup = vocabulary.validate(149, [vocabulary.CustomConcept("rozhlas", wold="23-1"),
                                    vocabulary.CustomConcept("rozhlas-2", wold="23-1")])
    assert any(problem.path == "concepts" for problem in dup)
    # Stejný význam podruhé je jen varování, ne chyba.
    twin = vocabulary.validate(149, [vocabulary.CustomConcept("paw", wold="4-35")])
    assert any("stejný význam" in problem.message and problem.severity == "warning" for problem in twin)
    assert not [problem for problem in twin if problem.severity == "error"]


def test_graf_vychozich_pojmu_zustane_i_ve_vetsim_slovniku():
    core = {(item.source, item.target): item for item in core_graph().relations}
    graph = vocabulary.resolve(500).graph()
    inside = {(item.source, item.target): item for item in graph.relations}
    for pair, relation in core.items():
        assert inside[pair] == relation
    assert len(inside) > len(core)
    assert graph.compounds == core_graph().compounds
    ids = set(vocabulary.resolve(500).ids)
    assert all(item.source in ids and item.target in ids for item in graph.relations)
    # Vztahy nových pojmů jsou z dat: tělesné části vzdálené od výchozího řezu se vážou.
    assert any(item.source in concept_data.catalog_ids() or item.target in concept_data.catalog_ids()
               for item in graph.relations)


def test_pribuzne_pojmy_vlastniho_pojmu_tvori_vztahy_se_smerem_a_vahou():
    custom = vocabulary.CustomConcept("drak", related=(
        vocabulary.Related("snake"),
        vocabulary.Related("fire", kind="derivation"),
        vocabulary.Related("sun", kind="colexification", weight=20),
        vocabulary.Related("bird", direction="to", weight=7),
        vocabulary.Related("water", direction="from", kind="derivation", weight=5),
    ))
    graph = vocabulary.resolve(500, [custom]).graph()
    found = {(item.source, item.target): item for item in graph.relations}
    assert found["snake", "drak"].polysemy == 2 and found["drak", "snake"].polysemy == 2
    assert found["fire", "drak"].derivation == 2 and ("drak", "fire") not in found
    assert found["sun", "drak"].colexification == 20 == found["drak", "sun"].colexification
    assert found["drak", "bird"].polysemy == 7 and ("bird", "drak") not in found
    assert found["water", "drak"].derivation == 5
    assert found["snake", "drak"].shift_weight > 0 and found["fire", "drak"].derivation_weight > 0
    # Zadaná váha má u dvojice a druhu vztahu přednost před daty.
    data = {(item.source, item.target): item for item in vocabulary.resolve(500).graph().relations}
    pair = next(pair for pair, item in data.items() if item.polysemy and "snake" not in pair and pair[0] != pair[1]
                and pair[0] in DEFAULT_CONCEPTS and pair[1] in vocabulary.resolve(500).ids)
    forced = vocabulary.CustomConcept("x", related=(vocabulary.Related(pair[0], weight=99),))
    assert {(item.source, item.target): item for item in
            vocabulary.resolve(500, [forced]).graph().relations}[pair[0], "x"].polysemy == 99


def test_vlastni_pojem_s_vazbou_dostane_vztahy_z_dat():
    graph = vocabulary.resolve(149, [vocabulary.CustomConcept("noha", gloss="leg")]).graph()
    # `leg` je pojem enginu: vlastní pojem se stejným významem zdědí jeho vztahy k ostatním.
    mine = {(item.source, item.target) for item in graph.relations if "noha" in (item.source, item.target)}
    assert mine and all(pair[0] != pair[1] for pair in mine)
    assert not vocabulary.resolve(149, [vocabulary.CustomConcept("zork")]).graph().into("zork")


def test_slovnik_o_500_pojmech_a_vlastni_pojem_je_ve_svete():
    custom = [{
        "id": "drak", "gloss": "dragon", "domain": "religion", "frequency": 0.3, "word_class": "noun",
        "related": [{"concept": "snake"}, {"concept": "fire", "kind": "derivation"}],
    }, {"id": "noha", "gloss": "leg"}, {"id": "zork"}]
    data = small(vocabulary=500, concepts=custom)
    issues = check(data)
    assert not errors(issues) and {issue.path for issue in warnings(issues)} == {"vocabulary", "concepts", "concepts.1"}
    world, events, spec = build(data)
    # Vlastní pojem je ve slovní zásobě, má frekvenci a doménu.
    assert "drak" in world.concept_classes and world.concept_frequencies["drak"] == 0.3
    assert world.vocabulary.domain("drak") == "religion" and world.vocabulary.domain("king") == "power"
    assert world.concept_frequencies["zork"] == concept_data.mean_frequency()
    assert world.concept_frequencies["noha"] == concept_data.frequency("leg")
    assert len(world.concept_frequencies) == 509
    assert any(item.meaning == "drak" for item in world.morphemes.values())
    group = world.groups[world.group_ids()[0]]
    assert group.main_code.phonology is not None
    # ...a při zadaných příbuzných pojmech i posuny významu a odvození.
    simulation = Simulation(world, events=events)
    context = InnovationContext(world, group, group.main_code, 1, 25.0)
    assert {option["from"] for _, option in SemanticShift().options(context, "drak")} == {"snake"}
    assert {option["from"] for _, option in Derivation().options(context, "drak")} == {"fire"}
    assert "drak" in {option["from"] for _, option in SemanticShift().options(context, "snake")}
    simulation.run(spec.end_year)
    assert simulation.history.digest()


def test_slovnik_o_500_pojmech_probehne_a_je_deterministicky():
    digests = []
    for _ in range(2):
        world, events, spec = build(small(vocabulary=500, end_year=200, regions=[
            {"id": "r1", "position": [0, 0], "villages": 2, "neighbours": ["r2"]},
            {"id": "r2", "position": [40, 0], "villages": 2, "neighbours": ["r1"]}]))
        simulation = Simulation(world, events=events)
        simulation.run(spec.end_year)
        digests.append(simulation.history.digest())
    assert digests[0] == digests[1]
    default, _, _ = build(small(end_year=200))
    assert len(default.concept_frequencies) == 155 and len(world.concept_frequencies) == 506


def test_stavajici_slova_se_ve_vetsim_slovniku_nepreloseji():
    small_world, _, _ = build(small(vocabulary=149))
    big_world, _, _ = build(small(vocabulary=500))
    forms = lambda world: {item.meaning: item.form for item in world.morphemes.values()}  # noqa: E731
    first, second = forms(small_world), forms(big_world)
    assert first and all(second[concept] == form for concept, form in first.items())
    # Frekvence pojmů s daty se nemění; generované (zdroje gramatikalizace) mohou.
    for concept in DEFAULT_CONCEPTS:
        assert small_world.concept_frequencies[concept] == big_world.concept_frequencies[concept]


def test_specifikace_zamita_nesmyslne_vstupy():
    def paths(**extra):
        return {issue.path: issue.message for issue in errors(check(small(**extra)))}

    assert "aspoň 149" in paths(vocabulary=100)["vocabulary"]
    assert "149 až" in paths(vocabulary=100000)["vocabulary"]
    assert "musí být jedna z možností" in paths(concepts=[{"id": "a", "domain": "nic"}])["concepts.0.domain"]
    assert "nejvýš" in paths(concepts=[{"id": "a", "frequency": 5}])["concepts.0.frequency"]
    assert "aspoň" in paths(concepts=[{"id": "a", "frequency": 0.001}])["concepts.0.frequency"]
    assert "vícekrát" in paths(concepts=[{"id": "a"}, {"id": "a"}])["concepts.1.id"]
    assert "už ve slovníku" in paths(concepts=[{"id": "water"}])["concepts.0.id"]
    assert "neznámý pojem" in paths(concepts=[{"id": "a", "related": [{"concept": "nic"}]}])["concepts.0.related.0.concept"]
    assert "smí obsahovat" in paths(concepts=[{"id": "a b"}])["concepts.0.id"]
    assert "neznámé pole" in paths(concepts=[{"id": "a", "foo": 1}])["concepts.0.foo"]
    assert "neznámý pojem" in paths(concepts=[{"id": "a"}], languages=[{"id": "a", "words": {"b": "ta"}}])[
        "languages.0.words.b"]
    with pytest.raises(Exception, match="concepts.0.domain"):
        build(small(concepts=[{"id": "a", "domain": "nic"}]))


def test_autor_muze_zadat_slovo_a_jmeno_jazyka_z_vlastniho_pojmu():
    data = small(concepts=[{"id": "drak"}], languages=[{"id": "a", "words": {"drak": "zmaj"}, "endonym": ["drak"]}])
    assert errors(check(data)) == []
    world, _, _ = build(data)
    assert any(world.table.render(item.form) == "zmaj" for item in world.morphemes.values() if item.meaning == "drak")


def test_varovani_nezastavi_stavbu_a_semantika_bez_grafu_to_oznami():
    data = small(vocabulary=200, semantics=False, concepts=[{"id": "a", "related": [{"concept": "fire"}]}])
    issues = check(data)
    assert not errors(issues) and any(issue.path == "semantics" for issue in warnings(issues))
    assert all(issue.severity == "warning" for issue in issues)
    build(data)


def test_schema_a_moznosti_slovniku_pro_ui():
    schema = json.dumps(WorldSpec.model_json_schema())
    for name in ("vocabulary", "ConceptSpec", "RelatedSpec", "colexification"):
        assert name in schema
    options = vocabulary_options()
    assert options["default"] == 149 and options["max"] == vocabulary.max_size() == 1453
    assert options["domains"] == list(concept_data.DOMAINS)
    assert set(ConceptSpec.model_json_schema()["properties"]["domain"]["anyOf"][0]["enum"]) == set(concept_data.DOMAINS)
    assert ConceptSpec(id="a").custom() == vocabulary.CustomConcept("a")


def test_datovy_soubor_semantiky_katalogu_nese_citace_licence_a_otisky():
    data = vocabulary.catalog_semantics()
    assert {source["license"] for source in data["sources"]} == {"CC-BY-4.0"}
    assert all(source["citation"] and source["sha256"] for source in data["sources"])
    assert all(len(row) == 5 and row[0] != row[1] for row in data["relations"])
    assert len(data["relations"]) > 5000 and set(data["aliases"]) <= set(DEFAULT_CONCEPTS)
    assert vocabulary.CATALOG_SEMANTICS.stat().st_size < 2_000_000
