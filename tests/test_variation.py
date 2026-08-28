"""
Rozrůzněnost vývoje: seed per uzel, makro-parametry, kontakt.

Reprodukovatelnost neznamená, že se všechny jazyky chovají stejně — znamená,
že se táž konfigurace chová stejně pokaždé (CEE_master.md 5.5).
"""
import pytest

from cee.core.models import Inventory, Lexicon, State
from cee.engine.generator import MacroParams, SoundChangeGenerator
from cee.engine.inventory import InventoryView
from cee.engine.parser import YamlParser
from cee.engine.rng import derive_seed
from cee.pipeline import LineageConfig, evolve_lineage

PRESET_PATH = "src/cee/data/presets/fantasy_preset.yaml"
SLOVA = [("vlk", "lupu"), ("voda", "laku"), ("strom", "petra"),
         ("oheň", "foku"), ("kámen", "sekuru"), ("přítel", "amiku")]


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


def _vyvoj(mapper, preset, node_id, biome="hory", **kwargs):
    state, history = evolve_lineage(
        _lexikon(mapper), mapper,
        LineageConfig(years=1000, epochs=5, preset=preset, biome=biome,
                      node_id=node_id, **kwargs),
    )
    return {w.concept_id: mapper.render_word(w) for w in state.lexicon.words}, history


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
    _formy, klidny = _vyvoj(mapper, preset, "klidny", macro={"conservatism": 0.9})
    _formy, bourlivy = _vyvoj(mapper, preset, "klidny", macro={"conservatism": 0.0})

    assert len(klidny.rule_applications()) < len(bourlivy.rule_applications())


def test_rychlost_zmeny_pridava_pravidla(mapper, preset):
    _f, pomaly = _vyvoj(mapper, preset, "u", macro={"change_rate": 0.5})
    _f, rychly = _vyvoj(mapper, preset, "u", macro={"change_rate": 2.0})

    assert len(rychly.rule_applications()) > len(pomaly.rule_applications())


@pytest.mark.parametrize(
    "vstup, ocekavano",
    [
        ({"conservatism": 5}, 1.0),      # ořez shora
        ({"conservatism": -3}, 0.0),     # ořez zdola
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


# --- kontakt mezi propojenými jazyky ----------------------------------------


def _rodina(mapper, edges, years=1000):
    from cee.api.server import DynamicSimulateRequest, run_dynamic_simulation

    return run_dynamic_simulation(DynamicSimulateRequest(
        topology_data={
            "nodes": {"proto": {}, "sever": {"biome": "hory"}, "jih": {"biome": "prales"}},
            "edges": edges,
        },
        proto_lexicon=[{"id": c, "ipa": i} for c, i in SLOVA],
        semantics="",
        years=years,
    ))["branches"]


DEDICNOST = [{"source": "proto", "target": "sever"}, {"source": "proto", "target": "jih"}]


def test_vetve_se_vyvijeji_po_celou_zadanou_dobu(mapper):
    """
    Horizont generování byl natvrdo 200 let, takže jazyky ztuhly hned na
    začátku a pozdější kontakt zastihl nehybný stav.
    """
    vetve = _rodina(mapper, DEDICNOST, years=1000)
    assert all(v["year"] == 1000 for v in vetve.values())


def test_vetve_se_navzajem_lisi(mapper):
    vetve = _rodina(mapper, DEDICNOST)
    sever = {w["id"]: w["ipa"] for w in vetve["sever"]["words"]}
    jih = {w["id"]: w["ipa"] for w in vetve["jih"]["words"]}
    assert sever != jih


def test_bez_kontaktni_hrany_zadne_vypujcky(mapper):
    vetve = _rodina(mapper, DEDICNOST)
    for v in vetve.values():
        assert not [w for w in v["words"] if w["source_id"]]


def test_kontaktni_hrana_pusobi_obema_smery(mapper):
    """Sousedící jazyky se ovlivňují navzájem, ne jen jedním směrem."""
    vetve = _rodina(mapper, DEDICNOST + [
        {"source": "sever", "target": "jih", "kind": "contact", "year": 500, "volume": 3},
    ])

    for branch_id, druhy in [("sever", "jih"), ("jih", "sever")]:
        pujcky = [w for w in vetve[branch_id]["words"] if w["source_id"]]
        assert pujcky, f"{branch_id} nepřejal nic."
        assert {w["source_id"] for w in pujcky} == {druhy}
        assert all(w["origin_year"] == 500 for w in pujcky)


def test_jednosmerny_kontakt(mapper):
    """Výrazně nesymetrická prestiž = kontakt jen jedním směrem."""
    vetve = _rodina(mapper, DEDICNOST + [
        {"source": "sever", "target": "jih", "kind": "contact",
         "year": 500, "volume": 3, "mutual": False},
    ])

    assert [w for w in vetve["jih"]["words"] if w["source_id"]]
    assert not [w for w in vetve["sever"]["words"] if w["source_id"]]


def test_vypujcka_projde_jen_pozdejsimi_zmenami(mapper):
    """
    Slovo přejaté v roce 500 nesmí projít změnami z roku 200 — to je smysl
    atributu origin_year (AGENT.md §1.4).
    """
    vetve = _rodina(mapper, DEDICNOST + [
        {"source": "sever", "target": "jih", "kind": "contact", "year": 500, "volume": 5},
    ])

    pujcky = {w["id"]: w["ipa"] for w in vetve["jih"]["words"] if w["source_id"]}
    domaci = {w["id"]: w["ipa"] for w in vetve["jih"]["words"] if not w["source_id"]}

    spolecne = set(pujcky) & set(domaci)
    assert spolecne, "Chybí koncept, který má domácí i přejatý tvar."
    assert any(pujcky[k] != domaci[k] for k in spolecne), (
        "Přejatý tvar vyšel stejně jako domácí — origin_year se neuplatnil."
    )
