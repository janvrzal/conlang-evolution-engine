"""Hromadné výpočty nad číselným datovým modelem horkých cest (banka, frekvence, fronty).

Každý hromadný výpočet se tu porovnává s původním výpočtem po jednom na skutečných
datech z běžícího světa; otisky celých běhů hlídá ``scripts/v2_digests.py``.
"""

import numpy as np
import pytest

from cee.v2 import phonology
from cee.v2.language.bank import UNCHANGED
from cee.v2.language.lexical_index import _clarity_reference, clarity_scores, related_keys
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation


@pytest.fixture(scope="module")
def running():
    """Svět se zvukovými změnami a slovní zásobou po několika stech letech."""
    world = village_grid(4, seed=2, morphology=True, semantics=True)
    simulation = Simulation(world)
    simulation.run(600)
    return world


def test_predfiltr_banky_nikdy_neodmitne_skutecne_misto(running):
    world = running
    bank = world.form_bank()
    assert len(world.processes) > 5 and len(bank) > 50
    rules = sorted({group.main_code.stress_rule for group in world.groups.values()})
    form_ids = np.arange(min(len(bank), 400), dtype=np.int64)
    for process in world.processes.values():
        for rule in rules:
            table = bank.process_table(process, rule)
            # Předfiltr po jednom tvaru (bity hlásek) i hromadný (ploché pole).
            bulk = bank.has_site(table._masks, form_ids)
            for form_id, flag in zip(form_ids.tolist(), bulk.tolist()):
                applied = process.apply(bank.forms[form_id], world.table, rule)
                if applied is not None:
                    assert flag and bank.may_apply(form_id, rule, process.key)
                if not bank.may_apply(form_id, rule, process.key):
                    assert applied is None
            # Výsledky tabulky (hromadně i po jednom) se shodují s aplikací změny.
            fresh = bank.process_table(process, rule)
            for form_id, result in zip(form_ids.tolist(), fresh.results(form_ids).tolist()):
                applied = process.apply(bank.forms[form_id], world.table, rule)
                assert (result == UNCHANGED) if applied is None else bank.forms[result] == applied
                assert fresh.result(form_id) == result


def test_predfiltr_banky_vrati_stejne_klice_jako_bity(running):
    world = running
    bank = world.form_bank()
    process = next(iter(world.processes.values()))
    for rule in ("penult", "initial"):
        bank.process_table(process, rule)
    for form_id in range(min(len(bank), 200)):
        for rule in ("penult", "initial"):
            keys = bank.possible(form_id, rule)
            assert (process.key in keys) == bank.may_apply(form_id, rule, process.key)


def test_hromadne_frekvence_uziti_davaji_stejne_hodnoty_jako_volani_po_jednom(running):
    world = running
    checked = 0
    for group in world.groups.values():
        code = group.main_code
        units = sorted(code.phonology.vocabulary)
        bulk = world.usage_frequencies(code, units)
        assert bulk == [world.usage_frequency(code, unit) for unit in units]
        checked += len(units)
    assert checked > 100


def test_vyber_vzorku_a_oriznute_frekvence_jsou_uplne_razeni(running):
    from cee.v2.language.assessment_index import clipped_frequencies, top_words

    world = running
    code = next(iter(world.groups.values())).main_code
    expected = sorted(
        code.phonology.vocabulary, key=lambda unit: (-world.usage_frequency(code, unit), unit)
    )[:50]
    assert top_words(world, code, 50) == expected
    clipped = clipped_frequencies(world, code, expected)
    assert list(clipped) == expected
    assert all(value == max(0.01, world.usage_frequency(code, unit)) for unit, value in clipped.items())


def test_hromadne_skore_lexikalni_jasnosti_sedi_s_pythonovou_referenci(running):
    world = running
    codes = [group.main_code for group in world.groups.values()]
    groups, morphemes, concepts = [], [], []
    for position, code in enumerate(codes):
        pairs = [(root, concept) for concept, root in sorted(code.phonology.dominant.items())]
        pairs += pairs[:5]  # duplicity se vracejí ve stejném pořadí
        for root, concept in pairs:
            groups.append(position)
            morphemes.append(world.registry.morphemes.numbers[root])
            concepts.append(world.registry.concepts.intern(concept))
    arguments = [np.array(values, dtype=np.int64) for values in (groups, morphemes, concepts)]
    bulk = clarity_scores(world, codes, *arguments)
    reference = _clarity_reference(world, codes, *arguments, related_keys(world))
    assert bulk.tolist() == reference.tolist() and len(bulk) == len(groups)
    # Podruhé totéž (výpočet nezávisí na paměti).
    assert clarity_scores(world, codes, *arguments).tolist() == bulk.tolist()


def test_hromadna_fronta_procesu_sedi_s_vkladanim_po_jednom(running):
    world = running
    code = next(iter(world.groups.values())).main_code
    state = code.phonology
    candidates = [
        variable_id for variable_id in sorted(world.processes)
        if variable_id not in state.pending and variable_id not in state.closed
    ]
    assert candidates, "scénář po 600 letech má mít proces, který skupina ještě nezná"
    checked = 0
    for variable_id in candidates[:6]:
        bulk_code = code.branch()
        phonology.activate(world, bulk_code, variable_id)
        # Původní postup: ``_queue`` pro každé dotčené slovo seřadil dvojice (potřebný logit, jméno).
        bank = world.form_bank()
        table = bank.process_table(world.processes[variable_id], bulk_code.stress_rule)
        reference = sorted(
            (phonology._needed(world, variable_id, morpheme_id, bulk_code), morpheme_id)
            for morpheme_id in sorted(bulk_code.phonology.vocabulary)
            if table.result(bank.id_of(world.form_of(bulk_code, morpheme_id))) >= 0
            and morpheme_id not in bulk_code.phonology.restructured.get(variable_id, ())
        )
        assert bulk_code.phonology.pending[variable_id].pairs() == reference
        assert set(bulk_code.phonology.queued[variable_id]) == {name for _, name in reference}
        checked += len(reference)
    assert checked > 0
