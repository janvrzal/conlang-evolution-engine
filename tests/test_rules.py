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
