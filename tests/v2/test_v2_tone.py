"""Tóny: rys samohlásky, tónové protojazyky, vznik a změny tónů."""

from cee.v2.changes.sound import (
    ToneDissimilation,
    ToneFromCoda,
    ToneFromOnset,
    ToneLoss,
    ToneMerger,
)
from cee.v2.language.protoforms import protolanguage
from cee.v2.language.segments import TONE_CODES, default_table
from cee.v2.metrics import lexicon_profile
from cee.v2.parameters import Parameters
from cee.v2.scenarios import DEFAULT_CONCEPTS, ProtoLanguage, Region, region_world
from cee.v2.simulation import Simulation
from cee.v2.spec import build, check


def render(table, form):
    return table.render(form)


def test_ton_je_rys_samohlasky():
    table = default_table()
    form = table.parse("má")
    assert render(table, form) == "ma˦" and len(form) == 2
    assert table.tone_of(form[1]) == TONE_CODES["˦"]
    a = table.id_of("a")
    assert table.with_tone(table.with_tone(a, TONE_CODES["˧˥"]), 0) == a
    assert table.is_vowel(table.with_tone(a, TONE_CODES["˥"]))


def test_tonovy_protojazyk_a_netonovy_beze_zmeny():
    plain, _ = protolanguage(DEFAULT_CONCEPTS, seed=5)
    again, _ = protolanguage(DEFAULT_CONCEPTS, seed=5, tones=())
    assert plain == again
    toned, _ = protolanguage(DEFAULT_CONCEPTS, seed=5, tones=("˥", "˧", "˩"))
    table = default_table()
    vowels = [s for form in toned.values() for s in table.parse(form) if table.is_vowel(s)]
    assert vowels and all(table.tone_of(s) for s in vowels)


def apply(process, ipa):
    table = default_table()
    out = process.apply(table.parse(ipa), table, "penult")
    return None if out is None else table.render(out)


def test_tonogeneze_ze_souhlasky_a_zakonceni():
    table = default_table()
    inventory = sorted(set(table.parse("tadaʔpahs")))
    onset = {p.label: p for p in ToneFromOnset().candidates(table, inventory)}
    assert apply(onset["V → V˦ /T_"], "tadapa") == "ta˦dapa˦"
    assert apply(onset["V → V˨ /D_"], "tadapa") == "tada˨pa"
    coda = {p.label: p for p in ToneFromCoda().candidates(table, inventory)}
    assert apply(coda["V → V˧˥ /_ʔ#"], "papaʔ") == "papa˧˥ʔ"
    assert apply(coda["V → V˥˩ /_h#"], "papah") == "papa˥˩h"


def test_tony_splyvaji_mizi_a_rozruznuji_se():
    table = default_table()
    inventory = sorted(set(table.parse("ta˦da˥pa˧˥")))
    merger = {p.label: p for p in ToneMerger().candidates(table, inventory)}
    assert apply(merger["˦ → ˥"], "ta˦da˦") == "ta˥da˥"
    loss = {p.label: p for p in ToneLoss().candidates(table, inventory)}
    assert apply(loss["˧˥ → ∅"], "ta˦pa˧˥") == "ta˦pa"
    sandhi = {p.label: p for p in ToneDissimilation().candidates(table, inventory)}
    assert apply(sandhi["˦ → ˥ /_C˦"], "ta˦da˦") == "ta˥da˦"


def small_world(languages, params=None, seed=1):
    regions = (
        Region("w", (0.0, 0.0), neighbours=("e",), language="a", villages=3),
        Region("e", (60.0, 0.0), neighbours=("w",), language="a", villages=3),
    )
    return region_world(regions, seed=seed, languages=languages, params=params)


def test_tonovy_jazyk_tony_udrzi():
    world = small_world((ProtoLanguage("a", tones=("˥", "˧", "˩")),))
    Simulation(world).run(500.0)
    assert all(lexicon_profile(world, group).tones >= 2 for group in ("w-v0", "e-v0"))


def test_tony_mohou_vzniknout_samy():
    # Zrychlená tonogeneze (úroveň změny v ``Parameters.change_rates``), aby test nebyl o náhodě.
    params = Parameters(change_rates={"tonogenesis_onset": 40.0, "tonogenesis_coda": 40.0})
    toned = 0
    for seed in (1, 2, 3):
        world = small_world((ProtoLanguage("a"),), params=params, seed=seed)
        Simulation(world).run(800.0)
        toned += lexicon_profile(world, "w-v0").tones > 0
    assert toned >= 2


def test_popis_sveta_overi_tony():
    spec = {"end_year": 50, "semantics": False, "languages": [{"id": "a", "tones": ["˥", "˧", "˧", "X"]}],
            "regions": [{"id": "c", "position": [0, 0], "villages": 2}]}
    issues = {issue.path: issue.message for issue in check(spec)}
    assert "neznámý tón" in issues["languages.0.tones.3"]
    assert "opakují" in issues["languages.0.tones"]
    spec["languages"][0]["tones"] = ["˥", "˧˥", "˩"]
    assert check(spec) == []
    build(spec)
