from cee.engine.rules import Rule


def test_synkopa_nezasahne_prizvucne_jadro(mapper):
    word = mapper.parse_word("test", "pataka")
    word.stress_index = 1  # první /a/
    rule = Rule(
        name="synkopa",
        target={"syl": "+"},
        action={"delete": "+"},
        env_before={"cons": "+"},
        env_after={"cons": "+"},
        prosody="unstressed",
    )

    assert rule.apply_to_word(word)
    assert mapper.render_word(word) == "patka"


def test_stary_lexikon_dostane_deterministicky_prizvuk(mapper):
    word = mapper.parse_word("test", "pata")
    assert word.stress_index == 1
    word.stress_index = None  # simulace starého serializovaného lexikonu
    word.ensure_stress()
    assert word.stress_index == 1
