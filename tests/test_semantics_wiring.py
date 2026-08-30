"""
Propojení sémantického grafu do enginu: který soubor se skutečně použije
a jestli se cache nepřepisuje mezi různými požadavky.

Bez tohohle by mohl builder v `semantics/builder.py` sestavit dokonalý
kombinovaný CLICS4+DatSemShift graf, a engine by ho stejně nikdy nepoužil —
`resolve_semantics_path`/`build_semantic_evaluator` je poslední krok
integrace, který data skutečně dostane k `SemanticEvaluator`u.
"""

from pathlib import Path

import pytest

import cee.pipeline as pipeline
from cee.pipeline import SimulationConfig, build_semantic_evaluator, resolve_semantics_path


@pytest.fixture(autouse=True)
def izolovana_cache(monkeypatch, tmp_path):
    """
    `_semantic_graph_cache` a "reálný graf" jsou globální/per-machine stav —
    testy si je musí izolovat, jinak by záleželo na tom, co má vývojářův
    stroj zrovna v ~/.cee/semantics/.
    """
    monkeypatch.setattr(pipeline, "_semantic_graph_cache", {})
    fake_real_graph = tmp_path / "nikdy_neexistuje.graphml"
    monkeypatch.setattr(
        pipeline, "default_semantics_paths", lambda: {"out_path": str(fake_real_graph)}
    )
    yield


def test_explicitni_cesta_ma_prednost(tmp_path):
    """Volající, který si sám vybral cestu, ji dostane — i kdyby reálný graf existoval."""
    explicit = tmp_path / "yaml_mock_sample.yaml"
    explicit.write_text("shifts: []\n", encoding="utf-8")

    assert resolve_semantics_path(str(explicit)) == str(explicit)


def test_neexistujici_explicitni_cesta_spadne_na_dalsi_moznost(tmp_path, monkeypatch):
    """Zadaná, ale mrtvá cesta se nepoužije naslepo — resolver hledá dál."""
    real_graph = tmp_path / "graph.graphml"
    real_graph.write_text("<graphml/>", encoding="utf-8")
    monkeypatch.setattr(pipeline, "default_semantics_paths", lambda: {"out_path": str(real_graph)})

    assert resolve_semantics_path("/nikde/neexistuje.yaml") == str(real_graph)


def test_bez_nicoho_pouzije_mock_ze_zabaleneho_balicku():
    path = resolve_semantics_path(None)
    assert path is not None
    assert path.endswith("semantics_mock.yaml")
    assert Path(path).exists()


def test_realny_graf_ma_prednost_pred_mockem(tmp_path, monkeypatch):
    real_graph = tmp_path / "graph.graphml"
    real_graph.write_text("<graphml/>", encoding="utf-8")
    monkeypatch.setattr(pipeline, "default_semantics_paths", lambda: {"out_path": str(real_graph)})

    assert resolve_semantics_path(None) == str(real_graph)


def test_cache_je_klicovana_cestou_ne_globalni(tmp_path):
    """
    Dřív existovala jediná `_global_semantic_graph` proměnná: jakmile se
    jednou načetl libovolný graf, zůstal použitý navždy — i pro požadavek,
    který výslovně chtěl jiný soubor. Cache musí rozlišovat podle cesty.
    """
    yaml_a = tmp_path / "a.yaml"
    yaml_a.write_text("shifts:\n  - source: X\n    target: Y\n    weight: 1.0\n", encoding="utf-8")
    yaml_b = tmp_path / "b.yaml"
    yaml_b.write_text("shifts:\n  - source: P\n    target: Q\n    weight: 1.0\n", encoding="utf-8")

    ev_a = build_semantic_evaluator(SimulationConfig(semantics_path=str(yaml_a)))
    ev_b = build_semantic_evaluator(SimulationConfig(semantics_path=str(yaml_b)))

    assert ev_a is not None and ev_b is not None
    assert ev_a.graph is not ev_b.graph
    assert ev_a.graph.G.has_node("X")
    assert ev_b.graph.G.has_node("P")
    assert not ev_a.graph.G.has_node("P")


def test_stejna_cesta_pouzije_stejny_graf_z_cache(tmp_path):
    yaml_a = tmp_path / "a.yaml"
    yaml_a.write_text("shifts: []\n", encoding="utf-8")

    ev1 = build_semantic_evaluator(SimulationConfig(semantics_path=str(yaml_a)))
    ev2 = build_semantic_evaluator(SimulationConfig(semantics_path=str(yaml_a)))

    assert ev1 is not None and ev2 is not None
    assert ev1.graph is ev2.graph  # stejný objekt, ne jen rovnocenná data


def test_neplatny_graf_varuje_a_nezastavi_beh(tmp_path):
    spatny = tmp_path / "spatny.graphml"
    spatny.write_text("tohle není platný GraphML", encoding="utf-8")

    with pytest.warns(UserWarning, match="se nepodařilo načíst"):
        result = build_semantic_evaluator(SimulationConfig(semantics_path=str(spatny)))

    assert result is None
