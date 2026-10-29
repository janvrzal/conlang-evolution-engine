#!/usr/bin/env python3
"""Audit stochastických bran pro zpevnění milníků enginu v2.

Spouští všechny stochastické brány na zadaných seedech (výchozí 101..120),
zapisuje průběžně výsledky do JSONL souboru a na konci vypíše souhrnnou
Markdown tabulku s Wilsonovým konfidenčním intervalem a prahy k z N.
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import datetime
import gc
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Přidání kořene repozitáře na začátek sys.path pro přímé spouštění.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.v2.gate_checks import (  # noqa: E402
    classify_rate,
    passes,
    threshold_k,
    wilson_interval,
)
from tests.v2.test_v2_m1_gate import (  # noqa: E402
    check_metrika_7,
    check_metrika_8,
    check_s1_hranice,
    check_s1_kontinuum,
    check_velka_souhrnna_skupina,
    run_bordered,
    run_continuum,
    run_drift_pair,
)
from tests.v2.test_v2_m2_gate import (  # noqa: E402
    check_jazyky_z_ruznych_seedu_se_lisi,
    check_metrika_3,
    check_metrika_4,
    check_metrika_5,
    check_metrika_6,
    check_zvukove_zmeny_se_siri,
    run_phonology,
)
from tests.v2.test_v2_m3_gate import (  # noqa: E402
    _run as run_m3,
)
from tests.v2.test_v2_m3_gate import (
    _run_without_leveling as run_m3_without_leveling,
)
from tests.v2.test_v2_m3_gate import (
    check_analogie,
    check_morfologizace,
    check_produktivni_vzor,
    check_sturtevantuv_paradox,
)
from tests.v2.test_v2_m3_gate import (
    check_zvukove_metriky as check_m3_zvukove_metriky,
)
from tests.v2.test_v2_m3b_gate import (  # noqa: E402
    check_erodovana_slova,
    check_metrika_1,
    check_metrika_2,
    check_nova_slova,
    check_tabu,
    run_eroded,
    run_m3b,
    run_taboo_pair,
)
from tests.v2.test_v2_m3b_gate import (
    check_zvukove_metriky as check_m3b_zvukove_metriky,
)
from tests.v2.test_v2_m4_gate import (  # noqa: E402
    check_analytizace,
    check_bez_eroze,
    check_jespersenuv_cyklus,
    check_velky_cyklus,
    run_control,
    run_jespersen,
    run_obj_eroded,
    run_velky_cyklus,
)
from tests.v2.test_v2_m4b_gate import (  # noqa: E402
    check_bez_padu,
    check_clen_jeden_seed,
    check_exaptace,
    check_jazyk_bez_kategorie,
    run_exaptation_pair,
    run_no_case,
    run_tenseless_pair,
)
from tests.v2.test_v2_m5_gate import (  # noqa: E402
    check_bez_dvojjazycnosti,
    check_metrika_11,
    check_s2_l2,
    check_s2_mesto,
    check_s3_prechod,
    check_s3_substrat,
    check_vypujcky,
    run_borrowing,
    run_metrika_11,
    run_s2_city,
    run_s2_l2_pair,
    run_shifted,
)
from tests.v2.test_v2_m6a_gate import (  # noqa: E402
    check_psany_kod_bez_tisku_stoji,
    check_s4_bez_skoly,
    check_s4_skola,
    check_skola_sjednoti,
    check_skola_zmrazena,
    run_codification,
    run_diglossia_courses,
)
from tests.v2.test_v2_m6b_gate import (  # noqa: E402
    check_elita_prejde,
    check_ferguson,
    check_jazyk_trhu,
    check_loajalita,
    check_metrika_9,
    check_migrace,
    check_nabozenstvi,
    check_superstrat,
    run_conquered,
    run_conversion_pair,
    run_ferguson,
    run_loyalty,
    run_market_town,
    run_metrika_9,
    run_migration,
)
from tests.v2.test_v2_m6c_gate import (  # noqa: E402
    check_strom_odpovida,
    check_strom_stabilni,
    run_known_tree,
)


@dataclass(frozen=True)
class GateInfo:
    gate_id: str
    test_file: str
    test_func: str
    seeds_today: str
    batch_id: str


@dataclass(frozen=True)
class Batch:
    batch_id: str
    gate_ids: tuple[str, ...]
    run_fn: Callable[..., Any]
    eval_fn: Callable[[Any], dict[str, tuple[bool, str | None]]]
    is_triplet: bool = False


# Registr všech 52 stochastických bran.
GATE_REGISTRY: tuple[GateInfo, ...] = (
    # m1 (5 bran)
    GateInfo("m1::s1_kontinuum", "test_v2_m1_gate.py", "test_s1_kontinuum_je_plynule_a_vzdalenost_roste_se_vzdalenosti", "1", "m1_continuum"),
    GateInfo("m1::s1_hranice", "test_v2_m1_gate.py", "test_s1_hranice_vytvori_svazek_izoglos", "1", "m1_bordered"),
    GateInfo("m1::metrika_7", "test_v2_m1_gate.py", "test_metrika_7_usalene_zmeny_se_siri_po_s_krivce", "1", "m1_continuum"),
    GateInfo("m1::metrika_8", "test_v2_m1_gate.py", "test_metrika_8_vetsina_inovaci_zanikne", "1", "m1_continuum"),
    GateInfo("m1::velka_skupina_drift", "test_v2_m1_gate.py", "test_velka_souhrnna_skupina_driftuje_mene_nez_mala_vesnice", "1", "m1_drift"),

    # m2 (6 bran)
    GateInfo("m2::metrika_3", "test_v2_m2_gate.py", "test_metrika_3_delka_slov_zustava_v_pasmu", "3", "m2_phonology"),
    GateInfo("m2::metrika_4", "test_v2_m2_gate.py", "test_metrika_4_inventare_lezi_v_pasmu_realnych_jazyku", "3", "m2_phonology"),
    GateInfo("m2::metrika_5", "test_v2_m2_gate.py", "test_metrika_5_homofonie_zustava_nizka", "3", "m2_phonology"),
    GateInfo("m2::metrika_6", "test_v2_m2_gate.py", "test_metrika_6_ustalene_zmeny_odpovidaji_prioru_a_nejsou_jednostranne", "3 (soubor)", "m2_phonology_triplet"),
    GateInfo("m2::ruznost_seedu", "test_v2_m2_gate.py", "test_jazyky_z_ruznych_seedu_se_lisi", "3 (soubor)", "m2_phonology_triplet"),
    GateInfo("m2::zvukove_zmeny_se_siri", "test_v2_m2_gate.py", "test_zvukove_zmeny_se_siri_arealne_a_maji_male_vyjimky", "3", "m2_phonology"),

    # m3 (5 bran)
    GateInfo("m3::sturtevantuv_paradox", "test_v2_m3_gate.py", "test_sturtevantuv_paradox_zvuk_tvori_nepravidelnost_analogie_ji_opravuje", "2", "m3_morphology"),
    GateInfo("m3::morfologizace", "test_v2_m3_gate.py", "test_morfologizace_vznikne_sama", "10 (aspoň 4)", "m3_morphology"),
    GateInfo("m3::produktivni_vzor", "test_v2_m3_gate.py", "test_produktivni_vzor_se_siri_a_caste_slova_si_drzi_nepravidelnost", "2", "m3_morphology"),
    GateInfo("m3::analogie", "test_v2_m3_gate.py", "test_analogie_zasahuje_spis_vzacna_slova", "2", "m3_morphology"),
    GateInfo("m3::zvukove_metriky", "test_v2_m3_gate.py", "test_zvukove_metriky_drzi_i_s_paradigmaty", "10 (aspoň 5)", "m3_morphology"),

    # m3b (6 bran)
    GateInfo("m3b::metrika_1", "test_v2_m3b_gate.py", "test_metrika_1_retence_zakladni_slovni_zasoby_v_pasmu", "2", "m3b_lexicon"),
    GateInfo("m3b::metrika_2", "test_v2_m3b_gate.py", "test_metrika_2_caste_pojmy_se_nahrazuji_pomaleji", "2", "m3b_lexicon"),
    GateInfo("m3b::nova_slova", "test_v2_m3b_gate.py", "test_nova_slova_maji_doloditelny_puvod", "2", "m3b_lexicon"),
    GateInfo("m3b::erodovana_slova", "test_v2_m3b_gate.py", "test_erodovana_slova_se_nahrazuji_casteji", "1", "m3b_eroded"),
    GateInfo("m3b::tabu", "test_v2_m3b_gate.py", "test_tabu_vyvola_kolobeh_opisu", "12 (aspoň 1)", "m3b_taboo"),
    GateInfo("m3b::zvukove_metriky", "test_v2_m3b_gate.py", "test_zvukove_metriky_drzi_i_s_lexikalni_zmenou", "2", "m3b_lexicon"),

    # m4 (4 brány)
    GateInfo("m4::analytizace", "test_v2_m4_gate.py", "test_analytizace_po_erozi_padu_se_ustali_slovosled", "1", "m4_control_eroded"),
    GateInfo("m4::velky_cyklus", "test_v2_m4_gate.py", "test_velky_cyklus_eroze_opis_priklonka_nova_koncovka", "10 (aspoň 2)", "m4_velky_cyklus"),
    GateInfo("m4::jespersen", "test_v2_m4_gate.py", "test_jespersenuv_cyklus_ne_ne_pas_pas", "19 (aspoň 1)", "m4_jespersen"),
    GateInfo("m4::bez_eroze", "test_v2_m4_gate.py", "test_bez_eroze_syntax_zustava_a_zvukove_metriky_drzi", "1", "m4_control_eroded"),

    # m4b (4 brány)
    GateInfo("m4b::clen_vznikne", "test_v2_m4b_gate.py", "test_clen_vznikne_z_ukazovaciho_zajmena", "3 (aspoň 2)", "m4b_no_case"),
    GateInfo("m4b::bez_padu", "test_v2_m4b_gate.py", "test_bez_padu_se_slovosled_ustali", "3", "m4b_no_case"),
    GateInfo("m4b::exaptace", "test_v2_m4b_gate.py", "test_exaptace_zbytkove_koncovky", "10 (aspoň 2)", "m4b_exaptation"),
    GateInfo("m4b::jazyk_bez_kategorie", "test_v2_m4b_gate.py", "test_jazyk_bez_kategorie_ji_nema_dokud_ji_nevyvine", "1", "m4b_tenseless"),

    # m5 (7 bran)
    GateInfo("m5::s2_mesto", "test_v2_m5_gate.py", "test_s2_mesto_s_pristehovalci_zjednodusuje_ostrov_drzi", "2", "m5_s2_city"),
    GateInfo("m5::s2_l2", "test_v2_m5_gate.py", "test_s2_zjednoduseni_pusobi_l2_mluvci", "2", "m5_s2_l2"),
    GateInfo("m5::s3_prechod", "test_v2_m5_gate.py", "test_s3_region_prejde_na_prestizni_jazyk", "2", "m5_shifted"),
    GateInfo("m5::s3_substrat", "test_v2_m5_gate.py", "test_s3_v_novem_jazyce_zustane_stavba_a_vyslovnost_ale_malo_slov", "12 (aspoň 1)", "m5_shifted"),
    GateInfo("m5::vypujcky", "test_v2_m5_gate.py", "test_vypujcky_jsou_vzacne_pojmy_adaptovane_hlaskami_prijemce", "2", "m5_borrowing"),
    GateInfo("m5::bez_dvojjazycnosti", "test_v2_m5_gate.py", "test_bez_dvojjazycnosti_se_stavba_nepujcuje", "2", "m5_borrowing"),
    GateInfo("m5::metrika_11", "test_v2_m5_gate.py", "test_metrika_11_slozitost_klesa_s_l2_mluvcimi_a_populaci", "2", "m5_metrika_11"),

    # m6a (5 bran)
    GateInfo("m6a::s4_skola", "test_v2_m6a_gate.py", "test_s4_rozdil_roste_do_skoly_pak_se_zmensuje", "2", "m6a_diglossia"),
    GateInfo("m6a::s4_bez_skoly", "test_v2_m6a_gate.py", "test_s4_bez_skoly_rozdil_roste_dal", "2", "m6a_diglossia"),
    GateInfo("m6a::skola_sjednoti", "test_v2_m6a_gate.py", "test_skola_sjednoti_dialekty_ale_jazyk_se_meni_dal", "2", "m6a_diglossia"),
    GateInfo("m6a::skola_zmrazena", "test_v2_m6a_gate.py", "test_skola_se_zmrazenou_normou_zmenu_zastavi", "2", "m6a_diglossia"),
    GateInfo("m6a::psany_kod_stoji", "test_v2_m6a_gate.py", "test_psany_kod_bez_tisku_stoji", "1", "m6a_codification"),

    # m6b (8 bran)
    GateInfo("m6b::metrika_9", "test_v2_m6b_gate.py", "test_metrika_9_vzdalenost_roste_se_zemepisnou_zpomalene", "2", "m6b_metrika_9"),
    GateInfo("m6b::elita_prejde", "test_v2_m6b_gate.py", "test_elita_v_mensine_prejde_na_jazyk_poddanych", "2", "m6b_conquered"),
    GateInfo("m6b::superstrat", "test_v2_m6b_gate.py", "test_superstrat_je_hlavne_slovni", "10 (aspoň 2)", "m6b_conquered"),
    GateInfo("m6b::jazyk_trhu", "test_v2_m6b_gate.py", "test_jazyk_trhu_jen_mimo_domov_je_stabilni_dvojjazycnost", "10 (aspoň 2)", "m6b_market_town"),
    GateInfo("m6b::loajalita", "test_v2_m6b_gate.py", "test_loajalita_prechod_zpomali_nebo_zastavi", "1", "m6b_loyalty"),
    GateInfo("m6b::migrace", "test_v2_m6b_gate.py", "test_podil_l2_mluvcich_vyplyne_z_migrace_a_slozitost_klesa", "10 (aspoň 2)", "m6b_migration"),
    GateInfo("m6b::ferguson", "test_v2_m6b_gate.py", "test_fergusonova_diglosie_vysoka_varieta_stoji_lidova_rec_se_vzdaluje", "2", "m6b_ferguson"),
    GateInfo("m6b::nabozenstvi", "test_v2_m6b_gate.py", "test_nabozenstvi_prinese_ucena_slova_z_liturgickeho_jazyka", "2", "m6b_conversion"),

    # m6c (2 brány)
    GateInfo("m6c::strom_odpovida", "test_v2_m6c_gate.py", "test_strom_jazyku_odpovida_historii_rozpadu", "2", "m6c_known_tree"),
    GateInfo("m6c::strom_stabilni", "test_v2_m6c_gate.py", "test_strom_je_stabilni", "2", "m6c_known_tree"),
)

GATE_BY_ID: dict[str, GateInfo] = {g.gate_id: g for g in GATE_REGISTRY}

EXCLUDED_DETERMINISTIC_TESTS: set[str] = {
    "test_v2_m1_gate.py::test_metrika_12_stejny_seed_da_stejny_log_a_jiny_seed_jiny",
    "test_v2_m1_gate.py::test_priblizeni_nezmeni_historii_nepropojene_oblasti",
    "test_v2_m1_gate.py::test_vykon_rezimu_udoli",
    "test_v2_m2_gate.py::test_determinismus_s_fonologii",
    "test_v2_m2_gate.py::test_priblizeni_nezmeni_zvukovou_historii_nepropojene_oblasti",
    "test_v2_m3_gate.py::test_determinismus_s_morfologii",
    "test_v2_m3b_gate.py::test_determinismus_s_vyznamem",
    "test_v2_m4_gate.py::test_determinismus_se_syntaxi",
    "test_v2_m4b_gate.py::test_determinismus_s_profilem",
    "test_v2_m6a_gate.py::test_determinismus_s_pismem",
}


# --- Vyhodnocovací logiky jednotlivých dávek ---------------------------------


def _eval_m1_continuum(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, history = state
    return {
        "m1::s1_kontinuum": passes(check_s1_kontinuum, world, history),
        "m1::metrika_7": passes(check_metrika_7, history),
        "m1::metrika_8": passes(check_metrika_8, history),
    }


def _eval_m1_bordered(history: Any) -> dict[str, tuple[bool, str | None]]:
    return {"m1::s1_hranice": passes(check_s1_hranice, history)}


def _eval_m1_drift(pair: tuple[float, float]) -> dict[str, tuple[bool, str | None]]:
    large, small = pair
    return {"m1::velka_skupina_drift": passes(check_velka_souhrnna_skupina, large, small)}


def _eval_m2_phonology(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, history, profiles = state
    return {
        "m2::metrika_3": passes(check_metrika_3, profiles),
        "m2::metrika_4": passes(check_metrika_4, profiles),
        "m2::metrika_5": passes(check_metrika_5, profiles),
        "m2::zvukove_zmeny_se_siri": passes(check_zvukove_zmeny_se_siri, world, history),
    }


def _run_m2_triplet(triplet: tuple[int, int, int]) -> list[Any]:
    return [run_phonology(seed) for seed in triplet]


def _eval_m2_triplet(runs: list[Any]) -> dict[str, tuple[bool, str | None]]:
    return {
        "m2::metrika_6": passes(check_metrika_6, runs),
        "m2::ruznost_seedu": passes(check_jazyky_z_ruznych_seedu_se_lisi, runs),
    }


def _run_m3_morphology(seed: int) -> tuple[Any, Any, Any]:
    world, history = run_m3(seed)
    unleveled, _ = run_m3_without_leveling(seed)
    return world, history, unleveled


def _eval_m3_morphology(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, history, unleveled = state
    return {
        "m3::sturtevantuv_paradox": passes(check_sturtevantuv_paradox, world, unleveled),
        "m3::morfologizace": passes(check_morfologizace, world),
        "m3::produktivni_vzor": passes(check_produktivni_vzor, [(world, history)]),
        "m3::analogie": passes(check_analogie, world, history),
        "m3::zvukove_metriky": passes(check_m3_zvukove_metriky, world),
    }


def _eval_m3b_lexicon(world: Any) -> dict[str, tuple[bool, str | None]]:
    return {
        "m3b::metrika_1": passes(check_metrika_1, world),
        "m3b::metrika_2": passes(check_metrika_2, [world]),
        "m3b::nova_slova": passes(check_nova_slova, [world]),
        "m3b::zvukove_metriky": passes(check_m3b_zvukove_metriky, world),
    }


def _eval_m3b_eroded(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, eroded = state
    return {"m3b::erodovana_slova": passes(check_erodovana_slova, world, eroded)}


def _eval_m3b_taboo(pair: tuple[Any, Any]) -> dict[str, tuple[bool, str | None]]:
    with_taboo, without_taboo = pair
    return {"m3b::tabu": passes(check_tabu, with_taboo, without_taboo)}


def _run_m4_control_eroded(seed: int) -> tuple[Any, Any]:
    control_world, _ = run_control(seed)
    eroded_world, _ = run_obj_eroded(seed)
    return control_world, eroded_world


def _eval_m4_control_eroded(state: Any) -> dict[str, tuple[bool, str | None]]:
    control_world, eroded_world = state
    return {
        "m4::analytizace": passes(check_analytizace, eroded_world, control_world),
        "m4::bez_eroze": passes(check_bez_eroze, control_world),
    }


def _eval_m4_velky_cyklus(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, history, kinds_500 = state
    return {"m4::velky_cyklus": passes(check_velky_cyklus, world, history, kinds_500)}


def _eval_m4_jespersen(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, history = state
    return {"m4::jespersen": passes(check_jespersenuv_cyklus, world, history)}


def _eval_m4b_no_case(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, history = state
    return {
        "m4b::clen_vznikne": passes(check_clen_jeden_seed, world, history),
        "m4b::bez_padu": passes(check_bez_padu, world),
    }


def _eval_m4b_exaptation(pair: Any) -> dict[str, tuple[bool, str | None]]:
    (world, history), (control, control_history) = pair
    return {"m4b::exaptace": passes(check_exaptace, world, history, control, control_history)}


def _eval_m4b_tenseless(state: Any) -> dict[str, tuple[bool, str | None]]:
    tenseless_world, (zero_world, zero_history) = state
    return {
        "m4b::jazyk_bez_kategorie": passes(
            check_jazyk_bez_kategorie, tenseless_world, zero_world, zero_history
        )
    }


def _eval_m5_s2_city(world: Any) -> dict[str, tuple[bool, str | None]]:
    return {"m5::s2_mesto": passes(check_s2_mesto, world)}


def _eval_m5_s2_l2(pair: tuple[Any, Any]) -> dict[str, tuple[bool, str | None]]:
    native, mixed = pair
    return {"m5::s2_l2": passes(check_s2_l2, native, mixed)}


def _eval_m5_shifted(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, history, substrate = state
    return {
        "m5::s3_prechod": passes(check_s3_prechod, world, history),
        "m5::s3_substrat": passes(check_s3_substrat, world, substrate),
    }


def _eval_m5_borrowing(world: Any) -> dict[str, tuple[bool, str | None]]:
    return {
        "m5::vypujcky": passes(check_vypujcky, world),
        "m5::bez_dvojjazycnosti": passes(check_bez_dvojjazycnosti, world),
    }


def _eval_m5_metrika_11(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, places = state
    return {"m5::metrika_11": passes(check_metrika_11, world, places)}


def _eval_m6a_diglossia(courses: Any) -> dict[str, tuple[bool, str | None]]:
    return {
        "m6a::s4_skola": passes(check_s4_skola, courses),
        "m6a::s4_bez_skoly": passes(check_s4_bez_skoly, courses),
        "m6a::skola_sjednoti": passes(check_skola_sjednoti, courses),
        "m6a::skola_zmrazena": passes(check_skola_zmrazena, courses),
    }


def _eval_m6a_codification(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, simulation, before, written = state
    return {
        "m6a::psany_kod_stoji": passes(
            check_psany_kod_bez_tisku_stoji, world, simulation, before, written
        )
    }


def _eval_m6b_metrika_9(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, history = state
    return {"m6b::metrika_9": passes(check_metrika_9, world, history)}


def _eval_m6b_conquered(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, history, elite = state
    return {
        "m6b::elita_prejde": passes(check_elita_prejde, world, history),
        "m6b::superstrat": passes(check_superstrat, world, elite),
    }


def _eval_m6b_market_town(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, history = state
    return {"m6b::jazyk_trhu": passes(check_jazyk_trhu, world, history)}


def _eval_m6b_loyalty(state: Any) -> dict[str, tuple[bool, str | None]]:
    free, loyal, steadfast = state
    return {"m6b::loajalita": passes(check_loajalita, free, loyal, steadfast)}


def _eval_m6b_migration(world: Any) -> dict[str, tuple[bool, str | None]]:
    return {"m6b::migrace": passes(check_migrace, world)}


def _eval_m6b_ferguson(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, history, before = state
    return {"m6b::ferguson": passes(check_ferguson, world, history, before)}


def _eval_m6b_conversion(state: Any) -> dict[str, tuple[bool, str | None]]:
    world, converted, control = state
    return {"m6b::nabozenstvi": passes(check_nabozenstvi, world, converted, control)}


def _eval_m6c_known_tree(simulation: Any) -> dict[str, tuple[bool, str | None]]:
    return {
        "m6c::strom_odpovida": passes(check_strom_odpovida, simulation),
        "m6c::strom_stabilni": passes(check_strom_stabilni, simulation),
    }


BATCHES: tuple[Batch, ...] = (
    Batch("m1_continuum", ("m1::s1_kontinuum", "m1::metrika_7", "m1::metrika_8"), run_continuum, _eval_m1_continuum),
    Batch("m1_bordered", ("m1::s1_hranice",), run_bordered, _eval_m1_bordered),
    Batch("m1_drift", ("m1::velka_skupina_drift",), run_drift_pair, _eval_m1_drift),

    Batch("m2_phonology", ("m2::metrika_3", "m2::metrika_4", "m2::metrika_5", "m2::zvukove_zmeny_se_siri"), run_phonology, _eval_m2_phonology),
    Batch("m2_phonology_triplet", ("m2::metrika_6", "m2::ruznost_seedu"), _run_m2_triplet, _eval_m2_triplet, is_triplet=True),

    Batch("m3_morphology", ("m3::sturtevantuv_paradox", "m3::morfologizace", "m3::produktivni_vzor", "m3::analogie", "m3::zvukove_metriky"), _run_m3_morphology, _eval_m3_morphology),

    Batch("m3b_lexicon", ("m3b::metrika_1", "m3b::metrika_2", "m3b::nova_slova", "m3b::zvukove_metriky"), run_m3b, _eval_m3b_lexicon),
    Batch("m3b_eroded", ("m3b::erodovana_slova",), run_eroded, _eval_m3b_eroded),
    Batch("m3b_taboo", ("m3b::tabu",), run_taboo_pair, _eval_m3b_taboo),

    Batch("m4_control_eroded", ("m4::analytizace", "m4::bez_eroze"), _run_m4_control_eroded, _eval_m4_control_eroded),
    Batch("m4_velky_cyklus", ("m4::velky_cyklus",), run_velky_cyklus, _eval_m4_velky_cyklus),
    Batch("m4_jespersen", ("m4::jespersen",), run_jespersen, _eval_m4_jespersen),

    Batch("m4b_no_case", ("m4b::clen_vznikne", "m4b::bez_padu"), run_no_case, _eval_m4b_no_case),
    Batch("m4b_exaptation", ("m4b::exaptace",), run_exaptation_pair, _eval_m4b_exaptation),
    Batch("m4b_tenseless", ("m4b::jazyk_bez_kategorie",), run_tenseless_pair, _eval_m4b_tenseless),

    Batch("m5_s2_city", ("m5::s2_mesto",), run_s2_city, _eval_m5_s2_city),
    Batch("m5_s2_l2", ("m5::s2_l2",), run_s2_l2_pair, _eval_m5_s2_l2),
    Batch("m5_shifted", ("m5::s3_prechod", "m5::s3_substrat"), run_shifted, _eval_m5_shifted),
    Batch("m5_borrowing", ("m5::vypujcky", "m5::bez_dvojjazycnosti"), run_borrowing, _eval_m5_borrowing),
    Batch("m5_metrika_11", ("m5::metrika_11",), run_metrika_11, _eval_m5_metrika_11),

    Batch("m6a_diglossia", ("m6a::s4_skola", "m6a::s4_bez_skoly", "m6a::skola_sjednoti", "m6a::skola_zmrazena"), run_diglossia_courses, _eval_m6a_diglossia),
    Batch("m6a_codification", ("m6a::psany_kod_stoji",), run_codification, _eval_m6a_codification),

    Batch("m6b_metrika_9", ("m6b::metrika_9",), run_metrika_9, _eval_m6b_metrika_9),
    Batch("m6b_conquered", ("m6b::elita_prejde", "m6b::superstrat"), run_conquered, _eval_m6b_conquered),
    Batch("m6b_market_town", ("m6b::jazyk_trhu",), run_market_town, _eval_m6b_market_town),
    Batch("m6b_loyalty", ("m6b::loajalita",), run_loyalty, _eval_m6b_loyalty),
    Batch("m6b_migration", ("m6b::migrace",), run_migration, _eval_m6b_migration),
    Batch("m6b_ferguson", ("m6b::ferguson",), run_ferguson, _eval_m6b_ferguson),
    Batch("m6b_conversion", ("m6b::nabozenstvi",), run_conversion_pair, _eval_m6b_conversion),

    Batch("m6c_known_tree", ("m6c::strom_odpovida", "m6c::strom_stabilni"), run_known_tree, _eval_m6c_known_tree),
)


def parse_seeds(seed_str: str) -> list[int]:
    """Rozparsuje řetězec seedů jako '101..120' nebo '1,2,3' nebo jejich kombinaci."""
    result: list[int] = []
    for part in seed_str.split(","):
        part = part.strip()
        if ".." in part:
            start_s, end_s = part.split("..", 1)
            result.extend(range(int(start_s), int(end_s) + 1))
        elif part:
            result.append(int(part))
    return sorted(list(dict.fromkeys(result)))


def load_completed_entries(output_path: Path) -> tuple[set[tuple[str, str]], dict[str, dict[str, dict[str, Any]]], dict[str, list[float]]]:
    """Načte již uložené záznamy z JSONL souboru."""
    completed: set[tuple[str, str]] = set()
    results: dict[str, dict[str, dict[str, Any]]] = {}  # batch_id -> trial -> {gate_id: {"passed": bool, "error": str | None}}
    times: dict[str, list[float]] = {}  # batch_id -> list[elapsed_s]

    if not output_path.exists():
        return completed, results, times

    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            batch_id = entry["batch"]
            trial = str(entry["trial"])
            completed.add((batch_id, trial))
            if batch_id not in results:
                results[batch_id] = {}
            results[batch_id][trial] = entry["results"]
            if batch_id not in times:
                times[batch_id] = []
            times[batch_id].append(float(entry["elapsed_s"]))

    return completed, results, times


def format_markdown_table(
    included_gates: list[GateInfo],
    gate_results: dict[str, list[bool]],
    batch_times: dict[str, list[float]],
) -> str:
    """Zformátuje souhrnnou Markdown tabulku výsledků."""
    lines = [
        "| Brána | Seedů dnes | Průchod | Wilson 95 % | Zařazení | k (N=10) | k (N=5) | Čas/seed (s) |",
        "|---|---:|---:|---:|---|---:|---:|---:|",
    ]

    for gate in included_gates:
        res = gate_results.get(gate.gate_id, [])
        total = len(res)
        successes = sum(res)
        times = batch_times.get(gate.batch_id, [])
        avg_time = (sum(times) / len(times)) if times else 0.0

        if total > 0:
            low, high = wilson_interval(successes, total)
            classification = classify_rate(successes, total)
            k_10 = threshold_k(10, low)
            k_5 = threshold_k(5, low)
            rate_str = f"{successes}/{total}"
            wilson_str = f"[{low:.3f}, {high:.3f}]"
            k_10_str = str(k_10)
            k_5_str = str(k_5)
        else:
            rate_str = "0/0"
            wilson_str = "[0.000, 0.000]"
            classification = "slabá"
            k_10_str = "-"
            k_5_str = "-"

        gate_display = f"`{gate.test_file}::{gate.test_func}`"
        lines.append(
            f"| {gate_display} | {gate.seeds_today} | {rate_str} | {wilson_str} | {classification} | {k_10_str} | {k_5_str} | {avg_time:.2f} |"
        )

    return "\n".join(lines)


def run_audit(args: argparse.Namespace) -> None:
    seeds = parse_seeds(args.seeds)
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    completed, stored_results, stored_times = (
        (set(), {}, {}) if args.fresh else load_completed_entries(output_path)
    )

    # Filtrování dávek podle --only
    filter_substr = args.only.lower() if args.only else None
    active_batches: list[Batch] = []
    for b in BATCHES:
        if filter_substr:
            match = filter_substr in b.batch_id.lower() or any(
                filter_substr in gid.lower() for gid in b.gate_ids
            )
            if not match:
                continue
        active_batches.append(b)

    # Shromáždění aktivních bran
    active_gate_ids = {gid for b in active_batches for gid in b.gate_ids}
    included_gates = [g for g in GATE_REGISTRY if g.gate_id in active_gate_ids]

    if not args.summary_only:
        mode = "w" if args.fresh else "a"
        out_file = open(output_path, mode, encoding="utf-8")  # noqa: SIM115
        try:
            print(f"Spouštím audit {len(included_gates)} bran v {len(active_batches)} dávkách na {len(seeds)} trial/seedeck...")
            print(f"Výstupní soubor: {output_path}")

            for batch in active_batches:
                if batch.is_triplet:
                    # Triplet trial pro každý index seedu
                    trials = [
                        (f"{seeds[0] + 3 * idx}_{seeds[0] + 3 * idx + 1}_{seeds[0] + 3 * idx + 2}",
                         (seeds[0] + 3 * idx, seeds[0] + 3 * idx + 1, seeds[0] + 3 * idx + 2))
                        for idx in range(len(seeds))
                    ]
                else:
                    trials = [(str(s), s) for s in seeds]

                for trial_key, trial_arg in trials:
                    if (batch.batch_id, trial_key) in completed:
                        continue

                    start_time = time.perf_counter()
                    state = batch.run_fn(trial_arg)
                    eval_results = batch.eval_fn(state)
                    elapsed = time.perf_counter() - start_time

                    record = {
                        "batch": batch.batch_id,
                        "trial": trial_key,
                        "elapsed_s": round(elapsed, 4),
                        "results": {
                            gid: {"passed": passed, "error": err}
                            for gid, (passed, err) in eval_results.items()
                        },
                    }
                    out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out_file.flush()
                    os.fsync(out_file.fileno())

                    # Uložit do paměti pro finální tabulku
                    completed.add((batch.batch_id, trial_key))
                    if batch.batch_id not in stored_results:
                        stored_results[batch.batch_id] = {}
                    stored_results[batch.batch_id][trial_key] = record["results"]
                    if batch.batch_id not in stored_times:
                        stored_times[batch.batch_id] = []
                    stored_times[batch.batch_id].append(elapsed)

                    del state
                    gc.collect()

                    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    res_parts = [
                        f"{gid.split('::')[-1]}: {'OK' if p else 'FAIL'}"
                        for gid, (p, _) in eval_results.items()
                    ]
                    print(
                        f"[{ts}] {batch.batch_id} trial={trial_key} ({elapsed:.2f}s) -> {', '.join(res_parts)}",
                        flush=True,
                    )
        finally:
            out_file.close()

    # Zpracování agregovaných výsledků pro každou bránu (jen požadované trialy)
    expected_trials_by_batch: dict[str, list[str]] = {}
    for batch in active_batches:
        if batch.is_triplet:
            expected_trials_by_batch[batch.batch_id] = [
                f"{seeds[0] + 3 * idx}_{seeds[0] + 3 * idx + 1}_{seeds[0] + 3 * idx + 2}"
                for idx in range(len(seeds))
            ]
        else:
            expected_trials_by_batch[batch.batch_id] = [str(s) for s in seeds]

    gate_results: dict[str, list[bool]] = {}
    for g in included_gates:
        b_res = stored_results.get(g.batch_id, {})
        passed_list = []
        for tkey in expected_trials_by_batch.get(g.batch_id, []):
            trial_dict = b_res.get(tkey)
            if trial_dict and g.gate_id in trial_dict:
                passed_list.append(bool(trial_dict[g.gate_id]["passed"]))
        gate_results[g.gate_id] = passed_list

    # Výpis souhrnné Markdown tabulky
    print("\n## Výsledky auditu stochastických bran\n")
    table = format_markdown_table(included_gates, gate_results, stored_times)
    print(table)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit stochastických bran enginu v2.")
    parser.add_argument(
        "--seeds",
        default="101..120",
        help="Rozsah nebo seznam seedů pro audit (např. '101..120' nebo '1,2,3', výchozí '101..120')",
    )
    parser.add_argument(
        "--output",
        default="/tmp/v2_gate_rates.jsonl",
        help="Cesta k JSONL souboru s průběžnými výsledky (výchozí '/tmp/v2_gate_rates.jsonl')",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Přepíše výstupní soubor od nuly a ignoruje dřívější výsledky",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Filtruje dávky nebo brány obsahující zadaný podřetězec (např. 'm1_drift' nebo 'jespersen')",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Nespouští simulace, pouze načte existující výstupní soubor a vypíše Markdown tabulku",
    )

    args = parser.parse_args()
    run_audit(args)


if __name__ == "__main__":
    main()
