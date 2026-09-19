"""Derivační kontrakty systémové zvukové historie.

Tyto testy nejsou jen kontrola, že se nějaké pravidlo spustilo. Každý chrání
jednu konkrétní historickou interpretaci, kterou musí simulátor zachovat.
"""

from cee.core.models import Inventory, Lexicon, PopulationProfile, State
from cee.engine.decisions import ChangeDecisionEngine
from cee.engine.inventory import InventoryView
from cee.engine.phonotactics import PhonotacticProfile
from cee.engine.rules import Rule


def _vowels(mapper, symbols="aeiou"):
    return [dict(mapper.parse_word("v", symbol).segments[0].features) for symbol in symbols]


def test_tazny_retezec_provede_vsechny_kroky_simultanne(mapper):
    a, e, i = _vowels(mapper, "aei")
    word = mapper.parse_word("sample", "pai")
    rule = Rule(
        "tažný řetězec s prázdným nízkým místem",
        {"syl": "+"},
        {},
        operation="chain_shift",
        chain_type="pull",
        chain_steps=[(e, a), (i, e)],
    )

    assert rule.apply_to_word(word) is True
    # /a/ je prázdné místo: /e/ a /i/ se posunou, ale žádný mezitvar
    # nespustí další krok ve stejném slově.
    assert mapper.render_word(word) == "pae"

    inventory = InventoryView(mapper, {"p", "a", "e", "i"}).apply(rule)
    # Plánovač vidí uvolněné vysoké místo, takže následný výběr pravidel
    # nevychází z inventáře před řetězcem.
    assert "i" not in inventory
    assert {"a", "e"}.issubset(set(inventory))


def test_harmonie_ma_smer_a_morfemova_domena(mapper):
    inventory = _vowels(mapper)
    word_domain = mapper.parse_word("whole", "petu")
    morpheme_domain = mapper.parse_word("bound", "petu")
    morpheme_domain.morpheme_boundaries = {2}
    rule = Rule(
        "regresivní harmonie zadnosti",
        {"syl": "+"},
        {},
        operation="vowel_harmony",
        harmony_direction="regressive",
        harmony_domain="word",
        harmony_features=["back"],
        harmony_inventory=inventory,
    )

    assert rule.apply_to_word(word_domain) is True
    assert mapper.render_word(word_domain) == "potu"
    rule.harmony_domain = "morpheme"
    assert rule.apply_to_word(morpheme_domain) is False
    assert mapper.render_word(morpheme_domain) == "petu"


def test_tonova_rada_a_sandhi_pracuji_s_konturami(mapper):
    word = mapper.parse_word("tone", "pata")
    nuclei = word.syllable_nuclei()
    word.tones = {nuclei[0]: "H", nuclei[1]: "L"}
    shift = Rule(
        "tónová rotace", {"syl": "+"}, {}, operation="tone_shift", tone_rotation={"H": "F", "F": "L", "L": "R", "R": "H"}
    )
    assert shift.apply_to_word(word) is True
    assert word.tones == {nuclei[0]: "F", nuclei[1]: "R"}

    word.tones = {nuclei[0]: "L", nuclei[1]: "H"}
    sandhi = Rule("sandhi", {"syl": "+"}, {}, operation="tone_sandhi", tone_sandhi_map={"L>H": "L>R"})
    assert sandhi.apply_to_word(word) is True
    assert word.tones == {nuclei[0]: "L", nuclei[1]: "R"}


def test_tonova_inovace_ma_oporu_v_populacni_siti(mapper):
    word = mapper.parse_word("tone", "pata")
    word.tones = {index: "H" for index in word.syllable_nuclei()}
    rule = Rule("tónová řada", {"syl": "+"}, {}, operation="tone_shift")
    sparse = State("sparse", Inventory(), Lexicon([word]), population=PopulationProfile(size=100, area=1000, centers=1))
    dense = State("dense", Inventory(), Lexicon([mapper.parse_word("tone", "pata")]), population=PopulationProfile(size=1_000_000, area=10, centers=4))
    dense.lexicon.words[0].tones = {index: "H" for index in dense.lexicon.words[0].syllable_nuclei()}

    assert ChangeDecisionEngine.assess_sound_change(dense, rule, mapper).pressure > ChangeDecisionEngine.assess_sound_change(sparse, rule, mapper).pressure


def test_fonotaktika_ucí_sonoritu_a_necha_ojedinely_relkit(mapper):
    productive = PhonotacticProfile.learn([mapper.parse_word("a", "pra"), mapper.parse_word("b", "pra")])
    assert productive.violation(mapper.parse_word("bad", "rpa")) == "onset_sonority"

    relic = PhonotacticProfile.learn([mapper.parse_word("normal", "pata"), mapper.parse_word("relic", "rpa")])
    assert relic.violation(mapper.parse_word("same-relic", "rpa")) is None


def test_funkcni_zatez_chrani_i_kontrast_v_ramci_paradigmatu(mapper):
    first = mapper.parse_word("past", "apa")
    second = mapper.parse_word("present", "aba")
    first.paradigm = second.paradigm = "verb:go"
    first.frequency = second.frequency = 0.9
    state = State("x", Inventory(), Lexicon([first, second]))
    rule = Rule("b > p", dict(second.segments[1].features), {"voi": "-"})

    decision = ChangeDecisionEngine.assess_sound_change(state, rule, mapper)
    assert decision.functional_load > 0
    assert decision.paradigm_retention < 1
