"""
Stavba kombinovaného sémantického grafu z CLICS4 + DatSemShift
(CEE_master.md 4.7).

Fixtures jsou syntetické a malé (`tests/fixtures/clics4_sample.gml`,
`datsemshift_sample.csv`), ale ve stejném formátu jako skutečná data —
podle AGENT.md se ta reálná (desítky/stovky MB) do gitu necommitují.

Testy pokrývají dvě chyby, které builder reálně měl:

1. **Váha CLICS hrany byla skoro vždy 0.** Kód četl neexistující pole
   `weight`, spadl na string `families` a odhadoval váhu jako
   `len(families.split('//')) // 2` — u typické (jednorodinné) hrany bez
   `//` to dá `1 // 2 == 0`. Whitepaper (4.7) přitom váhu definuje jako
   *počet jazyků*, což je pole `language_count`, přímo dostupné a čisté.

2. **CLICS4 a DatSemShift se nikdy nepotkaly.** CLICS4 GML nemá žádné
   číselné `concepticon_id` na uzlech — uzel je klíčovaný anglickým glosem
   (`WORLD`). DatSemShift naopak používal číselné `Concepticon_ID`. Dva
   různé klíčové prostory ve stejném `networkx.DiGraph` znamenají dva
   nespojené podgrafy, ne jeden kombinovaný.
"""

from pathlib import Path

import networkx as nx

from cee.semantics.builder import (
    _add_or_merge_edge,
    _load_clics4,
    _load_datsemshift,
    build_combined_semantic_graph,
    normalize_gloss,
)
from cee.semantics.graph import SemanticGraph

FIXTURES = Path(__file__).parent / "fixtures"
CLICS4_SAMPLE = FIXTURES / "clics4_sample.gml"
DATSEMSHIFT_SAMPLE = FIXTURES / "datsemshift_sample.csv"


def test_normalize_gloss():
    assert normalize_gloss("world") == "WORLD"
    assert normalize_gloss("  Fan (Object) ") == "FAN (OBJECT)"


def test_lexikalni_zakladna_pokryje_vsechny_koncepty_a_uzije_kolexifikaci():
    graph = SemanticGraph.__new__(SemanticGraph)
    graph.G = nx.DiGraph()
    graph.G.add_edge("SUN", "DAY", type="colexification", weight=5)
    graph.G.add_edge("DAY", "SUN", type="colexification", weight=5)
    graph.G.add_node("MOON")

    entries = graph.lexical_entries()
    covered = {entry["id"] for entry in entries}
    covered.update(meaning for entry in entries for meaning in entry["polysemy"])

    assert covered == {"sun", "day", "moon"}
    assert any(entry["id"] == "day" and entry["polysemy"] == ["sun"] for entry in entries)


class TestLoadClics4:
    def test_vaha_je_pocet_jazyku_ne_pocet_rodin_deleny_dvema(self):
        """
        FAMILY<->CHILD má v CLICS fixture jedinou rodinu ('taik1256', bez
        '//') a language_count=3. Stará heuristika `families.split('//')//2`
        by z jedné rodiny bez oddělovače udělala váhu 0 — přesně bug, který
        v reálných datech postihl většinu hran.
        """
        G = nx.DiGraph()
        _load_clics4(G, str(CLICS4_SAMPLE))

        assert G["FAMILY"]["CHILD"]["weight"] == 3
        assert G["CHILD"]["FAMILY"]["weight"] == 3

    def test_kolexifikace_jde_oboustranne(self):
        G = nx.DiGraph()
        _load_clics4(G, str(CLICS4_SAMPLE))

        assert G.has_edge("WORLD", "LAND")
        assert G.has_edge("LAND", "WORLD")
        assert G["WORLD"]["LAND"]["type"] == "colexification"
        assert G["WORLD"]["LAND"]["weight"] == 5  # language_count z fixture

    def test_uzly_klicovane_glosem_ne_ciselnym_id(self):
        """CLICS4 nemá concepticon_id — bez normalizace glosu není co sdílet."""
        G = nx.DiGraph()
        _load_clics4(G, str(CLICS4_SAMPLE))

        assert set(G.nodes) == {"WORLD", "LAND", "FAMILY", "CHILD"}


class TestLoadDatSemShift:
    def test_uzel_klicovany_concepticon_glosem_ne_id(self):
        """
        Klíčování podle Concepticon_ID by se s CLICS4 (klíčovaným glosem)
        nikdy nepotkalo — dva podgrafy ve stejném objektu, ne jeden graf.
        """
        G = nx.DiGraph()
        _load_datsemshift(G, str(DATSEMSHIFT_SAMPLE))

        assert "FAMILY" in G.nodes
        assert "CHILD" in G.nodes
        assert "194" not in G.nodes  # číselné Concepticon_ID není klíč uzlu

    def test_koncept_bez_glosu_zustava_pod_vlastnim_lokalnim_id(self):
        G = nx.DiGraph()
        _load_datsemshift(G, str(DATSEMSHIFT_SAMPLE))

        assert "3000_localonly" in G.nodes

    def test_target_concepts_da_orientovanou_shift_hranu(self):
        G = nx.DiGraph()
        _load_datsemshift(G, str(DATSEMSHIFT_SAMPLE))

        assert G.has_edge("FAMILY", "CHILD")
        assert G["FAMILY"]["CHILD"]["type"] == "shift"
        assert G["FAMILY"]["CHILD"]["weight"] == 5  # PolysemyByFamily(4) + DerivationByFamily(1)
        # DatSemShift je orientovaný (4.7) — opačný směr shift nevytváří.
        assert not G.has_edge("CHILD", "FAMILY")

    def test_linked_concepts_da_obousmernou_kolexifikaci(self):
        G = nx.DiGraph()
        _load_datsemshift(G, str(DATSEMSHIFT_SAMPLE))

        assert G.has_edge("FAMILY", "3000_localonly")
        assert G.has_edge("3000_localonly", "FAMILY")
        assert G["FAMILY"]["3000_localonly"]["type"] == "colexification"


class TestAddOrMergeEdge:
    def test_sama_na_sebe_se_ignoruje(self):
        G = nx.DiGraph()
        _add_or_merge_edge(G, "X", "X", 5, "colexification")
        assert G.number_of_edges() == 0

    def test_druhy_vpis_secte_vahu(self):
        G = nx.DiGraph()
        _add_or_merge_edge(G, "A", "B", 3, "colexification")
        _add_or_merge_edge(G, "A", "B", 4, "colexification")
        assert G["A"]["B"]["weight"] == 7

    def test_shift_prebiji_typ_existujici_kolexifikace(self):
        G = nx.DiGraph()
        _add_or_merge_edge(G, "A", "B", 3, "colexification")
        _add_or_merge_edge(G, "A", "B", 2, "shift")
        assert G["A"]["B"]["type"] == "shift"
        assert G["A"]["B"]["weight"] == 5

    def test_kolexifikace_neprebiji_existujici_shift(self):
        G = nx.DiGraph()
        _add_or_merge_edge(G, "A", "B", 3, "shift")
        _add_or_merge_edge(G, "A", "B", 2, "colexification")
        assert G["A"]["B"]["type"] == "shift"


class TestCombinedGraph:
    """Konec-konců: CLICS4 a DatSemShift v jednom grafu, ne vedle sebe."""

    def test_koncept_sdileny_obema_zdroji_ma_hrany_z_obou(self, tmp_path):
        out = tmp_path / "combined.graphml"
        G = build_combined_semantic_graph(str(DATSEMSHIFT_SAMPLE), str(CLICS4_SAMPLE), str(out))

        types_out = {d["type"] for _, _, d in G.out_edges("FAMILY", data=True)}
        assert "colexification" in types_out  # z CLICS4 (FAMILY<->3000_localonly) i DatSemShift
        assert "shift" in types_out  # z DatSemShift (Target_Concepts)

    def test_clics_hrana_prezije_sloučeni_se_shift_hranou(self, tmp_path):
        """
        FAMILY->CHILD existuje v obou zdrojích: CLICS dá colexification
        (váha 3), DatSemShift dá shift (váha 5). Po sloučení musí zůstat
        JEDNA hrana se součtem vah a typem 'shift' (4.7: orientovaný posun
        je specifičtější informace než symetrická kolexifikace).
        """
        out = tmp_path / "combined.graphml"
        G = build_combined_semantic_graph(str(DATSEMSHIFT_SAMPLE), str(CLICS4_SAMPLE), str(out))

        assert G["FAMILY"]["CHILD"]["type"] == "shift"
        assert G["FAMILY"]["CHILD"]["weight"] == 8

    def test_graf_se_ulozi_a_nacte_pres_semanticgraph(self, tmp_path):
        out = tmp_path / "combined.graphml"
        build_combined_semantic_graph(str(DATSEMSHIFT_SAMPLE), str(CLICS4_SAMPLE), str(out))

        sg = SemanticGraph(str(out))
        shifts = sg.get_possible_shifts("FAMILY")
        assert shifts, "SemanticGraph nenačetl žádné hrany z uloženého kombinovaného grafu."

        only_shift = sg.random_shift("FAMILY", edge_type="shift")
        assert only_shift == "CHILD"

    def test_chybejici_zdrojove_soubory_nespadnou(self, tmp_path):
        out = tmp_path / "empty.graphml"
        G = build_combined_semantic_graph(
            str(tmp_path / "nic.csv"), str(tmp_path / "nic.gml"), str(out)
        )
        assert G.number_of_nodes() == 0
        assert out.exists()

    def test_malymi_pismeny_zadane_concept_id_najde_velkymi_klicovany_uzel(self, tmp_path):
        """
        `concepts.json` (skutečný zdroj proto-lexikonu) dává concept_id
        malými písmeny ("tree"), builder ale uzly klíčuje normalizovaným
        (velkými písmeny) glosem ("TREE"). Bez sjednocení v `SemanticGraph`
        by `has_node("tree")` bylo vždy False a sémantika by nic nedělala,
        i když je graf sestavený úplně správně.
        """
        out = tmp_path / "combined.graphml"
        build_combined_semantic_graph(str(DATSEMSHIFT_SAMPLE), str(CLICS4_SAMPLE), str(out))

        sg = SemanticGraph(str(out))
        assert sg.get_possible_shifts("family") == sg.get_possible_shifts("FAMILY")
        assert sg.random_shift("family", edge_type="shift") == "CHILD"


class TestSemanticGraphCaseNormalization:
    """
    `SemanticGraph` musí case-insensitive porovnávat, ať data přijdou
    z GraphML (CLICS4/DatSemShift, klíčováno velkými písmeny) nebo z YAML
    mocku (typicky malými písmeny) — a `concept_id` v proto-lexikonu bývá
    malými písmeny (`concepts.json`).
    """

    def test_yaml_mock_normalizuje_casing(self, tmp_path):
        mock = tmp_path / "mock.yaml"
        mock.write_text(
            "shifts:\n  - source: sun\n    target: sky\n    weight: 1.0\n",
            encoding="utf-8",
        )
        sg = SemanticGraph(str(mock))

        assert sg.get_possible_shifts("sun") == sg.get_possible_shifts("SUN")
        assert sg.get_possible_shifts("Sun") == sg.get_possible_shifts("sun")

    def test_bundleovany_mock_pouziva_concepts_json_slovnik(self):
        """
        Zabalený `semantics_mock.yaml` je fallback pro čerstvý klon/CI bez
        cache reálného grafu — pokud by mluvil jiným slovníkem než
        `concepts.json` (dřív česky: "slunce", "voda"...), fallback by
        nikdy nic neudělal, stejně jako chybějící reálný graf.
        """
        mock_path = Path(__file__).parent.parent / "src" / "cee" / "data" / "semantics_mock.yaml"
        sg = SemanticGraph(str(mock_path))

        import json

        concepts_path = Path(__file__).parent.parent / "src" / "cee" / "data" / "concepts.json"
        concept_ids = {c["id"] for c in json.loads(concepts_path.read_text(encoding="utf-8"))}

        assert any(sg.get_possible_shifts(cid) for cid in concept_ids), (
            "Žádný koncept z concepts.json nemá v mocku odchozí posun — "
            "fallback graf by byl v reálné aplikaci mrtvý."
        )
