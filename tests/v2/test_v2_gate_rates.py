"""Jednotkové testy pro statistické funkce a audit stochastických bran.

Ověřuje Wilsonův interval, binomickou CDF, prahy k z N, klasifikaci bran,
zachytávání pádů přes passes, úplnost registru 52 bran vůči AST testů
a ukládání s navázáním (resume).
"""

import argparse
import ast
from pathlib import Path

import pytest

from scripts.v2_gate_rates import (
    EXCLUDED_DETERMINISTIC_TESTS,
    GATE_REGISTRY,
    load_completed_entries,
    parse_seeds,
    run_audit,
)
from tests.v2.gate_checks import (
    assert_k_of_n,
    binomial_cdf_lt,
    classify_rate,
    passes,
    threshold_k,
    wilson_interval,
)


def test_wilson_interval_values_and_symmetry():
    # 0/20: dolní mez musí být 0.0, horní kladná
    low_0, high_0 = wilson_interval(0, 20)
    assert low_0 == 0.0
    assert 0.0 < high_0 < 0.25

    # 20/20: horní mez musí být 1.0, dolní vysoká
    low_20, high_20 = wilson_interval(20, 20)
    assert high_20 == 1.0
    assert 0.75 < low_20 < 1.0

    # Symetrie: low(x, n) == 1 - high(n - x, n)
    assert pytest.approx(low_0) == 1.0 - high_20
    assert pytest.approx(high_0) == 1.0 - low_20

    # 10/20: střed je 0.5, symetrický interval kolem 0.5
    low_10, high_10 = wilson_interval(10, 20)
    assert 0.25 < low_10 < 0.5 < high_10 < 0.75
    assert pytest.approx(0.5 - low_10) == high_10 - 0.5

    # 19/20: robustní úspěšnost
    low_19, high_19 = wilson_interval(19, 20)
    assert 0.75 < low_19 < 0.99
    assert 0.95 < high_19 <= 1.0
    assert pytest.approx(low_19) == 1.0 - wilson_interval(1, 20)[1]

    # Neplatné vstupy
    with pytest.raises(ValueError):
        wilson_interval(-1, 20)
    with pytest.raises(ValueError):
        wilson_interval(21, 20)
    with pytest.raises(ValueError):
        wilson_interval(5, 0)


def test_binomial_cdf_lt_edge_cases():
    # k <= 0
    assert binomial_cdf_lt(0, 10, 0.5) == 0.0
    assert binomial_cdf_lt(-2, 10, 0.5) == 0.0

    # k > n
    assert binomial_cdf_lt(11, 10, 0.5) == 1.0
    assert binomial_cdf_lt(15, 10, 0.5) == 1.0

    # p == 0.0
    assert binomial_cdf_lt(0, 10, 0.0) == 0.0
    assert binomial_cdf_lt(1, 10, 0.0) == 1.0
    assert binomial_cdf_lt(5, 10, 0.0) == 1.0

    # p == 1.0
    assert binomial_cdf_lt(10, 10, 1.0) == 0.0
    assert binomial_cdf_lt(11, 10, 1.0) == 1.0

    # Neplatné vstupy
    with pytest.raises(ValueError):
        binomial_cdf_lt(5, -1, 0.5)
    with pytest.raises(ValueError):
        binomial_cdf_lt(5, 10, -0.1)
    with pytest.raises(ValueError):
        binomial_cdf_lt(5, 10, 1.1)


def test_threshold_k_properties():
    # Ověření pro různé n a p_lower
    for n in (5, 10, 20):
        prev_k = 0
        for p_int in range(1, 100):
            p = p_int / 100.0
            k = threshold_k(n, p, alpha=0.01)
            # Monotónnost v p_lower: k nesmí klesat s rostoucím p
            assert k >= prev_k
            prev_k = k

            # Garance definice: P(Bin(n, p) < k) <= 0.01
            assert binomial_cdf_lt(k, n, p) <= 0.01 + 1e-12

            # Největší takové k: pro k < n musí k + 1 překročit 0.01
            if k < n:
                assert binomial_cdf_lt(k + 1, n, p) > 0.01 - 1e-12


def test_classify_rate():
    # 20 pokusů
    assert classify_rate(20, 20) == "robustní"
    assert classify_rate(19, 20) == "robustní"
    assert classify_rate(18, 20) == "křehká"
    assert classify_rate(10, 20) == "křehká"
    assert classify_rate(9, 20) == "slabá"
    assert classify_rate(0, 20) == "slabá"

    # Neplatné vstupy
    with pytest.raises(ValueError):
        classify_rate(-1, 20)
    with pytest.raises(ValueError):
        classify_rate(5, 0)
    with pytest.raises(ValueError):
        classify_rate(25, 20)


def test_passes_and_assert_k_of_n():
    def pass_fn():
        assert True

    def fail_fn():
        assert False, "něco selhalo"

    def error_fn():
        raise RuntimeError("závažná systémová chyba")

    # passes zachytí AssertionError
    assert passes(pass_fn) == (True, None)
    passed, err = passes(fail_fn)
    assert not passed
    assert err is not None and "něco selhalo" in err

    # Jakákoliv jiná výjimka musí probublat!
    with pytest.raises(RuntimeError, match="závažná systémová chyba"):
        passes(error_fn)

    # assert_k_of_n
    # Úspěšný případ
    assert_k_of_n([1, 2, 3], [1, 2], k=2)

    # Selhání
    with pytest.raises(AssertionError) as exc_info:
        assert_k_of_n([1, 2, 3], [1], k=2, failures={2: "chyba 2", 3: "chyba 3"})
    msg = str(exc_info.value)
    assert "1/3" in msg
    assert ">= 2" in msg
    assert "[1]" in msg
    assert "seed 2: chyba 2" in msg
    assert "seed 3: chyba 3" in msg


def test_gate_registry_completeness():
    """Zkontroluje přes AST všech 10 souborů bran, že žádná brána nevypadla."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    tests_v2 = repo_root / "tests" / "v2"

    gate_files = sorted(tests_v2.glob("test_v2_m*_gate.py"))
    assert len(gate_files) == 10, f"Očekáváno 10 souborů bran, nalezeno: {len(gate_files)}"

    all_test_functions: set[str] = set()
    for file_path in gate_files:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                all_test_functions.add(f"{file_path.name}::{node.name}")

    registered_tests = {f"{g.test_file}::{g.test_func}" for g in GATE_REGISTRY}

    # Ověříme přesný počet bran
    assert len(GATE_REGISTRY) == 52, f"Registr musí mít přesně 52 bran, má: {len(GATE_REGISTRY)}"
    assert len(registered_tests) == 52, "Každá brána v registru musí ukazovat na unikátní testovací funkci"
    assert len(EXCLUDED_DETERMINISTIC_TESTS) == 10, "Deterministických testů musí být přesně 10"

    # Množiny musí být disjunktní
    overlap = registered_tests & EXCLUDED_DETERMINISTIC_TESTS
    assert not overlap, f"Překryv mezi stochastickými branami a deterministickými testy: {overlap}"

    # Sjednocení musí přesně pokrýt všechny test_* funkce v souborech bran
    expected_all = registered_tests | EXCLUDED_DETERMINISTIC_TESTS
    missing = all_test_functions - expected_all
    extra = expected_all - all_test_functions
    assert not missing, f"V souborech bran jsou testy, které chybí v registru i vyloučených: {missing}"
    assert not extra, f"V registru nebo vyloučených jsou neexistující testy: {extra}"
    assert len(all_test_functions) == 62


def test_parse_seeds():
    assert parse_seeds("101..105") == [101, 102, 103, 104, 105]
    assert parse_seeds("1, 2, 5") == [1, 2, 5]
    assert parse_seeds("101..103, 105, 102") == [101, 102, 103, 105]


def test_audit_save_and_resume(tmp_path: Path):
    """Ověří ukládání a navázání (resume) na superrychlé dávce m1_drift."""
    output_file = tmp_path / "test_rates.jsonl"

    # 1. Běh na seedu 101
    args1 = argparse.Namespace(
        seeds="101..101",
        output=str(output_file),
        fresh=True,
        only="m1_drift",
        summary_only=False,
    )
    run_audit(args1)

    completed1, results1, _ = load_completed_entries(output_file)
    assert ("m1_drift", "101") in completed1
    assert len(completed1) == 1
    assert "m1::velka_skupina_drift" in results1["m1_drift"]["101"]

    # 2. Běh naváže na seed 101..102 (seed 101 se znovu nepočítá)
    # Změníme data v prvním řádku tak, abychom poznali, že nebyl přepsán/zdvojen
    with open(output_file, "r", encoding="utf-8") as f:
        first_line = f.readline()

    args2 = argparse.Namespace(
        seeds="101..102",
        output=str(output_file),
        fresh=False,
        only="m1_drift",
        summary_only=False,
    )
    run_audit(args2)

    with open(output_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    assert len(lines) == 2, f"Očekávány 2 řádky (1 z 1. běhu, 1 z navázání), nalezeno {len(lines)}"
    assert lines[0] == first_line.strip()

    completed2, results2, _ = load_completed_entries(output_file)
    assert ("m1_drift", "101") in completed2
    assert ("m1_drift", "102") in completed2
    assert len(completed2) == 2

    # 3. Test --summary-only
    args3 = argparse.Namespace(
        seeds="101..102",
        output=str(output_file),
        fresh=False,
        only="m1_drift",
        summary_only=True,
    )
    # Spustí se a nevypíše chybu
    run_audit(args3)


def test_converted_gates_thresholds_match_formula():
    """Ověří, že prahy k převedených bran přesně odpovídají vzorci threshold_k."""
    # (úspěchů v auditu x, celkem v auditu total, N seedů brány, k práh brány)
    cases = (
        (11, 20, 12, 1),  # m3b::tabu, m5::s3_substrat
        (15, 20, 10, 2),  # m4::velky_cyklus, m4b::exaptace, m6b::migrace
        (16, 20, 10, 2),  # m6b::superstrat, m6b::jazyk_trhu
        (8, 20, 19, 1),   # m4::jespersen
        (35, 40, 10, 4),  # m3::morfologizace
        (20, 20, 10, 5),  # m3::zvukove_metriky
    )
    for x, total, n, expected_k in cases:
        p_lower, _ = wilson_interval(x, total)
        k = threshold_k(n, p_lower)
        assert k == expected_k, f"Pro x={x}, total={total}, n={n} vyšlo k={k}, očekáváno {expected_k}"


def test_evaluate_seeds_helper():
    """Ověří pomocnou funkci evaluate_seeds."""
    from tests.v2.gate_checks import evaluate_seeds

    runs = {1: 10, 2: 5, 3: 20}

    def check(val: int):
        assert val >= 10, "příliš nízká hodnota"

    evaluate_seeds(runs, check, k=2)

    with pytest.raises(AssertionError) as exc_info:
        evaluate_seeds(runs, check, k=3)
    assert "2/3" in str(exc_info.value)
    assert "seed 2: příliš nízká hodnota" in str(exc_info.value)
