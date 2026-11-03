"""Secondary-articulation intent, contexts, reverse paths and phonologization."""

import unicodedata

import pytest

from cee.v2 import metrics, phonology
from cee.v2.changes.base import InnovationContext
from cee.v2.changes.sound import (
    CodaLoss,
    Delabialization,
    Depalatalization,
    Labialization,
    LabialShift,
    PalatalAffrication,
    Palatalization,
    SecondaryPalatalization,
    VowelDenazalization,
    VowelNasalization,
    _Candidates,
    context_stats,
    sound_index,
)
from cee.v2.history import History
from cee.v2.language.lexicon import UnitForm
from cee.v2.language.processes import Process
from cee.v2.language.segments import default_table
from cee.v2.language.sound_index import SoundIndex
from cee.v2.repertoire import Distribution, Origin
from cee.v2.world import Code, SpeechGroup, Territory, World


@pytest.fixture(scope="module")
def table():
    return default_table()


def _inventory(table, symbols):
    return tuple(sorted({table.id_of(symbol) for symbol in symbols}))


def _nfd(text):
    return unicodedata.normalize("NFD", text)


def _candidate(family, table, source, inventory):
    source_id = table.id_of(source)
    return next(
        process for process in family().candidates(table, inventory)
        if source_id in process.target
    )


def _feature_delta(table, source, target):
    source_vector = table.vectors[table.id_of(source)]
    target_vector = table.vectors[table.id_of(target)]
    values = {1: "+", -1: "-", 0: "0"}
    return tuple(
        (name, values[int(target_value)])
        for index, name in enumerate(table.names)
        if (target_value := target_vector[index]) != source_vector[index]
    )


def test_panphon_tabule_obsahuje_potrebne_znacene_segmenty(table):
    for symbol in (
        "kʲ", "tʲ", "sʲ", "pʲ", "ɡʲ", "kʷ", "ɡʷ",
        "ã", "ẽ", "ĩ", "õ", "ũ", "t͡ʃ", "d͡ʒ",
    ):
        form = table.parse(symbol)
        assert len(form) == 1
        assert _nfd(table.render(form)) == _nfd(symbol)


def test_znacka_vystupu_se_pridava_jedine_s_vyslovnym_zamerem_a_plain_regrese_zustava(table):
    # Původní artefakt: prosté zvýšení /o/ má dát /u/, nikoli /oˠ/.
    raised = table.changed(table.id_of("o"), (("hi", "+"),))
    assert raised is not None and table.ipa[raised] == "u"

    oral = table.id_of("a")
    nasal = table.id_of("ã")
    nasal_delta = _feature_delta(table, "a", "ã")
    incidental = table.changed(oral, nasal_delta)
    intended = table.changed(oral, nasal_delta, allow=("̃",))
    assert incidental is None or table.feature(incidental, "nas") != 1
    assert intended is not None and table.feature(intended, "nas") == 1
    assert intended == nasal

    # Both composed and decomposed spellings parse as marked vowels; neither
    # spelling leaks through the default plain-output path.
    for spelling in ("ã", "ã"):
        marked_id = table.parse(spelling)[0]
        assert table.feature(marked_id, "nas") == 1
        assert _nfd(table.render((marked_id,))) == _nfd(spelling)


def test_bezna_zmena_zachova_jiz_existujici_palatalizaci_a_nazalitu(table):
    voiced_palatal = table.changed(
        table.id_of("tʲ"), _feature_delta(table, "tʲ", "dʲ")
    )
    raised_nasal = table.changed(
        table.id_of("ã"), _feature_delta(table, "ã", "ẽ")
    )
    assert voiced_palatal is not None and table.ipa[voiced_palatal] == "dʲ"
    assert raised_nasal is not None and table.ipa[raised_nasal] == "ẽ"


def test_zamer_a_druhe_prostredi_jsou_soucasti_klice_procesu(table):
    target = table.segments(("k",))
    base = Process("test", target, "change", changes=(("hi", "+"),))
    same_legacy = Process("test", target, "change", changes=(("hi", "+"),), allow=(), right2=None)
    palatal = Process("test", target, "change", changes=(("hi", "+"),), allow=("ʲ",))
    labial = Process("test", target, "change", changes=(("hi", "+"),), allow=("ʷ",))
    second_boundary = Process("test", target, "change", changes=(("hi", "+"),), right2=table.BOUNDARY)

    assert base.key == same_legacy.key
    assert base.key != palatal.key
    assert palatal.key != labial.key
    assert base.key != second_boundary.key


@pytest.mark.parametrize(
    "family,source,inventory,form,expected",
    [
        (SecondaryPalatalization, "k", ("k", "i"), "ki", "kʲi"),
        (SecondaryPalatalization, "t", ("t", "j"), "atj", "atʲj"),
        (VowelNasalization, "a", ("p", "a", "n"), "pan", "pãn"),
        (VowelNasalization, "a", ("p", "a", "n", "t"), "pant", "pãnt"),
        (Labialization, "k", ("k", "u"), "ku", "kʷu"),
        (Labialization, "ɡ", ("ɡ", "w", "a"), "ɡwa", "ɡʷwa"),
    ],
)
def test_nove_znacky_vznika_jen_v_podminenem_prostredi(
    table, family, source, inventory, form, expected
):
    process = _candidate(family, table, source, _inventory(table, inventory))
    result = process.apply(table.parse(form), table, "penult")
    assert result is not None and _nfd(table.render(result)) == _nfd(expected)
    assert process.allow


@pytest.mark.parametrize(
    "family,source,inventory,form,expected",
    [
        (Depalatalization, "kʲ", ("kʲ",), "kʲa", "ka"),
        (PalatalAffrication, "kʲ", ("kʲ",), "kʲa", "t͡ʃa"),
        (VowelDenazalization, "ã", ("ã",), "pã", "pa"),
        (Delabialization, "kʷ", ("kʷ",), "kʷa", "ka"),
        (LabialShift, "kʷ", ("kʷ",), "kʷa", "pa"),
    ],
)
def test_reverzni_cesty_rozkladaji_znacky_a_mezistupne(
    table, family, source, inventory, form, expected
):
    process = _candidate(family, table, source, _inventory(table, inventory))
    result = process.apply(table.parse(form), table, "penult")
    assert result is not None and _nfd(table.render(result)) == _nfd(expected)


def test_puvodni_prime_palatalizacni_cesta_zustava(table):
    process = _candidate(Palatalization, table, "k", _inventory(table, ("k", "i")))
    result = process.apply(table.parse("ki"), table, "penult")
    assert result is not None and _nfd(table.render(result)) == _nfd("t͡ʃi")

    first = _candidate(SecondaryPalatalization, table, "k", _inventory(table, ("k", "i")))
    intermediate = first.apply(table.parse("ki"), table, "penult")
    assert intermediate is not None and _nfd(table.render(intermediate)) == _nfd("kʲi")
    second = _candidate(PalatalAffrication, table, "kʲ", _inventory(table, ("kʲ",)))
    final = second.apply(intermediate, table, "penult")
    assert final is not None and _nfd(table.render(final)) == _nfd("t͡ʃi")


def test_nazalizace_vyzaduje_n_a_druhy_segment_c_nebo_hranici(table):
    process = _candidate(
        VowelNasalization, table, "a", _inventory(table, ("p", "a", "n", "t", "i"))
    )
    assert process.right2 is not None
    assert _nfd(table.render(process.apply(table.parse("pan"), table, "penult"))) == _nfd("pãn")
    assert _nfd(table.render(process.apply(table.parse("pant"), table, "penult"))) == _nfd("pãnt")
    assert process.apply(table.parse("pani"), table, "penult") is None
    assert process.apply(table.parse("pati"), table, "penult") is None


def test_right2_stats_candidates_and_incremental_sound_index_stay_equal(table):
    words = {
        "final_n": "pan",
        "coda_cluster": "pant",
        "initial_n": "an",
        "nasal_before_vowel": "pani",
        "non_nasal_context": "pata",
        "no_trigger": "pa",
    }
    world, group = _world_with_words(words)
    code = group.main_code
    context = InnovationContext(world, group, code, 0, 0.0)
    family = VowelNasalization()
    inventory = tuple(sorted({segment for form in words.values() for segment in table.parse(form)}))
    process = _candidate(VowelNasalization, table, "a", inventory)

    def expected_support():
        return sum(
            len(process.sites(world.form_of(code, unit), table, code.stress_rule))
            for unit in sorted(code.phonology.vocabulary)
        )

    def indexed_support():
        found = [
            support for candidate, support in family._supported(context).values()
            if candidate.key == process.key
        ]
        assert len(found) == 1
        return found[0]

    stats_before = context_stats(context)
    assert stats_before is not None
    explicit_before = expected_support()
    assert explicit_before == 3  # pan, pant, and an; pani/pata/pa do not match _N(C|#).
    assert stats_before.support(process, table) == explicit_before
    assert _Candidates([process], table).supports(stats_before, table)[0] == explicit_before
    assert indexed_support() == explicit_before

    state = code.phonology
    index = sound_index(world)
    assert isinstance(index, SoundIndex)
    changed_unit = next(
        morpheme.id for morpheme in world.morphemes.values()
        if morpheme.meaning == "nasal_before_vowel" and morpheme.kind == "root"
    )
    old = world.unit_of(code, changed_unit)
    code.forms.set(changed_unit, UnitForm(table.parse("pant"), None, old.exponent))
    state.version += 1  # mirror the version bump performed by production form rewrites

    stats_after = context_stats(context)
    assert stats_after is not None and stats_after is not stats_before
    explicit_after = expected_support()
    assert explicit_after == 4
    assert stats_after.support(process, table) == explicit_after
    assert _Candidates([process], table).supports(stats_after, table)[0] == explicit_after
    assert indexed_support() == explicit_after
    assert sound_index(world) is index


def _world_with_words(words, seed=12):
    world = World(seed=seed)
    world.add_territory(Territory("world", "world"))
    world.add_territory(Territory("v", "settlement", parent="world"))
    base = world.seed_lexicon(list(words), dict(words))
    group = world.add_group(SpeechGroup("v", "v", 500, [Code("main", base.branch())]))
    group.main_code.phonology.vocabulary.update(
        morpheme.id for morpheme in world.morphemes.values()
    )
    return world, group


def _establish(world, code, process, tick):
    variable, _ = phonology.register(world, process, Origin(process.family, tick, tick * 25.0, "v"))
    code.repertoire.set(variable, Distribution.fixed(phonology.changed_id(variable)))
    phonology.activate(world, code, variable)
    phonology.restructure(world, "v", tick, 25.0, History(), tick * 25.0)
    return variable


def test_nazovy_kontrast_vznika_restrukturaci_az_po_ztrate_spoustece(table):
    words = {f"nasal_{index}": "pan" for index in range(24)}
    words.update({f"oral_{index}": "pa" for index in range(24)})
    world, group = _world_with_words(words)
    code = group.main_code
    inventory = _inventory(table, ("p", "a", "n"))

    nasalization = _candidate(VowelNasalization, table, "a", inventory)
    _establish(world, code, nasalization, 1)
    # The vowel is nasal in stored forms, but remains conditioned by final /n/.
    proxy = metrics.underlying_inventory_proxy(world, [group.id])
    assert proxy is not None and proxy["nasal_vowel"]
    assert metrics.nasal_contrast_witness(world, group.id) is None

    coda_loss = _candidate(CodaLoss, table, "n", inventory)
    _establish(world, code, coda_loss, 2)
    witness = metrics.nasal_contrast_witness(world, group.id)
    assert witness is not None


def test_vsechny_hlasky_v_tabulce_maji_unikatni_vektory(table):
    """Žádné dvě hlásky v tabulce nesmí mít stejný vektor rysů.

    Palatalizované veláry kʲ a ɡʲ mají zdůvodněné back=0 (pokročilá velární
    artikulace), což je odlišuje od obyčejných velár (back=1) i od palatál
    c/ɟ (back=-1) a zabraňuje kolizi v rysovém prostoru.
    """
    vectors = [tuple(v) for v in table.vectors]
    assert len(set(vectors)) == len(table.ipa)

    back_idx = table.index["back"]
    # k vs kʲ vs c
    assert table.vectors[table.id_of("k"), back_idx] == 1
    assert table.vectors[table.id_of("kʲ"), back_idx] == 0
    assert table.vectors[table.id_of("c"), back_idx] == -1
    # ɡ vs ɡʲ vs ɟ
    assert table.vectors[table.id_of("ɡ"), back_idx] == 1
    assert table.vectors[table.id_of("ɡʲ"), back_idx] == 0
    assert table.vectors[table.id_of("ɟ"), back_idx] == -1
