from cee.engine.graph_builder import GraphBuilder
from cee.storage.genealogy import FileGenealogyStore, RunNotFoundError


def _graph() -> GraphBuilder:
    graph = GraphBuilder()
    graph.add_word("proto-tree", "TREE", "tara", 0, "proto", ["WOOD"])
    graph.add_word("coastal-tree-early", "TREE", "tara", 500, "coastal", ["WOOD"])
    graph.add_origin_edge("coastal-tree-early", "proto-tree", "inherited")
    graph.add_word(
        "coastal-tree-late",
        "TREE",
        "tora",
        1000,
        "coastal",
        ["WOOD"],
        stress_index=0,
        long_nuclei=[1],
        morpheme_boundaries=[2],
        paradigm="strong",
        grammatical_features={"case": "nom"},
        active=True,
        origin_type="mutated",
    )
    graph.add_origin_edge(
        "coastal-tree-late", "coastal-tree-early", "mutated", "snížení samohlásky"
    )
    return graph


def test_rez_slovnikem_respektuje_rok_a_dedi_predka(tmp_path):
    store = FileGenealogyStore(tmp_path)
    store.save("run-one", _graph())

    early = store.language("run-one", "coastal", 500)
    late = store.language("run-one", "coastal", 1000)

    assert len(early) == len(late) == 1
    assert {key: early[0][key] for key in ("id", "concept_id", "to", "from", "polysemy")} == {
        "id": "coastal-tree-early",
        "concept_id": "TREE",
        "to": "tara",
        "from": "tara",
        "polysemy": ["WOOD"],
    }
    assert {key: late[0][key] for key in ("id", "concept_id", "to", "from", "polysemy")} == {
        "id": "coastal-tree-late",
        "concept_id": "TREE",
        "to": "tora",
        "from": "tara",
        "polysemy": ["WOOD"],
    }


def test_export_a_mazani_jsou_omezene_na_jeden_beh(tmp_path):
    store = FileGenealogyStore(tmp_path)
    store.save("first", _graph())
    store.save("second", _graph())

    store.delete("first")

    assert store.export("second")["run_id"] == "second"
    assert store.export("second")["schema_version"] == 2
    assert store.export("second")["events"] == []
    try:
        store.export("first")
    except RunNotFoundError:
        pass
    else:  # pragma: no cover - zajišťuje srozumitelnou chybu testu
        raise AssertionError("Smazání prvního běhu nemělo ponechat jeho data.")


def test_trace_a_izoglosa_jsou_vazany_na_beh(tmp_path):
    store = FileGenealogyStore(tmp_path)
    store.save("run-one", _graph())

    trace = store.word_trace("run-one", "coastal-tree-late")

    assert [step["form"] for step in trace] == ["tara", "tara", "tora"]
    assert trace[-1]["rule_name"] == "snížení samohlásky"
    assert trace[-1]["stress_index"] == 0
    assert trace[-1]["long_nuclei"] == [1]
    assert trace[-1]["morpheme_boundaries"] == [2]
    assert trace[-1]["paradigm"] == "strong"
    assert trace[-1]["grammatical_features"] == {"case": "nom"}
    assert store.isogloss("run-one", "TREE", 500) == {"proto": "tara", "coastal": "tara"}
