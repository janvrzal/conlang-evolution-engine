"""
Testy API vrstvy. Přeskočí se, když není nainstalované extra `ui`
(`pip install -e '.[ui]'`).
"""

import pytest

pytest.importorskip("fastapi")

from cee.api.ports import ENGINE_SIGNATURE, find_free_port, is_port_free  # noqa: E402
from cee.api.server import (  # noqa: E402
    DynamicSimulateRequest,
    ProtolangRequest,
    generate_protolang,
    health_check,
    run_dynamic_simulation,
)
from cee.storage.genealogy import FileGenealogyStore  # noqa: E402

PROTO = [
    {"id": "vlk", "ipa": "lupu"},
    {"id": "voda", "ipa": "laku"},
    {"id": "strom", "ipa": "petra"},
]


@pytest.fixture(autouse=True)
def localni_uloziste_simulace(tmp_path, monkeypatch):
    """HTTP testy nikdy nezapisují uživatelské běhy do ~/.cee."""
    store = FileGenealogyStore(tmp_path / "runs")
    monkeypatch.setattr("cee.api.server.get_genealogy_store", lambda: store)
    return store


def test_health_nese_podpis_enginu():
    """Podle `engine` pozná frontend CEE od jiné aplikace na stejném portu."""
    assert health_check()["engine"] == ENGINE_SIGNATURE


def test_vychozi_protolexikon_je_kuratorovane_jadro_a_prijme_vlastni_slovo():
    """Nový projekt nesmí tiše vytvořit několik tisíc položek z CLICS4."""
    result = generate_protolang(
        ProtolangRequest(custom_concepts=["skyship", "moonstone"])
    )

    concepts = {word["id"] for word in result["words"]}
    assert result["source"] == "Swadeshovo jádro + rozšířené koncepty"
    assert "water" in concepts
    assert {"skyship", "moonstone"} <= concepts
    assert 100 < len(concepts) < 250


def test_find_free_port_vrati_navazatelny_port():
    port = find_free_port(8000)
    assert is_port_free(port)


def test_find_free_port_preskoci_obsazeny(tmp_path):
    import socket
    from contextlib import closing

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        obsazeny = sock.getsockname()[1]
        assert find_free_port(obsazeny) != obsazeny


def test_biom_z_ui_ovlivni_vysledek(monkeypatch):
    """
    UI posílá konfiguraci uzlu naplocho ({"biome": ...}), zatímco simulátor ji
    čte pod klíčem `map`. Bez normalizace vyšly všechny větve stejně, protože
    se biom ke generátoru vůbec nedostal.
    """
    req = DynamicSimulateRequest(
        topology_data={
            "nodes": {
                "proto": {"biome": "none"},
                "hory": {"biome": "hory"},
                "prales": {"biome": "prales"},
            },
            "edges": [
                {"source": "proto", "target": "hory"},
                {"source": "proto", "target": "prales"},
            ],
        },
        proto_lexicon=PROTO,
        semantics="",
    )

    captured_graph = None

    def mock_run_simulation(lexicon, graph, mapper, config, builder):
        nonlocal captured_graph
        captured_graph = graph
        return {}

    monkeypatch.setattr("cee.api.server.run_simulation", mock_run_simulation)

    result = run_dynamic_simulation(req)
    assert result["status"] == "success"

    assert captured_graph is not None
    assert captured_graph.node_configs["hory"]["map"]["biome"] == "hory"
    assert captured_graph.node_configs["prales"]["map"]["biome"] == "prales"


def test_api_prijme_dva_nezavisle_protojazyky(monkeypatch):
    captured = None

    def mock_run_multiroot(proto_lexicons, graph, mapper, config, builder):
        nonlocal captured
        captured = (proto_lexicons, graph)
        return {}

    monkeypatch.setattr("cee.api.server.run_multiroot_simulation", mock_run_multiroot)
    result = run_dynamic_simulation(
        DynamicSimulateRequest(
            topology_data={
                "nodes": {
                    "proto-a": {"isProto": True, "year": 0},
                    "proto-b": {"isProto": True, "year": 0},
                },
                "edges": [],
            },
            proto_languages=[
                {"id": "proto-a", "lexicon": [{"id": "sun", "ipa": "sula"}]},
                {"id": "proto-b", "lexicon": [{"id": "moon", "ipa": "miko"}]},
            ],
            semantics="",
        )
    )

    assert result["status"] == "success"
    assert captured is not None
    assert set(captured[0]) == {"proto-a", "proto-b"}


def test_dynamicka_topologie_respektuje_map_i_primo(monkeypatch):
    """Kanonický tvar z YAML (`map`) musí fungovat stejně jako plochý z UI."""
    captured_graph = None

    def mock_run_simulation(lexicon, graph, mapper, config, builder):
        nonlocal captured_graph
        captured_graph = graph
        return {}

    monkeypatch.setattr("cee.api.server.run_simulation", mock_run_simulation)

    def spustit(nodes):
        run_dynamic_simulation(
            DynamicSimulateRequest(
                topology_data={
                    "nodes": nodes,
                    "edges": [{"source": "proto", "target": "hory"}],
                },
                proto_lexicon=PROTO,
                semantics="",
            )
        )
        return captured_graph

    plochy = spustit({"proto": {}, "hory": {"biome": "hory"}})
    plochy_biome = plochy.node_configs["hory"]["map"]["biome"]

    kanonicky = spustit({"proto": {}, "hory": {"map": {"biome": "hory"}}})
    kanonicky_biome = kanonicky.node_configs["hory"]["map"]["biome"]

    assert plochy_biome == kanonicky_biome == "hory"


def test_simulace_odmitne_neplatnou_referenci_pred_spustenim():
    """Poškozená topologie nesmí propadnout až do simulátoru."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        run_dynamic_simulation(
            DynamicSimulateRequest(
                topology_data={
                    "snapshots": [{
                        "year": 0,
                        "nodes": [{"id": "proto"}],
                        "edges": [{"source": "proto", "target": "missing", "type": "straight"}],
                    }],
                },
                proto_lexicon=PROTO,
                semantics="",
            )
        )
    assert exc_info.value.status_code == 422
    assert "neexistující ID: missing" in str(exc_info.value.detail)


def test_casova_osa_zachova_dedictvi_jen_v_okamziku_odstepeni(monkeypatch):
    """Pozdější kontakt nesmí přepsat dřívější dědičnou hranu."""
    captured_graph = None

    def mock_run_simulation(lexicon, graph, mapper, config, builder):
        nonlocal captured_graph
        captured_graph = graph
        assert config.root_id == "lang-1"
        assert config.evolve_root is True
        return {}

    monkeypatch.setattr("cee.api.server.run_simulation", mock_run_simulation)
    run_dynamic_simulation(
        DynamicSimulateRequest(
            topology_data={
                "snapshots": [
                    {
                        "year": 0,
                        "nodes": [{"id": "lang-1", "data": {"isProto": True, "year": 0}}],
                        "edges": [],
                    },
                    {
                        "year": 500,
                        "nodes": [
                            {"id": "lang-1", "data": {"isProto": True, "year": 0}},
                            {"id": "coastal", "data": {"year": 500}},
                        ],
                        "edges": [
                            {
                                "source": "lang-1",
                                "target": "coastal",
                                "type": "straight",
                                "data": {},
                            }
                        ],
                    },
                    {
                        "year": 1000,
                        "nodes": [
                            {"id": "lang-1", "data": {"isProto": True, "year": 0}},
                            {"id": "coastal", "data": {"year": 500}},
                        ],
                        "edges": [
                            {"source": "lang-1", "target": "coastal", "type": "contact", "data": {}}
                        ],
                    },
                ],
            },
            proto_lexicon=PROTO,
            semantics="",
        )
    )

    assert captured_graph is not None
    assert any(
        edge.parent_id == "lang-1" and edge.child_id == "coastal"
        for edge in captured_graph.vertical_edges
    )
    assert [
        (edge.year, edge.source_id, edge.target_id) for edge in captured_graph.contact_edges
    ] == [(1000, "lang-1", "coastal")]


def test_health_hlasi_revizi_rozhrani():
    """
    Podle revize klient pozná, že mluví se zastaralým serverem. Bez ní by
    chybějící endpoint vypadal jako holý 404 kdesi v aplikaci.
    """
    from cee.api.ports import API_REVISION

    zdravi = health_check()
    assert zdravi["api_revision"] == API_REVISION
    assert zdravi["version"]


def test_skutecna_simulace_pres_api_ulozi_casovy_rez_a_export(monkeypatch, tmp_path):
    """Integrační kontrakt: UI payload → engine → úložiště → export.

    Na rozdíl od testů normalizace topologie se zde `run_simulation` nemockuje.
    Malý slovník drží test rychlý, ale projde stejnou cestou jako tlačítko
    „Spustit vývoj“ v mapovém editoru.
    """
    from cee.api import runs

    store = FileGenealogyStore(tmp_path / "real-run")
    monkeypatch.setattr("cee.api.server.get_genealogy_store", lambda: store)
    monkeypatch.setattr("cee.api.runs.get_genealogy_store", lambda: store)
    req = DynamicSimulateRequest(
        topology_data={
            "snapshots": [
                {
                    "year": 0,
                    "nodes": [{"id": "proto", "data": {"isProto": True, "year": 0}}],
                    "edges": [],
                },
                {
                    "year": 100,
                    "nodes": [
                        {"id": "proto", "data": {"isProto": True, "year": 0}},
                        {"id": "child", "data": {"year": 100}},
                    ],
                    "edges": [
                        {"source": "proto", "target": "child", "type": "straight", "data": {}}
                    ],
                },
            ]
        },
        proto_lexicon=PROTO,
        semantics="",
        years=100,
        run_id="integration",
        empirical_phonology=False,
    )

    result = run_dynamic_simulation(req)
    assert result == {
        "status": "success",
        "message": "Simulace byla uložena.",
        "run_id": "integration",
        "storage": "file",
    }

    at_start = runs.get_language("integration", "proto", year=0)
    at_end = runs.get_language("integration", "child", year=100)
    exported = runs.export_run("integration")
    assert len(at_start["words"]) == len(PROTO)
    assert len(at_end["words"]) == len(PROTO)
    assert exported["schema_version"] == 3
    assert exported["events"]
    assert "child" in exported["artifacts"]["grammars"]
    trace = runs.get_word_trace("integration", at_end["words"][0]["id"])
    assert trace["status"] == "success"
    assert trace["trace"]

    grammar = runs.get_grammar("integration", "child")
    metrics = runs.get_run_metrics("integration")
    rules = runs.get_edge_rules("integration", "child")
    assert grammar["grammar_md"].startswith("# Gramatika jazyka child")
    assert "sound_changes" in metrics["metrics"]
    assert rules["status"] == "success"


def test_e2e_semanticka_varianta_projde_kontaktem_az_do_exportu(monkeypatch, tmp_path):
    """UI payload → sémantika → kontakt → časový řez → export bez mocku."""
    from cee.api import runs

    store = FileGenealogyStore(tmp_path / "semantic-contact")
    monkeypatch.setattr("cee.api.server.get_genealogy_store", lambda: store)
    monkeypatch.setattr("cee.api.runs.get_genealogy_store", lambda: store)
    req = DynamicSimulateRequest(
        topology_data={
            "snapshots": [
                {
                    "year": 0,
                    "nodes": [
                        {"id": "proto", "data": {"isProto": True, "year": 0}},
                        {"id": "source", "data": {"year": 0}},
                        {"id": "target", "data": {"year": 0}},
                    ],
                    "edges": [
                        {"source": "proto", "target": "source", "type": "straight", "data": {}},
                        {"source": "proto", "target": "target", "type": "straight", "data": {}},
                    ],
                },
                {
                    "year": 367,
                    "nodes": [
                        {"id": "proto", "data": {"isProto": True, "year": 0}},
                        {"id": "source", "data": {"year": 0}},
                        {"id": "target", "data": {"year": 0}},
                    ],
                    "edges": [
                        {"source": "source", "target": "target", "type": "contact", "data": {"calqueRate": 1.0}},
                    ],
                },
            ]
        },
        proto_lexicon=[{"id": "sun", "ipa": "sula", "frequency": 1.0}],
        semantics="",
        years=400,
        run_id="semantic-contact",
        empirical_phonology=False,
    )

    assert run_dynamic_simulation(req)["status"] == "success"
    at_year = runs.get_language("semantic-contact", "target", year=400)
    exported = runs.export_run("semantic-contact")

    assert at_year["words"]
    assert any(event["kind"] == "semantic_change_started" for event in exported["events"])
    assert any(event["kind"] == "semantic_contact_variant" for event in exported["events"])
    assert any(event["kind"] == "contact" for event in exported["events"])


def test_strankovany_slovnik_filtruje_a_omezi_odpoved(monkeypatch, tmp_path):
    """Detail jazyka nesmí kvůli jednomu pohledu posílat celý lexikon."""
    from cee.api import runs
    from cee.engine.graph_builder import GraphBuilder

    store = FileGenealogyStore(tmp_path / "paged-run")
    graph = GraphBuilder()
    for index in range(6):
        graph.add_word(
            f"word-{index}",
            "TREE" if index < 2 else f"CONCEPT-{index}",
            "tara" if index < 2 else f"form-{index}",
            0,
            "proto",
                [],
            grammatical_features={
                "lexical.register": "ritual" if index % 2 else "ordinary",
                "social.group": "city" if index < 3 else "rural",
            },
        )
    store.save("paged", graph)
    monkeypatch.setattr("cee.api.runs.get_genealogy_store", lambda: store)

    result = runs.get_language_page("paged", "proto", limit=2, community="city")

    assert result["total"] == 3
    assert len(result["words"]) == 2
    assert result["next_offset"] == 2
    assert result["facets"]["homonym_forms"] == ["tara"]
    assert result["facets"]["synonym_concepts"] == ["TREE"]


def test_revize_pokryva_soucasne_endpointy():
    """Přidal-li někdo endpoint, musí zvýšit i revizi."""
    from cee.api.ports import API_REVISION
    from cee.api.server import app

    cesty = {r.path for r in app.routes if hasattr(r, "path")}
    assert {"/api/projects", "/api/projects/{project_id}"} <= cesty
    assert API_REVISION >= 3
