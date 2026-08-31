from cee.engine.inventory import InventoryView
from cee.engine.schemas import (
    ChainShiftSchema,
    ToneShiftSchema,
    TonogenesisSchema,
    VowelHarmonySchema,
)


def test_vokalova_harmonie_projde_celou_formou(mapper):
    inventory = InventoryView(mapper, {"p", "k", "o", "i"})
    rule = VowelHarmonySchema().generate_rule(inventory, 100)
    word = mapper.parse_word("word", "poki")

    assert rule is not None
    assert rule.apply_to_word(word)
    assert mapper.render_word(word) == "peki"


def test_retezovy_posun_rotuje_kontrasty_soubezne(mapper):
    inventory = InventoryView(mapper, {"p", "a", "e", "i"})
    rule = ChainShiftSchema().generate_rule(inventory, 100)
    word = mapper.parse_word("word", "paei")

    assert rule is not None
    assert rule.apply_to_word(word)
    assert mapper.render_word(word) == "peia"


def test_tonogeneze_nahradi_ztracenou_kodu_tonem(mapper):
    inventory = InventoryView(mapper, {"p", "a", "t"})
    rule = TonogenesisSchema().generate_rule(inventory, 100)
    word = mapper.parse_word("word", "pat")

    assert rule is not None
    assert rule.apply_to_word(word)
    assert mapper.render_word(word) == "pa"
    assert word.tones == {1: "H"}
    assert mapper.render_word_prosodic(word) == "pˈa˥"

    shift = ToneShiftSchema().generate_rule(inventory, 200)
    assert shift is not None and shift.apply_to_word(word)
    assert word.tones == {1: "R"}
