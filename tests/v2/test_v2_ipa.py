"""Úplné IPA v tabulce hlásek (``cee.v2.language.segments``)."""

import unicodedata

import pytest

from cee.v2.language.segments import default_table

CHART = (
    "p b t d ʈ ɖ c ɟ k ɡ q ɢ ʔ m ɱ n ɳ ɲ ŋ ɴ ʙ r ʀ ⱱ ɾ ɽ ɸ β f v θ ð s z ʃ ʒ ʂ ʐ ç ʝ x ɣ χ ʁ ħ ʕ h ɦ ɬ ɮ "
    "ʋ ɹ ɻ j ɰ l ɭ ʎ ʟ ʘ ǀ ǃ ǂ ǁ ɓ ɗ ʄ ɠ ʛ pʼ tʼ kʼ sʼ ʍ w ɥ ʜ ʢ ʡ ɕ ʑ ɺ ɧ t͡s d͡z t͡ʃ d͡ʒ t͡ɕ d͡ʑ ʈ͡ʂ ɖ͡ʐ "
    "k͡p ɡ͡b ŋ͡m i y ɨ ʉ ɯ u ɪ ʏ ʊ e ø ɘ ɵ ɤ o ə ɛ œ ɜ ɞ ʌ ɔ æ ɐ a ɶ ɑ ɒ ɚ ɝ"
)
DIACRITICS = (
    "aː aˑ ă ã n̥ d̥ ŋ̊ t̬ tʰ o̹ ɔ̜ u̟ e̠ ë e̽ n̩ e̯ b̤ a̰ t̼ tʷ tʲ tˠ tˤ ɫ e̝ e̞ e̘ e̙ t̪ t̺ t̻ ẽ dⁿ dˡ t̚ "
    "qʷ dʱ tˀ ʘ̃ t̪ʰ ɛ̞ː ɾ̥ ɐ̃ kʷʰ"
)


def signature(ipa):
    return "".join(sorted(unicodedata.normalize("NFD", ipa).replace("̊", "̥")))


@pytest.mark.parametrize("symbol", (CHART + " " + DIACRITICS).split())
def test_kazda_hlaska_ipa_se_zapise_zpet_beze_ztraty(symbol):
    table = default_table()
    form = table.parse(symbol)
    assert len(form) == 1
    assert signature(table.render(form)) == signature(symbol)


def test_ruzne_hlasky_nesplyvaji():
    table = default_table()
    symbols = (CHART + " " + DIACRITICS).split()
    assert len({table.parse(symbol) for symbol in symbols}) == len(symbols)


def test_puvodni_hlasky_maji_nulove_vlastni_rysy_a_stejna_id():
    table = default_table()
    assert table.ipa[table.parse("t")[0]] == "t"
    assert table.parse("ɐ")[0] >= table.old_count and table.parse("e")[0] < table.old_count
    detail = [table.index[name] for name in table.detail_names]
    assert not table.vectors[: table.old_count][:, detail].any()


def test_tony_diakritikou_jsou_tonove_znacky():
    table = default_table()
    assert table.render(table.parse("á")) == "a˦"
    assert table.render(table.parse("ǎ")) == "a˩˥"
    assert table.render(table.parse("kʷá")) == "kʷa˦"
    assert table.lossless("á") and table.lossless("ˈpata")


def test_nova_hlaska_neni_vystupem_zmeny_misto_puvodni():
    table = default_table()
    # zvýšení /ɛ/: nejbližší je pořád původní /e/, ne nová /e̝/ ani /ɐ/
    raised = table.changed(table.id_of("ɛ"), (("tense", "+"),))
    assert raised is not None and raised < table.old_count
