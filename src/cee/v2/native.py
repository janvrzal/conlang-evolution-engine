"""Volitelné jádro v Rustu (rozšíření ``cee_core``).

Python zůstává referenční implementací: bez sestaveného rozšíření, s nastaveným
``CEE_NATIVE=0`` nebo při neshodě verze rozhraní poběží stávající kód beze
změny a výsledky jsou bitově stejné. Rozšíření se sestavuje z ``rust/cee_core``
(``maturin``); kdo ho nemá, o nic nepřichází.

Verze rozhraní chrání před rozjetím Pythonu a rozšíření: rozšíření se může
nainstalovat do sdíleného prostředí a vidět ho tak i jiná kopie kódu, která
čeká jiné rozhraní. Při neshodě se nepoužije.
"""

from __future__ import annotations

import os
from types import ModuleType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cee.v2.language.segments import SegmentTable

#: Verze rozhraní, kterou tento Python čeká (viz ``INTERFACE_VERSION`` v Rustu).
INTERFACE_VERSION = 14

#: Čísla operací a pravidel přízvuku, jak je zná Rust (``process.rs``).
OPERATIONS = ("change", "replace", "delete", "insert_before", "insert_after", "merge_next", "tone")
RULES = ("initial", "second", "antepenult", "penult", "final")

_UNLOADED: Any = object()
_module: ModuleType | None | Any = _UNLOADED


def _load() -> ModuleType | None:
    global _module
    if _module is _UNLOADED:
        try:
            import cee_core  # type: ignore[import-not-found, unused-ignore]
        except ImportError:
            _module = None
        else:
            _module = cee_core if getattr(cee_core, "INTERFACE_VERSION", None) == INTERFACE_VERSION else None
    return _module


def available() -> bool:
    """Je rozšíření sestavené, nainstalované a má správnou verzi rozhraní?"""
    return _load() is not None


def enabled() -> bool:
    """Použije se Rust? Ne, když je ``CEE_NATIVE=0`` nebo rozšíření chybí."""
    return os.environ.get("CEE_NATIVE", "") != "0" and available()


_SUMS: bool | None = None


def sums_match() -> bool:
    """Sčítá ``numpy`` na tomto stroji párově stejně jako Rust (``pairwise_sum``)?

    Hodnocení v Rustu musí dát bit po bitu totéž co ``np.sum`` po řádcích. Jiná
    verze ``numpy`` či jiná architektura by mohla sčítat v jiném pořadí; pak se
    hodnocení nepočítá v Rustu, ale v Pythonu, ať se otisky neliší. Ověří se jednou
    na polích všech délek, které model používá (a nad ně).
    """
    global _SUMS
    if _SUMS is None:
        _SUMS = False
        module = _load()
        if module is not None:
            import numpy as np

            rng = np.random.default_rng(20261103)
            ok = True
            for width in (*range(1, 40), 64, 119, 120, 127, 128, 129, 200, 513):
                rows = rng.random((3, width)) * rng.choice([1.0, 100.0, 1e-3], size=(3, width))
                ok &= all(
                    module.pairwise_sum(np.ascontiguousarray(row)).hex() == float(total).hex()
                    for row, total in zip(rows, rows.sum(axis=1))
                )
            _SUMS = bool(ok)
    return _SUMS


_LIBM: bool | None = None


def libm_matches() -> bool:
    """Dává knihovna systému v Rustu bit po bitu totéž co ``numpy`` (``exp``, ``log``, ``cos``)?

    Výběr v přenosu používá ``exp``, šum driftu ``log`` a ``cos``. Rust je počítá funkcemi
    knihovny systému, ``numpy`` svými (na jiném stroji či s jinou verzí mohou mít jiný poslední
    bit). Ověří se jednou na náhodných vstupech v rozsahu, který model používá, včetně celého
    ``hash_normal``; kdo neprojde, počítá ``settle`` Python a otisky se nerozejdou.
    """
    global _LIBM
    if _LIBM is None:
        _LIBM = False
        module = _load()
        if module is not None:
            import numpy as np

            from cee.v2.rng import hash_normal

            rng = np.random.default_rng(20261103)
            count = 20000
            empty = np.zeros(0, dtype=np.uint64)
            exps = rng.uniform(-8.0, 8.0, count)
            logs = (rng.integers(0, 1 << 53, count) + 0.5) / float(1 << 53)
            coss = rng.uniform(0.0, 2.0 * np.pi, count)
            keys = rng.integers(0, np.iinfo(np.uint64).max, size=(2, count), dtype=np.uint64)
            ok = np.array_equal(module.libm_probe("exp", exps, empty), np.exp(exps))
            ok &= np.array_equal(module.libm_probe("ln", logs, empty), np.log(logs))
            ok &= np.array_equal(module.libm_probe("cos", coss, empty), np.cos(coss))
            ok &= np.array_equal(
                module.libm_probe("hash_normal", np.zeros(count), np.ascontiguousarray(keys.T.reshape(-1))),
                hash_normal(keys[0], keys[1], pairwise=True),
            )
            _LIBM = bool(ok)
    return _LIBM


def transmit_enabled() -> bool:
    """Počítá se přenos bloku (míšení, výběr, drift) celý v Rustu? Vyžaduje shodu knihovny (:func:`libm_matches`)."""
    return enabled() and libm_matches()


def threads() -> int:
    """Počet vláken Rustu (``CEE_THREADS``, výchozí 1); vlákna dělí jen nezávislé úseky, bity se nemění."""
    try:
        return max(1, int(os.environ.get("CEE_THREADS", "1")))
    except ValueError:
        return 1


def status() -> str:
    """Čitelný popis pro výpisy skriptů: ``rust`` či ``python`` a důvod."""
    if os.environ.get("CEE_NATIVE", "") == "0":
        return "python (CEE_NATIVE=0)"
    if available():
        return "rust"
    return "python (rozšíření cee_core není k dispozici)"


def kernel(name: str) -> Any | None:
    """Funkce jádra v Rustu (bez banky tvarů), nebo ``None`` bez Rustu.

    Jádra, která nepotřebují stav (opora zvukových změn), jsou funkce modulu
    ``cee_core``; volající při ``None`` počítá v Pythonu totéž.
    """
    if not enabled():
        return None
    module = _load()
    assert module is not None
    return getattr(module, name)


def new_bank(table: SegmentTable) -> Any | None:
    """Prázdná banka v Rustu nad tabulkou hlásek, nebo ``None`` bez Rustu."""
    if not enabled():
        return None
    module = _load()
    assert module is not None
    return module.NativeBank(table.boundary, table.vowel_mask, glide_mask(table))


def glide_mask(table: SegmentTable) -> Any:
    """Maska polosamohlásek (``SegmentTable.sonority == 3``) s hranicí slova na konci.

    Vektorově to samé, co ``sonority``: ne slabičná, sonorantní a nesouhláskové.
    """
    import numpy as np

    vectors, index = table.vectors, table.index
    syllabic = vectors[:, index["syl"]] == 1
    sonorant = vectors[:, index["son"]] == 1
    consonantal = vectors[:, index["cons"]] == 1
    return np.append(~syllabic & sonorant & ~consonantal, False)


def new_cells(groups: int, capacity: int) -> Any | None:
    """Prázdné uložení buněk bloku fondů v Rustu (``NativeCells``), nebo ``None`` bez Rustu."""
    if not enabled():
        return None
    module = _load()
    assert module is not None
    return module.NativeCells(groups, capacity, threads())


def cells_from_flat(groups: int, capacity: int, *state: Any) -> Any | None:
    """Uložení buněk v Rustu ze stavu ``flat``, nebo ``None`` bez Rustu."""
    if not enabled():
        return None
    module = _load()
    assert module is not None
    return module.NativeCells.from_flat(groups, capacity, *state, threads())


def new_step(*arrays: Any) -> Any:
    """Vstupy kroku pro přenos v Rustu (``NativeStep``)."""
    module = _load()
    assert module is not None
    return module.NativeStep(*arrays)


def new_sound_index(scales: list[float]) -> Any | None:
    """Index prostředí a opor zvukových změn v Rustu, nebo ``None`` (bez Rustu či bez shody párových součtů).

    Míry rodin se v Rustu sčítají párově jako ``np.sum``; pokud numpy na stroji sčítá jinak
    (:func:`sums_match`), počítá index Python.
    """
    if not enabled() or not sums_match():
        return None
    module = _load()
    assert module is not None
    return module.SoundIndex(scales)


def new_site_index() -> Any | None:
    """Index míst morfologických, sémantických a syntaktických změn v Rustu, nebo ``None``.

    Míry se v Rustu sčítají párově jako ``np.sum``; pokud numpy na stroji sčítá jinak
    (:func:`sums_match`), počítá index Python.
    """
    if not enabled() or not sums_match():
        return None
    module = _load()
    assert module is not None
    return module.SiteIndex()


_DISPERSION: bool | None = None


def dispersion_matches() -> bool:
    """Dávají souřadnice samohlásek v Rustu (součin místo ``** 2``) bit po bitu totéž co Python?

    Zisk rozptylu vokálů (``assessment._nearest``) počítá ``(a - b) ** 2``; Rust počítá ``d * d``.
    Rozdíly souřadnic jsou z malé množiny hodnot (viz ``SegmentTable.vowel_coordinates``), ověří se
    všechny rozdíly vzájemně (a znaménka); jinak se hodnocení v Rustu nepoužije.
    """
    global _DISPERSION
    if _DISPERSION is None:
        _DISPERSION = False
        if _load() is not None:
            values = [0.0, 0.5, 0.6, 1.0, 2.0]
            differences = {a - b for a in values for b in values}
            _DISPERSION = all((d ** 2).hex() == (d * d).hex() for d in differences)
    return _DISPERSION


_PLAIN_SUM: bool | None = None


def plain_sum_matches() -> bool:
    """Sčítá vestavěné ``sum`` čísla typu ``float`` prostě zleva doprava (Python do 3.11)?

    Frekvence užití lexému (``World.usage_frequency``) je ``sum`` frekvencí pojmů v pořadí vložení; Rust
    (``form_assess.rs``) je sčítá zleva doprava. Python od 3.12 sčítá kompenzovaně a poslední bit by se
    mohl lišit; pak se hodnocení tvarů v Rustu nepoužije.
    """
    global _PLAIN_SUM
    if _PLAIN_SUM is None:
        samples = ([0.1] * 10, [0.7, 0.2, 0.1], [1e16, 1.0, -1e16, 0.3], [0.1, 0.2, 0.3, 0.4, 0.45, 0.01])
        ok = True
        for values in samples:
            plain = 0.0
            for value in values:
                plain += value
            ok &= sum(values).hex() == plain.hex()
        _PLAIN_SUM = bool(ok)
    return _PLAIN_SUM
_OBSERVE: bool | None = None


def observe_matches() -> bool:
    """Dává Rust v pozorování bit po bitu totéž co ``numpy``?

    Pozorování stojí na čtyřech věcech mimo čisté součty a součiny: skalární součin řádků
    ``float32`` (``a @ b`` volá BLAS, jehož pořadí sčítání neznáme; Rust volá na macOS tutéž
    funkci Accelerate), ``hypot`` (vzdálenost sousedů na mapě), celočíselné dělení ``//``
    s opravou zaokrouhlení a součet ``float32`` přes osy ``(0, 3)`` matice vzdáleností. Ověří se
    všechny jednou na náhodných vstupech; kdo neprojde (jiný stroj, jiný BLAS), počítá
    pozorování Python a otisky se nerozejdou.
    """
    global _OBSERVE
    if _OBSERVE is None:
        _OBSERVE = False
        module = _load()
        if module is not None and sums_match():
            import numpy as np

            from cee.v2.observe import _distance_totals

            rng = np.random.default_rng(20261103)
            ok = True
            # Řádky jedné matice, jako v shlukování: šířky jsou násobky 13 (vložení má 13 rozměrů).
            for columns in (1, 2, 3, 7, 40, 101, 400, 2000):
                width = 13 * columns
                matrix = (rng.random((9, width)) * (rng.random((9, width)) < 0.4) * 3.7).astype(np.float32)
                first = rng.integers(0, 9, 40)
                second = rng.integers(0, 9, 40)
                expected = np.array([np.float32(matrix[a] @ matrix[b]) for a, b in zip(first, second)])
                found = module.observe_dot_probe(matrix, first, second)
                ok &= bool(np.array_equal(found.view(np.uint32), expected.view(np.uint32)))
            xs = rng.uniform(-300.0, 300.0, 4000)
            ys = rng.uniform(-300.0, 300.0, 4000)
            ok &= bool(np.array_equal(module.observe_hypot_probe(xs, ys), np.hypot(xs, ys)))
            for size in (0.37, 5.0, 12.5, 1e-3):
                points = np.concatenate([xs, np.round(xs / size) * size, [0.0, -0.0, size, -size, 3 * size]])
                expected = np.array([float(np.float64(x) // np.float64(size)) for x in points])
                found = module.observe_floor_divide_probe(points, size)
                ok &= bool(np.array_equal(found, expected) and np.array_equal(np.signbit(found), np.signbit(expected)))
            # Součet přes osy (0, 3): různé kapacity slotů, počty řádků a skupin, bloky po jednom řádku i celé.
            for capacity, rows, groups, chunk in ((1, 2, 3, 4_000_000), (3, 4, 6, 4_000_000), (8, 3, 5, 4_000_000),
                                                  (9, 2, 7, 50), (17, 5, 4, 4_000_000), (5, 6, 9, 100),
                                                  (4, 7, 5, 1)):
                freqs = rng.random((rows + 1, groups, capacity)) * (rng.random((rows + 1, groups, capacity)) < 0.7)
                present = rng.random((rows + 1, groups)) < 0.85
                chosen = np.arange(0, rows + 1, 2, dtype=np.int64)
                zeros = np.zeros(len(chosen), dtype=np.int64)
                expected = _distance_totals([(freqs, present, chosen, zeros)], groups, chunk)
                found = module.observe_distance_totals([(freqs, present, chosen, zeros)], groups, chunk, 1)
                ok &= bool(np.array_equal(found, expected)) and found.tobytes() == expected.tobytes()
            _OBSERVE = bool(ok)
    return _OBSERVE


def observe_enabled() -> bool:
    """Počítá se pozorování v Rustu (a shodují se párové součty a knihovny, viz :func:`observe_matches`)?"""
    return enabled() and sums_match() and observe_matches()


def assess_enabled() -> bool:
    """Počítá se hodnocení v Rustu (sčítá-li numpy párově stejně, platí zkouška rozptylu a ``sum`` je prosté)?"""
    return enabled() and sums_match() and dispersion_matches() and plain_sum_matches()


def new_assess_index() -> Any | None:
    """Index hodnocení v Rustu (``cee_core.AssessIndex``), nebo ``None``."""
    if not assess_enabled():
        return None
    module = _load()
    assert module is not None
    return module.AssessIndex()


def new_code() -> Any | None:
    """Prázdný stav fonologie kódu v Rustu (fronty, dominantní kořeny), nebo ``None`` bez Rustu."""
    if not enabled():
        return None
    module = _load()
    assert module is not None
    return module.NativeCode()


def sync_names(handle: Any, names: list[str]) -> None:
    """Doplní bance v Rustu jména morfémů, která ještě nezná (řazení front podle jmen)."""
    module = _load()
    assert module is not None
    known = module.names_count(handle)
    if known < len(names):
        module.extend_names(handle, known, names[known:])


def restore_code(state: Any) -> Any:
    """Stav fonologie kódu v Rustu z neutrální podoby (``NativeCode.export``)."""
    module = _load()
    assert module is not None
    return module.restore_code(state)


def restructure_groups(*arguments: Any) -> Any:
    """Fonologizace skupin jedním voláním (``cee_core.restructure_groups``)."""
    module = _load()
    assert module is not None
    return module.restructure_groups(*arguments)
