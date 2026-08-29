"""Chování evolučního simulátoru: hloubka stromu, kontakt, složeniny, determinismus."""
import pytest
import yaml

from cee.core.models import Inventory, Lexicon, State
from cee.engine.parser import YamlParser
from cee.engine.simulator import EvolutionSimulator
from cee.engine.topology import EvolutionGraph

LENICE = {
    "name": "Lenice ptk -> bdg",
    "year": 100,
    "target": {"cons": "+", "cont": "-", "voi": "-"},
    "env_before": {"syl": "+"},
    "env_after": {"syl": "+"},
    "action": {"voi": "+"},
}

APOKOPA = {
    "name": "Ztráta koncové samohlásky",
    "year": 200,
    "target": {"syl": "+"},
    "env_after": {"_boundary": "+"},
    "action": {"delete": "+"},
}


def _topologie(tmp_path, definice: dict):
    """Zapíše topologii na disk a načte ji stejnou cestou jako CLI."""
    path = tmp_path / "topo.yaml"
    path.write_text(yaml.safe_dump(definice, allow_unicode=True), encoding="utf-8")
    return YamlParser.parse_topology(str(path))


def _root(mapper, slova):
    lexicon = Lexicon(words=[mapper.parse_word(cid, ipa) for cid, ipa in slova])
    return State(node_id="proto", year=0, inventory=Inventory(), lexicon=lexicon)


def test_vnoreny_strom_se_nezahodi(mapper, tmp_path):
    """
    Třípatrová topologie: vnuk musí zdědit změny rodiče a přidat vlastní.
    Dřív se do simulace dostaly jen přímé děti rootu a vnuci mizeli bez hlášky.
    """
    graph = _topologie(tmp_path, {
        "nodes": [{"id": "proto"}, {"id": "west"}, {"id": "west_a"}],
        "vertical_edges": [
            {"parent": "proto", "child": "west", "rules": [LENICE]},
            {"parent": "west", "child": "west_a", "rules": [APOKOPA]},
        ],
    })

    root = _root(mapper, [("vlk", "lupu")])
    states = EvolutionSimulator(graph, mapper).simulate(root)

    assert set(states) == {"west", "west_a"}
    assert mapper.render_word(states["west"].lexicon.words[0]) == "lubu"
    # west_a dědí lenici a navíc ztrácí koncový vokál
    assert mapper.render_word(states["west_a"].lexicon.words[0]) == "lub"


def test_nedosazitelny_uzel_varuje(mapper, tmp_path):
    graph = _topologie(tmp_path, {
        "nodes": [{"id": "proto"}, {"id": "sirotek"}],
        "vertical_edges": [
            {"parent": "neznamy_rodic", "child": "sirotek", "rules": [LENICE]},
        ],
    })

    root = _root(mapper, [("vlk", "lupu")])
    with pytest.warns(UserWarning, match="nejsou z 'proto' dosažitelné"):
        states = EvolutionSimulator(graph, mapper).simulate(root)
    assert states == {"proto": root}


def test_vypujcka_nese_stopu_a_unika_starsim_pravidlum(mapper, tmp_path):
    graph = _topologie(tmp_path, {
        "nodes": [{"id": "proto"}, {"id": "north"}, {"id": "south"}],
        "vertical_edges": [
            {"parent": "proto", "child": "north", "rules": [LENICE]},
            {"parent": "proto", "child": "south", "rules": [APOKOPA]},
        ],
        "contact_edges": [
            {"year": 300, "source": "north", "target": "south", "volume": 1},
        ],
    })

    root = _root(mapper, [("vlk", "lupu")])
    states = EvolutionSimulator(graph, mapper).simulate(root)

    south = states["south"].lexicon.words
    vypujcky = [w for w in south if w.source_id == "north"]
    assert len(vypujcky) == 1

    vypujcka = vypujcky[0]
    assert vypujcka.origin_year == 300
    # Přejato v roce 300, tedy až po apokopě z roku 200 — koncový vokál zůstává.
    assert mapper.render_word(vypujcka) == "lubu"
    assert mapper.render_word([w for w in south if w.source_id is None][0]) == "lup"


def test_slozeniny_ridi_topologie_ne_kod(mapper, tmp_path):
    """
    Složeniny se dřív vytvářely natvrdo v simulator.py pro české koncepty.
    Teď je předepisuje topologie a respektuje se compound_head.
    """
    slozenina = [{"head": "mesto", "modifier": "zlaty", "id": "zlate_mesto"}]
    graph = _topologie(tmp_path, {
        "nodes": [
            {"id": "proto"},
            {"id": "north", "map": {"compound_head": "initial"}, "compounds": slozenina},
            {"id": "south", "map": {"compound_head": "final"}, "compounds": slozenina},
        ],
        "vertical_edges": [
            {"parent": "proto", "child": "north"},
            {"parent": "proto", "child": "south"},
        ],
    })

    root = _root(mapper, [("mesto", "viku"), ("zlaty", "auru")])
    states = EvolutionSimulator(graph, mapper).simulate(root)

    north = states["north"].lexicon.get_word("zlate_mesto")
    south = states["south"].lexicon.get_word("zlate_mesto")
    assert mapper.render_word(north) == "vikuauru"   # head-initial
    assert mapper.render_word(south) == "auruviku"   # head-final


def test_bez_predepsanych_slozenin_zadne_nevzniknou(mapper, tmp_path):
    graph = _topologie(tmp_path, {
        "nodes": [{"id": "proto"}, {"id": "north"}],
        "vertical_edges": [{"parent": "proto", "child": "north", "rules": [LENICE]}],
    })

    root = _root(mapper, [("mesto", "viku"), ("zlaty", "auru")])
    states = EvolutionSimulator(graph, mapper).simulate(root)
    assert len(states["north"].lexicon.words) == 2


def test_simulace_je_deterministicka_a_neprepisuje_topologii(mapper, tmp_path):
    """Dvojí běh nad týmž grafem musí dát tentýž výsledek (AGENT.md §1)."""
    preset = YamlParser.parse_preset("src/cee/data/presets/fantasy_preset.yaml")
    graph = _topologie(tmp_path, {
        "nodes": [{"id": "proto"}, {"id": "hory", "map": {"biome": "hory"}}],
        "vertical_edges": [{"parent": "proto", "child": "hory"}],
    })

    def bez(seed=42):
        root = _root(mapper, [("vlk", "lupu"), ("voda", "laku")])
        states = EvolutionSimulator(graph, mapper, preset=preset, seed=seed).simulate(root)
        return [mapper.render_word(w) for w in states["hory"].lexicon.words]

    prvni = bez()
    assert bez() == prvni, "Opakovaný běh dal jiný výsledek (graf se nesmí mutovat)."
    assert prvni != ["lupu", "laku"], "Generátor nevyrobil žádnou změnu."


def test_volitelne_se_vyviji_i_korenovy_protojazyk(mapper):
    """UI sleduje kořen na mapě, proto nesmí zůstat mimo výsledky simulace."""
    root = _root(mapper, [("vlk", "lupu")])
    graph = EvolutionGraph()
    preset = YamlParser.parse_preset("src/cee/data/presets/fantasy_preset.yaml")

    states = EvolutionSimulator(
        graph, mapper, preset=preset, seed=42, end_year=1000, evolve_root=True
    ).simulate(root)

    assert "proto" in states
    assert mapper.render_word(states["proto"].lexicon.words[0]) != "lupu"


def test_uzel_bez_vlastniho_pravidla_vznika_v_roce_z_konfigurace(mapper):
    graph = EvolutionGraph()
    graph.node_configs = {"proto": {}, "daughter": {"year": 500}}
    graph.vertical_edges.append(
        __import__("cee.engine.topology", fromlist=["VerticalEdge"]).VerticalEdge("proto", "daughter", [])
    )

    states = EvolutionSimulator(graph, mapper).simulate(_root(mapper, [("vlk", "lupu")]))
    assert states["daughter"].year == 500
