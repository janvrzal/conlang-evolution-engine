"""InventoryView — dotazy na přirozené třídy a vývoj inventáře v čase."""
import pytest

from cee.engine.inventory import InventoryView
from cee.engine.rules import Rule
from cee.engine.schemas import SCHEMA_REGISTRY


@pytest.fixture
def inv(mapper):
    return InventoryView(mapper, set("aiuptkvlr"))


def test_dotaz_na_prirozenou_tridu(inv):
    assert inv.matching({"cons": "+", "son": "-", "voi": "-", "cont": "-"}) == ["k", "p", "t"]
    assert inv.matching({"cons": "+", "son": "-", "voi": "+", "cont": "+"}) == ["v"]
    assert inv.matching({"cons": "+", "son": "+", "cont": "+"}) == ["l", "r"]


def test_znele_frikativy_se_nepletou_s_likvidami(inv):
    """/l/ a /r/ jsou [son: +], /v/ je [son: -] — bez toho terče splývají."""
    siroky = inv.matching({"cons": "+", "voi": "+", "cont": "+"})
    uzky = inv.matching({"cons": "+", "son": "-", "voi": "+", "cont": "+"})
    assert set(siroky) == {"l", "r", "v"}
    assert uzky == ["v"]


def test_ridici_klice_se_do_dotazu_nepocitaji(inv):
    """`_boundary` označuje hranici slova, ne rys segmentu."""
    assert inv.has({"_boundary": "+"})
    assert inv.has_all({"_boundary": "+"}, None)


def test_prazdna_trida(mapper):
    bez_frikativ = InventoryView(mapper, set("aiuptk"))
    assert bez_frikativ.has({"cons": "+", "son": "-", "voi": "+", "cont": "+"}) is False
    assert bez_frikativ.has_all({"cons": "+"}, {"syl": "+"}) is True


def test_lenice_prida_znele_okluzivy(mapper):
    """Feeding: po lenici je v jazyce b/d/ɡ, které tam předtím nebyly."""
    inv = InventoryView(mapper, set("ptkaiu"))
    po = inv.apply(SCHEMA_REGISTRY["lenition"].build(inv, 100))
    assert {"b", "d", "ɡ"} <= set(po)
    # Pravidlo má prostředí, takže původní neznělé okluzivy jinde ve slově zůstávají.
    assert {"p", "t", "k"} <= set(po)


def test_bezpodminecne_pravidlo_puvodni_hlasku_odebere(mapper):
    inv = InventoryView(mapper, set("eioau"))
    bezpodminecne = Rule(
        name="e -> i všude",
        target={"syl": "+", "hi": "-", "lo": "-", "back": "-"},
        action={"hi": "+"},
    )
    po = inv.apply(bezpodminecne)
    assert "i" in po
    assert "e" not in po


def test_mazaci_pravidlo_inventar_nemeni(mapper, inv):
    """Zda foném zanikne, závisí na pozicích ve slovech — inventář je nezná."""
    po = inv.apply(SCHEMA_REGISTRY["coda_loss"].build(inv, 100))
    assert set(po) == set(inv)


def test_prevod_tam_a_zpet(mapper):
    inv = InventoryView(mapper, set("ptk"))
    assert set(InventoryView.from_inventory(inv.to_inventory(), mapper)) == {"p", "t", "k"}
