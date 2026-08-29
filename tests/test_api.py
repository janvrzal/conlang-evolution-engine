"""
Testy API vrstvy. Přeskočí se, když není nainstalované extra `ui`
(`pip install -e '.[ui]'`).
"""
import pytest

pytest.importorskip("fastapi")

from cee.api.ports import ENGINE_SIGNATURE, find_free_port, is_port_free  # noqa: E402
from cee.api.server import (  # noqa: E402
    DynamicSimulateRequest,
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

    assert captured_graph.node_configs["hory"]["map"]["biome"] == "hory"
    assert captured_graph.node_configs["prales"]["map"]["biome"] == "prales"


def test_dynamicka_topologie_respektuje_map_i_primo(monkeypatch):
    """Kanonický tvar z YAML (`map`) musí fungovat stejně jako plochý z UI."""
    captured_graph = None
    def mock_run_simulation(lexicon, graph, mapper, config, builder):
        nonlocal captured_graph
        captured_graph = graph
        return {}
        
    monkeypatch.setattr("cee.api.server.run_simulation", mock_run_simulation)
    
    def spustit(nodes):
        run_dynamic_simulation(DynamicSimulateRequest(
            topology_data={
                "nodes": nodes,
                "edges": [{"source": "proto", "target": "hory"}],
            },
            proto_lexicon=PROTO,
            semantics="",
        ))
        return captured_graph

    plochy = spustit({"proto": {}, "hory": {"biome": "hory"}})
    plochy_biome = plochy.node_configs["hory"]["map"]["biome"]
    
    kanonicky = spustit({"proto": {}, "hory": {"map": {"biome": "hory"}}})
    kanonicky_biome = kanonicky.node_configs["hory"]["map"]["biome"]

    assert plochy_biome == kanonicky_biome == "hory"


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
    run_dynamic_simulation(DynamicSimulateRequest(
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
                    "edges": [{"source": "lang-1", "target": "coastal", "type": "straight", "data": {}}],
                },
                {
                    "year": 1000,
                    "nodes": [
                        {"id": "lang-1", "data": {"isProto": True, "year": 0}},
                        {"id": "coastal", "data": {"year": 500}},
                    ],
                    "edges": [{"source": "lang-1", "target": "coastal", "type": "contact", "data": {}}],
                },
            ],
        },
        proto_lexicon=PROTO,
        semantics="",
    ))

    assert any(
        edge.parent_id == "lang-1" and edge.child_id == "coastal"
        for edge in captured_graph.vertical_edges
    )
    assert [(edge.year, edge.source_id, edge.target_id) for edge in captured_graph.contact_edges] == [
        (1000, "lang-1", "coastal")
    ]


def test_health_hlasi_revizi_rozhrani():
    """
    Podle revize klient pozná, že mluví se zastaralým serverem. Bez ní by
    chybějící endpoint vypadal jako holý 404 kdesi v aplikaci.
    """
    from cee.api.ports import API_REVISION

    zdravi = health_check()
    assert zdravi["api_revision"] == API_REVISION
    assert zdravi["version"]


def test_revize_pokryva_soucasne_endpointy():
    """Přidal-li někdo endpoint, musí zvýšit i revizi."""
    from cee.api.ports import API_REVISION
    from cee.api.server import app

    cesty = {r.path for r in app.routes if hasattr(r, "path")}
    assert {"/api/projects", "/api/projects/{project_id}"} <= cesty
    assert API_REVISION >= 3
