"""Testy přenositelného proudu náhody ``rng.Stream`` (krok A6 přípravy na Rust).

Pevné referenční hodnoty slouží zároveň jako zlatá data pro Rust: stejný
algoritmus (viz docstring ``Stream``) musí dát stejná čísla. Celá čísla
a ``random()`` se musí shodovat přesně, hodnoty z libm (``normal``) s
tolerancí posledního bitu.
"""

import math

import numpy as np
import pytest

from cee.v2.rng import Stream, cumulative, hash_poisson, poisson_inversion, stable_int

_PARTS = ("innovation", 12, "g1", "c1", "x")


def _stream() -> Stream:
    return Stream(7, *_PARTS)


def test_splitmix64_ma_znamy_prubeh_ze_stavu_nula():
    # Publikované výstupy SplitMix64 se stavem 0 (Vigna).
    stream = Stream.from_key(0)
    assert [stream.next_u64() for _ in range(3)] == [
        0xE220A8397B1DCDAF,
        0x6E789E6AA1B965F4,
        0x06C45D188009454F,
    ]


def test_klic_proudu_a_prvni_tahy_jsou_pevne():
    assert stable_int("stream", 7, *_PARTS) == 5297385815531639756
    stream = _stream()
    assert stream.state == 5297385815531639756
    assert [stream.next_u64() for _ in range(3)] == [
        1482785598662770846,
        9707476936427561035,
        7700042200845430622,
    ]


def test_zaporny_seed_se_bere_modulo_2_64():
    assert Stream(-1, "a").state == Stream(2**64 - 1, "a").state


def test_random_pevne_hodnoty_a_rozsah():
    stream = _stream()
    assert [stream.random() for _ in range(3)] == [
        0.08038196837001976,
        0.5262433791913845,
        0.41742012411933394,
    ]
    values = [Stream(1, "r", i).random() for i in range(2000)]
    assert all(0.0 <= value < 1.0 for value in values)


def test_integers_pevne_hodnoty():
    stream = _stream()
    assert [stream.integers(10) for _ in range(8)] == [0, 5, 4, 3, 4, 2, 0, 4]
    assert [stream.integers(1000003) for _ in range(3)] == [263667, 263558, 116115]


def test_integers_jedna_vraci_nulu_a_spotrebuje_jeden_tah():
    stream = _stream()
    reference = _stream()
    assert stream.integers(1) == 0
    reference.next_u64()
    assert stream.state == reference.state
    with pytest.raises(ValueError):
        stream.integers(0)


def test_integers_odmita_zkreslene_tahy_lemirovou_metodou():
    # n = 3: práh = (2**64 - 3) % 3 = 1, takže x = 0 (low = 0 < 1) se zahodí.
    draws = iter([0, 1 << 63])

    class Scripted(Stream):
        __slots__ = ()

        def next_u64(self) -> int:
            return next(draws)

    stream = Scripted.from_key(0)
    assert stream.integers(3) == 1  # (2**63 * 3) >> 64
    assert next(draws, None) is None


def test_integers_je_rovnomerne_chi_kvadrat():
    n, draws = 6, 60000
    stream = Stream(3, "chi", "integers")
    counts = [0] * n
    for _ in range(draws):
        counts[stream.integers(n)] += 1
    chi2 = sum((count - draws / n) ** 2 / (draws / n) for count in counts)
    assert chi2 < 20.5  # 99,9. percentil χ² s 5 stupni volnosti je 20,5


def test_choice_pevne_hodnoty_a_nulova_vaha():
    stream = _stream()
    picks = [stream.choice(4, [0.1, 0.0, 0.6, 0.3]) for _ in range(8)]
    assert picks == [0, 2, 2, 2, 2, 2, 0, 2]
    assert 1 not in picks


def test_choice_chi_kvadrat_a_nulove_vahy_se_nevybiraji():
    weights = [0.0, 2.0, 0.5, 0.0, 1.0, 3.5, 0.0]
    draws = 70000
    stream = Stream(5, "chi", "choice")
    counts = [0] * len(weights)
    for _ in range(draws):
        counts[stream.choice(len(weights), np.array(weights))] += 1
    total = sum(weights)
    assert all(counts[i] == 0 for i, w in enumerate(weights) if w == 0.0)
    chi2 = sum(
        (counts[i] - draws * w / total) ** 2 / (draws * w / total)
        for i, w in enumerate(weights) if w > 0.0
    )
    assert chi2 < 18.5  # 99,9. percentil χ² se 3 stupni volnosti je 16,3


def test_choice_bez_vah_je_rovnomerny_vyber():
    stream = _stream()
    reference = _stream()
    assert [stream.choice(10) for _ in range(5)] == [reference.integers(10) for _ in range(5)]


def test_choice_kumulativni_soucet_je_postupny_v_poradi_indexu():
    weights = [0.1] * 10
    cumulated = cumulative(np.array(weights))
    running = 0.0
    for index, weight in enumerate(weights):
        running += weight
        assert cumulated[index] == running  # přesně, ne np.cumsum / math.fsum


def test_choice_zaokrouhleni_na_konci_vybere_posledni_kladnou_vahu():
    cumulated = cumulative([0.3, 0.7, 0.0, 0.0])
    # u = 1 sice random() nevrátí, ale zaokrouhlení u * total na total ano.
    assert Stream.pick(cumulated, 1.0) == 1
    assert Stream.pick(cumulated, 0.0) == 0
    assert Stream.pick(cumulative([0.0, 0.0, 2.0]), 0.0) == 2
    assert Stream.pick(cumulated, 1.0 - 2.0**-53) == 1


def test_choice_odmitne_chybne_vahy():
    stream = _stream()
    for bad in ([], [0.0, 0.0], [1.0, -1.0], [1.0, math.inf], [1.0, math.nan]):
        with pytest.raises(ValueError):
            stream.choice(len(bad), bad)


def test_normal_pevne_hodnoty():
    stream = _stream()
    expected = [-3.3224515086957886, -0.9601533922812364, 0.24756990731896591]
    values = [stream.normal(0.0, 1.5) for _ in range(3)]
    assert values == pytest.approx(expected, rel=1e-12)


def test_normal_prumer_a_rozptyl():
    stream = Stream(9, "stats", "normal")
    values = np.array([stream.normal(2.0, 1.5) for _ in range(40000)])
    assert abs(values.mean() - 2.0) < 4 * 1.5 / math.sqrt(len(values))
    assert abs(values.std() / 1.5 - 1.0) < 0.02
    assert abs(float(np.mean(((values - 2.0) / 1.5) ** 4)) - 3.0) < 0.15  # špičatost


def test_poisson_pevne_hodnoty():
    stream = _stream()
    got = [stream.poisson(lam) for lam in (0.5, 4.0, 29.0, 30.0, 31.0, 100.0, 500.0)]
    assert got == [0, 4, 28, 27, 27, 85, 504]
    assert _stream().poisson(0.0) == 0


@pytest.mark.parametrize("lam", [0.7, 4.0, 30.0, 45.0, 250.0])
def test_poisson_prumer_a_rozptyl(lam):
    stream = Stream(11, "stats", "poisson", lam)
    values = np.array([stream.poisson(lam) for _ in range(20000)], dtype=float)
    assert abs(values.mean() - lam) < 4 * math.sqrt(lam / len(values))
    assert abs(values.var() / lam - 1.0) < 0.06


def test_poisson_inverze_je_po_kusech_nejvys_30():
    assert poisson_inversion(5.0, 0.0) == 0
    assert poisson_inversion(5.0, math.exp(-5.0) * 1.0000001) == 1
    # Velká střední hodnota se dělí na stejné kusy; 61 → 3 kusy po 61 / 3.
    stream = _stream()
    reference = _stream()
    expected = sum(poisson_inversion(61.0 / 3, reference.random()) for _ in range(3))
    assert stream.poisson(61.0) == expected
    assert stream.state == reference.state


def test_hash_poisson_velke_stredni_hodnoty_pevne_a_bez_numpy_generatoru(monkeypatch):
    rows = np.array([1, 2, 3], dtype=np.uint64)
    columns = np.array([5, 6], dtype=np.uint64)
    expected = np.array([[50.0, 100.0], [31.0, 500.0], [3.0, 40.0]])

    def forbidden(*args, **kwargs):
        raise AssertionError("numpy generátor v hash_poisson")

    monkeypatch.setattr(np.random, "PCG64", forbidden)
    got = hash_poisson(rows, columns, expected)
    assert got.tolist() == [[51, 89], [37, 506], [2, 35]]


def test_hash_poisson_velke_hodnoty_maji_spravny_prumer():
    keys = np.arange(4000, dtype=np.uint64)
    column = np.array([77], dtype=np.uint64)
    got = hash_poisson(keys, column, np.full((4000, 1), 60.0))
    assert abs(got.mean() - 60.0) < 4 * math.sqrt(60.0 / 4000)


def test_proudy_jsou_nezavisle_na_poradi_volani():
    alone = Stream(1, "a", 1)
    alone_values = [alone.random() for _ in range(5)]
    first, other = Stream(1, "a", 1), Stream(1, "a", 2)
    interleaved = []
    for _ in range(5):
        other.random()
        other.normal()
        interleaved.append(first.random())
    assert interleaved == alone_values
    assert Stream(1, "a", 2).random() != alone_values[0]
    assert Stream(2, "a", 1).random() != alone_values[0]


def test_stejne_casti_davaji_stejny_proud_a_ruzne_ruzny():
    assert Stream(1, "ab", "c").next_u64() == Stream(1, "ab", "c").next_u64()
    assert Stream(1, "ab", "c").next_u64() != Stream(1, "a", "bc").next_u64()
