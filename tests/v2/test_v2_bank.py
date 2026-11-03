"""Banka tvarů, tabulky procesů a průběžné indexy (výkonová vrstva M6d)."""


from cee.v2.changes.sound import CATALOG, sound_index
from cee.v2.language.bank import UNCHANGED, FormBank
from cee.v2.language.index import ExponentIndex
from cee.v2.language.lexicon import FormStore, UnitForm
from cee.v2.language.processes import Process
from cee.v2.language.sound_index import SoundIndex
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation


def test_banka_da_stejnemu_tvaru_stejne_cislo_a_tabulka_sedi_s_aplikaci():
    world = village_grid(1, seed=1, phonology=True)
    table = world.table
    bank = FormBank(table)
    forms = [table.parse(word) for word in ("kata", "kita", "kata", "papa")]
    ids = bank.ids_of(forms)
    assert ids[0] == ids[2] != ids[1] and len(bank) == 3
    process = Process("voicing", table.segments(["t"]), "replace", segment=table.id_of("d"),
                      left=table.VOWEL, right=table.VOWEL)
    results = bank.process_table(process, "penult").results(ids)
    for form, result in zip(forms, results.tolist()):
        expected = process.apply(form, table, "penult")
        assert (result == UNCHANGED) if expected is None else bank.forms[result] == expected
    assert bank.process_table(process, "penult").result(int(ids[3])) == UNCHANGED


def test_ulozeni_tvaru_vede_denik_a_vetev_ma_novou_identitu():
    store = FormStore()
    store.set("a", UnitForm((1, 2), None, None))
    store.set("b", UnitForm((3,), None, None))
    assert store.log == ["a", "b"]
    branch = store.branch()
    assert branch.token != store.token and branch.log == []
    assert branch.get("a") == UnitForm((1, 2), None, None)


def _context_multiset(index, world, code):
    """Počty prostředí kódu jako seřazená pole n-tic (nezávisí na číslování prostředí)."""
    columns = index.context_counts(code, world)
    return sorted(zip(*(column.tolist() for column in columns)))


def test_prubezne_indexy_se_shoduji_s_vypoctem_od_nuly():
    world = village_grid(3, seed=2, syntax=True, semantics=True)
    simulation = Simulation(world)
    kept = {}
    index = sound_index(world)
    for group in world.group_ids():
        code = world.groups[group].main_code
        kept[group] = ExponentIndex()
        kept[group].sync(world, code)
        index.sync(world, [code], CATALOG, force=True)
    for year in (300, 600, 900):
        simulation.run(year)
        for group in world.group_ids():
            code = world.groups[group].main_code
            exponents = kept[group]
            exponents.sync(world, code)
            index.sync(world, [code], CATALOG, force=True)
            fresh_exponents, fresh = ExponentIndex(), SoundIndex()
            fresh_exponents.sync(world, code)
            fresh.sync(world, [code], CATALOG, force=True)
            assert _context_multiset(index, world, code) == _context_multiset(fresh, world, code)
            assert index.inventory(code) == fresh.inventory(code)
            assert index.supports(code).tolist() == fresh.supports(code).tolist()
            assert exponents.exponents == fresh_exponents.exponents
            assert exponents.shapes == fresh_exponents.shapes
    assert any(len(world.groups[group].main_code.forms.log) for group in world.group_ids())
    assert all(len(_context_multiset(index, world, world.groups[group].main_code)) > 0 for group in world.group_ids())
