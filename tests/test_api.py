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

PROTO = [
    {"id": "vlk", "ipa": "lupu"},
    {"id": "voda", "ipa": "laku"},
    {"id": "strom", "ipa": "petra"},
]


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


def test_biom_z_ui_ovlivni_vysledek():
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

    result = run_dynamic_simulation(req)
    assert result["status"] == "success"

    hory = [w["ipa"] for w in result["branches"]["hory"]["words"]]
    prales = [w["ipa"] for w in result["branches"]["prales"]["words"]]

    assert hory != prales, "Biom se neprojevil — konfigurace uzlu se nedostala do state.map."


def test_dynamicka_topologie_respektuje_map_i_primo():
    """Kanonický tvar z YAML (`map`) musí fungovat stejně jako plochý z UI."""
    def spustit(nodes):
        return run_dynamic_simulation(DynamicSimulateRequest(
            topology_data={
                "nodes": nodes,
                "edges": [{"source": "proto", "target": "hory"}],
            },
            proto_lexicon=PROTO,
            semantics="",
        ))["branches"]["hory"]["words"]

    plochy = spustit({"proto": {}, "hory": {"biome": "hory"}})
    kanonicky = spustit({"proto": {}, "hory": {"map": {"biome": "hory"}}})

    assert [w["ipa"] for w in plochy] == [w["ipa"] for w in kanonicky]


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
    assert {"/api/evolve", "/api/projects", "/api/projects/{project_id}"} <= cesty
    assert API_REVISION >= 3
