"""
Rozrůzněnost vývoje: seed per uzel, makro-parametry, kontakt.

Reprodukovatelnost neznamená, že se všechny jazyky chovají stejně — znamená,
že se táž konfigurace chová stejně pokaždé (CEE_master.md 5.5).
"""

import pytest

from cee.core.models import Lexicon
from cee.engine.generator import MacroParams, SoundChangeGenerator
from cee.engine.parser import YamlParser
from cee.engine.rng import derive_seed
from cee.pipeline import SimulationConfig

PRESET_PATH = "src/cee/data/presets/fantasy_preset.yaml"
SLOVA = [
    ("vlk", "lupu"),
    ("voda", "laku"),
    ("strom", "petra"),
    ("oheň", "foku"),
    ("kámen", "sekuru"),
    ("přítel", "amiku"),
]


@pytest.fixture(scope="module")
def preset():
    return YamlParser.parse_preset(PRESET_PATH)


def _lexikon(mapper):
    return Lexicon(words=[mapper.parse_word(c, i) for c, i in SLOVA])


# --- odvozování seedů --------------------------------------------------------


def test_seed_je_stabilni_a_ruzny_pro_uzel():
    assert derive_seed(42, "sever") == derive_seed(42, "sever")
    assert derive_seed(42, "sever") != derive_seed(42, "jih")
    assert derive_seed(42, "sever") != derive_seed(7, "sever")


def test_seed_nezamenuje_slozene_casti():
    """('ab','c') a ('a','bc') musí dát různý výsledek."""
    assert derive_seed(1, "ab", "c") != derive_seed(1, "a", "bc")


# --- vývoj jednotlivých jazyků ----------------------------------------------


def _vyvoj(mapper, preset, node_id, biome="hory", years=1000, **kwargs):
    from cee.engine.graph_builder import GraphBuilder
    from cee.engine.topology import EvolutionGraph

    graph = EvolutionGraph()
    graph.node_configs[node_id] = {"map": {"biome": biome}, **kwargs}

    config = SimulationConfig(years=years, preset=preset, root_id="proto")

    # We must start from a root proto node connected to our node to mimic how simulator forks
    graph.node_configs["proto"] = {}
    graph.vertical_edges.append(
        __import__("cee.engine.topology", fromlist=["VerticalEdge"]).VerticalEdge(
            parent_id="proto", child_id=node_id, rules=[]
        )
    )

    builder = GraphBuilder()
    states = __import__("cee.pipeline").pipeline.run_simulation(
        _lexikon(mapper), graph, mapper, config, builder
    )

    state = states[node_id]

    def count_mutations():
        return sum(
            1
            for event in builder.events
            if event.get("kind") == "sound_change" and event.get("hit_count", 0) > 0
        )

    return {w.concept_id: mapper.render_word(w) for w in state.lexicon.words}, count_mutations


def test_dva_jazyky_se_stejnym_biomem_se_rozejdou(mapper, preset):
    """
    Jádro problému: dokud byl seed jeden pro všechno, tři jazyky se stejným
    nastavením dostaly identickou chronologii.
    """
    sever, _ = _vyvoj(mapper, preset, "sever")
    jih, _ = _vyvoj(mapper, preset, "jih")

    rozdilne = [k for k in sever if sever[k] != jih[k]]
    assert rozdilne, "Sever a jih vyšly slovo od slova stejně."


def test_tyz_uzel_dava_tyz_vysledek(mapper, preset):
    prvni, _ = _vyvoj(mapper, preset, "sever")
    druhy, _ = _vyvoj(mapper, preset, "sever")
    assert prvni == druhy


def test_biom_meni_charakter_zmen(mapper, preset):
    hory, _ = _vyvoj(mapper, preset, "x", biome="hory")
    prales, _ = _vyvoj(mapper, preset, "x", biome="prales")
    assert hory != prales


# --- makro-parametry ---------------------------------------------------------


def test_konzervativni_jazyk_se_meni_min(mapper, preset):
    _formy, klidny_mutations = _vyvoj(mapper, preset, "klidny", macro={"conservatism": 0.9})
    _formy, bourlivy_mutations = _vyvoj(mapper, preset, "klidny", macro={"conservatism": 0.0})

    assert klidny_mutations() < bourlivy_mutations()


def test_rychlost_zmeny_pridava_pravidla(mapper, preset):
    _f, pomaly_mutations = _vyvoj(mapper, preset, "u", years=200, macro={"change_rate": 0.5})
    _f, rychly_mutations = _vyvoj(mapper, preset, "u", years=200, macro={"change_rate": 2.0})

    assert rychly_mutations() > pomaly_mutations()


@pytest.mark.parametrize(
    "vstup, ocekavano",
    [
        ({"conservatism": 5}, 1.0),  # ořez shora
        ({"conservatism": -3}, 0.0),  # ořez zdola
    ],
)
def test_konzervativnost_se_orizne(vstup, ocekavano):
    assert MacroParams.from_config(vstup).conservatism == ocekavano


def test_pozdejsi_zdroj_prebije_drivejsi():
    """Nastavení uzlu má přednost před presetem."""
    macro = MacroParams.from_config({"change_rate": 1.0}, {"change_rate": 3.0})
    assert macro.change_rate == 3.0


def test_eroze_konců_posiluje_prislusna_schemata(mapper, preset):
    silna = SoundChangeGenerator(preset, seed=1, macro=MacroParams(coda_erosion=5.0))
    slaba = SoundChangeGenerator(preset, seed=1, macro=MacroParams(coda_erosion=0.1))

    def vaha(gen):
        choices, weights = gen._weighted_schemas("hory")
        return {s.name: w for s, w in zip(choices, weights)}

    assert vaha(silna)["coda_loss"] > vaha(slaba)["coda_loss"]
    assert vaha(silna)["lenition"] == vaha(slaba)["lenition"]


def test_deletion_rate_reguluje_vsechny_mazaci_zakony(mapper, preset):
    silna = SoundChangeGenerator(preset, seed=1, macro=MacroParams(deletion_rate=1.0))
    slaba = SoundChangeGenerator(preset, seed=1, macro=MacroParams(deletion_rate=0.1))

    def vaha(gen):
        choices, weights = gen._weighted_schemas("hory")
        return {s.name: w for s, w in zip(choices, weights)}

    assert vaha(silna)["apocope"] > vaha(slaba)["apocope"]
    assert vaha(silna)["compensatory_lengthening"] > vaha(slaba)["compensatory_lengthening"]
    assert vaha(silna)["lenition"] == vaha(slaba)["lenition"]


def test_rok_zmeny_je_rozptyleny_ale_v_mezich(mapper, preset):
    """Bez rozptylu padají změny v přesném taktu, což nevypadá jako dějiny."""
    gen = SoundChangeGenerator(preset, seed=5, macro=MacroParams(timing_jitter=0.5))
    roky = [gen.year_for_slot(0, 1000, i, 8) for i in range(8)]

    assert all(0 < r <= 1000 for r in roky)

    presny = SoundChangeGenerator(preset, seed=5, macro=MacroParams(timing_jitter=0.0))
    takt = [presny.year_for_slot(0, 1000, i, 8) for i in range(8)]
    # Takt bez rozptylu je pravidelný až na zaokrouhlení (1000/9 = 111.1).
    rozdily = [b - a for a, b in zip(takt, takt[1:])]
    assert max(rozdily) - min(rozdily) <= 1, f"Takt má být pravidelný, je {rozdily}."
    assert roky != takt


def test_izolace_tlumi_tempo_inovaci_neblokuje_je_uplne():
    propojeny = MacroParams(sound_changes_per_millennium=8.0, isolation=0.0)
    izolovany = MacroParams(sound_changes_per_millennium=8.0, isolation=1.0)

    assert propojeny.innovations_per_millennium == 10.0
    assert izolovany.innovations_per_millennium == 6.0


def test_generovana_zmena_se_siri_postupne_a_je_auditovatelna(mapper):
    """Jedna inovace má počátek, fáze šíření a konec; není to skrytý skok."""
    from cee.engine.graph_builder import GraphBuilder
    from cee.engine.topology import EvolutionGraph, VerticalEdge

    preset = {
        "schemas": {"final_devoicing": {"base_weight": 1.0}},
        "biomes": {},
        "macro": {
            "sound_changes_per_millennium": 4.0,
            "change_spread_years": 120,
            "timing_jitter": 0.0,
        },
    }
    graph = EvolutionGraph(
        node_configs={"proto": {}, "child": {"year": 0}},
        vertical_edges=[VerticalEdge("proto", "child", [])],
    )
    builder = GraphBuilder()
    state = __import__("cee.pipeline").pipeline.run_simulation(
        Lexicon([mapper.parse_word(f"word-{index}", "ab") for index in range(80)]),
        graph,
        mapper,
        SimulationConfig(years=500, preset=preset, root_id="proto", seed=9),
        builder,
    )["child"]

    events = [
        event
        for event in builder.events
        if event.get("kind") == "sound_change" and event.get("schema_id") == "final_devoicing"
    ]
    assert events
    first_change_id = events[0]["change_id"]
    phases = [event for event in events if event["change_id"] == first_change_id]
    assert phases[0]["duration"] > 0
    assert phases[0]["progress"] < 1.0
    assert phases[-1]["progress"] == 1.0
    assert 0 < phases[0]["hit_count"] < 80
    assert all(mapper.render_word(word) == "ap" for word in state.lexicon.words)


def test_potomek_dedi_i_zmenu_ktera_prave_probiha(mapper):
    from cee.engine.events import SoundChangeEvent
    from cee.engine.rules import Rule
    from cee.engine.simulator import EvolutionSimulator
    from cee.engine.topology import EvolutionGraph

    simulator = EvolutionSimulator(EvolutionGraph(), mapper)
    change = SoundChangeEvent(
        year=10,
        branch_id="parent",
        rule=Rule("odzneleni", {"voi": "+"}, {"voi": "-"}),
        change_id="parent:10:1",
        duration=120,
    )
    simulator._sound_changes[change.change_id] = change
    simulator._sound_change_adoptions[change.change_id] = {("word", 0, "")}
    queued = []

    simulator._inherit_active_sound_changes("parent", "child", 60, lambda *args: queued.append(args))

    inherited_id = "parent:10:1:fork:child"
    assert simulator._sound_change_adoptions[inherited_id] == {("word", 0, "")}
    assert queued
    assert all(event.branch_id == "child" and event.year > 60 for _, _, event in queued)


# --- kontakt mezi propojenými jazyky ----------------------------------------


def _rodina(mapper, preset, edges, years=1000):
    from cee.engine.topology import ContactEdge, EvolutionGraph, VerticalEdge

    graph = EvolutionGraph()
    graph.node_configs = {
        "proto": {},
        "sever": {"map": {"biome": "hory"}},
        "jih": {"map": {"biome": "prales"}},
    }

    for edge in edges:
        if edge.get("kind") == "contact":
            graph.contact_edges.append(
                ContactEdge(
                    year=edge.get("year", years // 2),
                    source_id=edge["source"],
                    target_id=edge["target"],
                    volume=edge.get("volume", 5),
                    mutual=edge.get("mutual", True),
                )
            )
        else:
            graph.vertical_edges.append(
                VerticalEdge(parent_id=edge["source"], child_id=edge["target"], rules=[])
            )

    config = __import__("cee.pipeline").pipeline.SimulationConfig(
        years=years, root_id="proto", preset=preset
    )
    states = __import__("cee.pipeline").pipeline.run_simulation(
        _lexikon(mapper), graph, mapper, config
    )

    branches = {}
    for node_id, state in states.items():
        words = []
        for w in state.lexicon.words:
            words.append(
                {
                    "id": w.concept_id,
                    "ipa": mapper.render_word(w),
                    "source_id": w.source_id,
                    "origin_year": w.origin_year,
                }
            )
        branches[node_id] = {"year": state.year, "words": words}

    return branches


DEDICNOST = [{"source": "proto", "target": "sever"}, {"source": "proto", "target": "jih"}]


def test_vetve_se_vyvijeji_po_celou_zadanou_dobu(mapper, preset):
    """
    Horizont generování byl natvrdo 200 let, takže jazyky ztuhly hned na
    začátku a pozdější kontakt zastihl nehybný stav.
    """
    vetve = _rodina(mapper, preset, DEDICNOST, years=1000)
    assert all(v["year"] == 1000 for v in vetve.values())


def test_vetve_se_navzajem_lisi(mapper, preset):
    vetve = _rodina(mapper, preset, DEDICNOST)
    sever = {w["id"]: w["ipa"] for w in vetve["sever"]["words"]}
    jih = {w["id"]: w["ipa"] for w in vetve["jih"]["words"]}
    assert sever != jih


def test_bez_kontaktni_hrany_zadne_vypujcky(mapper, preset):
    vetve = _rodina(mapper, preset, DEDICNOST)
    for v in vetve.values():
        assert not [w for w in v["words"] if w["source_id"]]


def test_kontaktni_hrana_pusobi_obema_smery(mapper, preset):
    """Sousedící jazyky se ovlivňují navzájem, ne jen jedním směrem."""
    vetve = _rodina(
        mapper,
        preset,
        DEDICNOST
        + [
            {"source": "sever", "target": "jih", "kind": "contact", "year": 500, "volume": 3},
        ],
    )

    for branch_id, druhy in [("sever", "jih"), ("jih", "sever")]:
        pujcky = [w for w in vetve[branch_id]["words"] if w["source_id"]]
        assert pujcky, f"{branch_id} nepřejal nic."
        assert {w["source_id"] for w in pujcky} == {druhy}
        assert all(w["origin_year"] >= 500 for w in pujcky)


def test_jednosmerny_kontakt(mapper, preset):
    """Výrazně nesymetrická prestiž = kontakt jen jedním směrem."""
    vetve = _rodina(
        mapper,
        preset,
        DEDICNOST
        + [
            {
                "source": "sever",
                "target": "jih",
                "kind": "contact",
                "year": 500,
                "volume": 3,
                "mutual": False,
            },
        ],
    )

    assert [w for w in vetve["jih"]["words"] if w["source_id"]]
    assert not [w for w in vetve["sever"]["words"] if w["source_id"]]


def test_vypujcka_projde_jen_pozdejsimi_zmenami(mapper, preset):
    """
    Slovo přejaté v roce 500 nesmí projít změnami z roku 200 — to je smysl
    atributu origin_year (AGENT.md §1.4).
    """
    vetve = _rodina(
        mapper,
        preset,
        DEDICNOST
        + [
            {"source": "sever", "target": "jih", "kind": "contact", "year": 500, "volume": 5},
        ],
    )

    pujcky = {w["id"]: w["ipa"] for w in vetve["jih"]["words"] if w["source_id"]}
    domaci = {w["id"]: w["ipa"] for w in vetve["jih"]["words"] if not w["source_id"]}

    spolecne = set(pujcky) & set(domaci)
    assert spolecne, "Chybí koncept, který má domácí i přejatý tvar."
    assert any(
        pujcky[k] != domaci[k] for k in spolecne
    ), "Přejatý tvar vyšel stejně jako domácí — origin_year se neuplatnil."
