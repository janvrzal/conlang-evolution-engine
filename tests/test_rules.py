"""Sémantika aplikace pravidel: dvoufázovost, hranice slova, časová stopa."""
from cee.core.models import Word
from cee.engine.rules import Rule


def test_pravidlo_se_aplikuje_simultanne(mapper):
    """
    Pravidlo nesmí krmit samo sebe. Při aplikaci zleva doprava s průběžnou
    mutací by 'aaa' dalo 'aia' (druhé 'a' už změněné odřízne prostředí
    třetího); simultánní aplikace dá 'aii'.
    """
    rule = Rule(
        name="a -> i po nízkém vokálu",
        target={"syl": "+", "lo": "+"},
        action={"lo": "-", "hi": "+", "back": "-", "tense": "+"},
        env_before={"syl": "+", "lo": "+"},
    )
    word = mapper.parse_word("x", "aaa")
    assert rule.apply_to_word(word) is True
    assert mapper.render_word(word) == "aii"


def test_env_boundary_koncova_pozice(mapper):
    rule = Rule(
        name="ztráta koncové souhlásky",
        target={"cons": "+"},
        action={"delete": "+"},
        env_after={"_boundary": "+"},
    )
    word = mapper.parse_word("x", "amat")
    assert rule.apply_to_word(word) is True
    assert mapper.render_word(word) == "ama"


def test_env_boundary_nesmi_zasahnout_uvnitr_slova(mapper):
    rule = Rule(
        name="ztráta koncové souhlásky",
        target={"cons": "+"},
        action={"delete": "+"},
        env_after={"_boundary": "+"},
    )
    word = mapper.parse_word("x", "ama")
    assert rule.apply_to_word(word) is False
    assert mapper.render_word(word) == "ama"


def test_vypujcka_unika_starsimu_pravidlu(mapper):
    """Slovo přejaté po datu pravidla jím podle AGENT.md §1 neprojde."""
    rule = Rule(
        name="lenice v roce 200",
        target={"cons": "+", "cont": "-", "voi": "-"},
        action={"voi": "+"},
        env_before={"syl": "+"},
        env_after={"syl": "+"},
        year=200,
    )

    domaci = mapper.parse_word("x", "apa")
    assert rule.apply_to_word(domaci) is True
    assert mapper.render_word(domaci) == "aba"

    vypujcka = mapper.parse_word("x", "apa")
    vypujcka.origin_year = 400
    assert rule.apply_to_word(vypujcka) is False
    assert mapper.render_word(vypujcka) == "apa"


def test_pravidlo_bez_zasahu_vraci_false(mapper):
    rule = Rule(name="nic", target={"cons": "+", "voi": "+", "cont": "+"}, action={"cont": "-"})
    word = mapper.parse_word("x", "aaa")
    assert rule.apply_to_word(word) is False


def test_predikat_pravidla_nemeni_tvar_a_uzna_platny_zasah(mapper):
    """Výběr kandidáta nesmí simulovat změnu mutací slovníku."""
    rule = Rule(
        name="lenice mezi vokály",
        target={"cons": "+", "cont": "-", "voi": "-"},
        action={"voi": "+"},
        env_before={"syl": "+"},
        env_after={"syl": "+"},
    )
    word = mapper.parse_word("x", "apa")

    assert rule.can_apply_to_word(word) is True
    assert mapper.render_word(word) == "apa"


def test_predikat_pravidla_respektuje_prosodickou_minimalitu(mapper):
    rule = Rule(
        name="synkopa vysokých vokálů",
        target={"syl": "+", "hi": "+"},
        action={"delete": "+"},
        env_before={"cons": "+"},
        env_after={"cons": "+"},
    )
    word = mapper.parse_word("x", "spir")

    assert rule.can_apply_to_word(word) is False


def test_predikat_nebere_pravidlo_ktere_uz_nema_co_zmenit(mapper):
    rule = Rule(
        name="finální odznělení",
        target={"cons": "+", "son": "-"},
        action={"voi": "-"},
        env_after={"_boundary": "+"},
    )

    assert rule.can_apply_to_word(mapper.parse_word("x", "ap")) is False
    assert rule.can_apply_to_word(mapper.parse_word("x", "ab")) is True


def test_vlozeni_segmentu_za_terc(mapper):
    """Engine musí umět i přidávat, ne jen měnit rysy a mazat."""
    from cee.engine.inventory import InventoryView

    inv = InventoryView(mapper, set("aeioupktrs"))
    rule = Rule(
        name="epenteze",
        target={"cons": "+"},
        action={},
        env_after={"cons": "+"},
        insert="after",
        insert_features=inv.features_of("i"),
        insert_label="i",
    )

    word = mapper.parse_word("x", "ptra")
    assert rule.apply_to_word(word) is True
    assert mapper.render_word(word) == "pitira"


def test_vlozeni_pred_terc(mapper):
    from cee.engine.inventory import InventoryView

    inv = InventoryView(mapper, set("aeioupktrs"))
    rule = Rule(
        name="protéze",
        target={"cons": "+"},
        action={},
        env_before={"_boundary": "+"},
        insert="before",
        insert_features=inv.features_of("a"),
        insert_label="a",
    )

    word = mapper.parse_word("x", "spika")
    assert rule.apply_to_word(word) is True
    assert mapper.render_word(word) == "aspika"


def test_vkladaci_pravidlo_bez_zasahu_nic_nepridá(mapper):
    from cee.engine.inventory import InventoryView

    inv = InventoryView(mapper, set("aeioupktrs"))
    rule = Rule(
        name="epenteze",
        target={"cons": "+"},
        action={},
        env_after={"cons": "+"},
        insert="after",
        insert_features=inv.features_of("i"),
    )

    word = mapper.parse_word("x", "aka")  # žádný shluk
    assert rule.apply_to_word(word) is False
    assert mapper.render_word(word) == "aka"


def test_mazani_neponici_slovo_uplne(mapper):
    """
    'Information carrying capacity': jednosegmentové slovo se mazacím
    pravidlem nesmí smrsknout na nic. Segment-count kontrola (< 2 hlásky)
    tohle nechytí, protože se aktivuje jen když slovo mělo aspoň 2 hlásky
    před mazáním — jednosegmentové slovo skrz ni propadne beze změny.
    """
    rule = Rule(
        name="ztráta koncové souhlásky",
        target={"cons": "+"},
        action={"delete": "+"},
        env_after={"_boundary": "+"},
    )
    word = mapper.parse_word("x", "n")
    assert rule.apply_to_word(word) is False
    assert mapper.render_word(word) == "n"


def test_mazani_nesmi_odebrat_posledni_jadro_slabiky(mapper):
    """
    Segment-count kontrola sama nestačí: 'spir' má po synkopě 3 hlásky
    (nad libovolnou pevnou hranicí), ale žádnou samohlásku — tedy žádné
    slabičné jádro. Takové slovo je nevyslovitelné a splývá s jakýmkoliv
    jiným souhláskovým shlukem, což je přesně ztráta informační kapacity.
    """
    rule = Rule(
        name="synkopa vysokých vokálů",
        target={"syl": "+", "hi": "+"},
        action={"delete": "+"},
        env_before={"cons": "+"},
        env_after={"cons": "+"},
    )
    word = mapper.parse_word("x", "spir")
    assert rule.apply_to_word(word) is False
    assert mapper.render_word(word) == "spir"


def test_mazani_projde_kdyz_jine_jadro_zbyva(mapper):
    """Minimalita nesmí blokovat mazání, dokud slovo má jinou samohlásku."""
    rule = Rule(
        name="ztráta koncové souhlásky",
        target={"cons": "+"},
        action={"delete": "+"},
        env_after={"_boundary": "+"},
    )
    word = mapper.parse_word("x", "amat")
    assert rule.apply_to_word(word) is True
    assert mapper.render_word(word) == "ama"


def test_minimalita_neresi_slovo_bez_samohlasky_od_pocatku(mapper):
    """
    Umělé slovo bez jediné samohlásky nemá co ztratit navíc — minimalita
    ho nesmí zaseknout na věčné mazání ničeho.
    """
    from cee.core.models import Segment, Word as WordModel

    p = Segment(features=dict(mapper.parse_word("x", "p").segments[0].features))
    t = Segment(features=dict(mapper.parse_word("x", "t").segments[0].features))
    word = WordModel(concept_id="x", segments=[p, t])

    rule = Rule(
        name="ztráta koncové souhlásky",
        target={"cons": "+"},
        action={"delete": "+"},
        env_after={"_boundary": "+"},
    )
    assert rule.apply_to_word(word) is True
    assert mapper.render_word(word) == "p"
