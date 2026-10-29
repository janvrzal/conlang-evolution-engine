"""Napojení číselného jádra na proces a banku tvarů."""

import numpy as np

from cee.v2.language.bank import UNCHANGED, FormBank
from cee.v2.language.processes import Process
from cee.v2.language.segments import default_table


def test_proces_a_sledovana_hranice_sedi_s_referenci():
    table = default_table()
    forms = [table.parse(word) for word in ("kata", "tatata", "ata", "kita")]
    processes = [
        Process("x", table.segments(["t"]), "replace", segment=table.id_of("d")),
        Process("x", table.segments(["t"]), "insert_before", segment=table.id_of("s")),
        Process("x", table.segments(["t"]), "delete"),
        Process("x", table.segments(["t"]), "change", changes=(("voi", "+"),)),
        Process("x", table.segments(["t"]), "merge_next", segment=table.id_of("d")),
    ]
    for process in processes:
        for form in forms:
            for rule in ("initial", "penult", "final"):
                for boundary in (None, 0, 1, len(form)):
                    assert process.apply_tracked(form, table, rule, boundary) == process._apply(
                        form, table, rule, boundary
                    )


def test_banka_roste_a_davka_zachovava_poradi_registrace():
    table = default_table()
    bank = FormBank(table)
    process = Process("x", table.segments(["t"]), "replace", segment=table.id_of("d"))
    forms = [table.parse("kata"), table.parse("tatata"), table.parse("kita"), table.parse("papa")]
    ids = bank.ids_of(forms)
    for length in range(1, 90):
        bank.id_of((table.id_of("a"),) * length)
    results = bank.process_table(process, "penult").results(ids[[2, 0, 2, 3, 1]])
    for index, result in zip(ids[[2, 0, 2, 3, 1]], results):
        expected = process._apply(bank.forms[index], table, "penult", None)
        assert result == UNCHANGED if expected is None else bank.forms[result] == expected[0]
    assert np.all(bank._matrix[ids[0], :len(forms[0])] == forms[0])
    assert bank.id_of(process._apply(forms[0], table, "penult", None)[0]) < bank.id_of(
        process._apply(forms[2], table, "penult", None)[0]
    )
