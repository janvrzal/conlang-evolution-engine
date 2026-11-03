"""Přenos jako čisté funkce nad poli (krok A5 přípravy na Rust, zbytek).

Funkce tady dostanou pole a čísla, vrátí pole a nesahají na svět, skupiny ani
kódy. Třídy ``cee.v2.transmission`` (``prepare``, ``transmit``, ``StepInputs``,
``CrossFlow``), ``cee.v2.contact`` a ``cee.v2.institutions`` z objektů
poskládají vstupní pole, zavolají funkci odtud a výsledek jen předají dál.
Rust (``cee_core``) počítá ``hear``, ``settle`` a ``normalized`` bit po bitu stejně; Python
zůstává referenční implementací (``hear_python``, ``settle_python``, ``normalized_python``)
a běží bez rozšíření nebo s ``CEE_NATIVE=0``. ``settle`` v Rustu vyžaduje, aby ``exp``,
``log`` a ``cos`` knihovny systému daly totéž co ``numpy`` (``native.libm_matches``).

Co je čistá funkce polí:

- **příprava kroku** (jednou za krok, osa = skupiny): ``mixing_from_links``
  (matice vazeb z řídké tabulky vazeb), ``components`` (propojené komponenty
  sítě), ``foreign_mask``, ``elite_shares`` a ``trade_shares`` (podíly kanálů
  vazeb mezi jazyky), ``neighbor_fraction``, ``internal_blocks`` a
  ``cross_blocks`` (bloky matice po komponentách), ``channel_weights``
  (váhy interference, čtení, školy a liturgie), ``cohort_scales``;
- **faktory proměnných** (osa = proměnné bloku): ``borrowing_factors`` (filtr
  výpůjček kanálu), ``interference_factors``, ``reading_factors``,
  ``school_factors``, ``liturgy_factors``. Vstupem jsou sloupce vlastností
  proměnných (druh, frekvence a doména pojmu, přenositelnost);
- **přenos bloku** (osy proměnné × skupiny × sloty): ``mix`` (míšení po
  komponentách), ``hear`` (co skupiny slyší od sousedů, jiných jazyků a z
  kanálů), ``settle`` (výběr podle tlaků, trend, drift, ustálení a základna
  trendu), ``normalized``.

Na objektech zůstává: sbírání vlastností skupin a proměnných ze světa (kód
skupiny, vazby, obchodní cesty, frekvence a doména pojmu), mocnina
přenositelnosti a prestiže (``**`` v Pythonu, protože ``numpy.power`` se
v posledním bitu může lišit), klíče driftu (``stable_int``, blake2b) a tlaky
na varianty (``Pressure.scores``) mezi ``hear`` a ``settle``.

Pořadí sčítání je součástí smlouvy a Rust ho musí zopakovat:

- ``mix`` sčítá vstup skupiny **postupně přes zdroje**: pro cílovou skupinu
  se jednotlivé součiny ``váha × podíl`` přičítají striktně zleva doprava
  podle vzestupného čísla zdroje a vynechají se zdroje s nulovou vahou
  (nulový součin součet nezmění, takže výsledek nezávisí na tom, kolik nulových
  sloupců matice obsahuje). Součin se zaokrouhlí zvlášť, pak se přičte; žádné
  sloučené násobení se sčítáním (FMA). Rust to zopakuje bit po bitu. Dřív to
  byl BLAS ``@``, jehož pořadí součtů závisí na knihovně, verzi a tvaru matice
  (vědomá změna otisků, ``scripts/v2_digests.py``);
- ``normalized`` sčítá seřazené hodnoty slotů striktně zleva doprava;
- ``mixing_from_links`` sčítá řádky ``numpy.sum`` (párově, viz
  ``cee_core.pairwise_sum``);
- ``settle`` počítá šum driftu přes ``rng.hash_normal(..., pairwise=True)``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import numpy.typing as npt

from cee.v2 import native
from cee.v2.rng import hash_normal

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]
IntArray = npt.NDArray[np.intp]
KeyArray = npt.NDArray[np.uint64]

#: Pořadí druhů proměnných jako ``tables.VARIABLE_KINDS`` (kód = pozice).
KINDS = ("process", "lexical", "form", "construction", "prosody")
LEXICAL = KINDS.index("lexical")



def kind_table(mapping: Mapping[str, float]) -> tuple[float, ...]:
    """Základ filtru podle druhu proměnné jako pole v pořadí ``KINDS`` (chybějící druh = 0)."""
    return tuple(mapping.get(kind, 0.0) for kind in KINDS)


# --- příprava kroku: sít skupin ----------------------------------------------------


def mixing_from_links(
    link_source: IntArray,
    link_target: IntArray,
    link_strength: FloatArray,
    place: IntArray,
    power: FloatArray,
    openness: FloatArray,
) -> FloatArray:
    """Od koho se která skupina učí: řádek g je rozdělení vstupu skupiny g.

    ``link_source`` a ``link_target`` jsou čísla skupin v registru (CSR tabulka
    vazeb světa) a ``link_strength`` síla vazby; ``place[číslo]`` je sloupec
    skupiny v kroku (−1 = skupina v kroku není). ``power`` je prestiž cíle
    umocněná na ``alpha`` (počítá objekt, ``**`` v Pythonu) a ``openness``
    otevřenost skupiny, obojí po skupinách kroku.

    Na diagonále je vlastní skupina s vahou ``1 − otevřenost``. Zbytek se
    rozdělí mezi sousedy úměrně síle vazby a prestiži zdroje. Skupina bez
    sousedů se učí jen sama od sebe (její otevřenost se bere za nulu).
    """
    size = len(power)
    rows, columns = place[link_source], place[link_target]
    kept = (rows >= 0) & (columns >= 0)
    weights = np.zeros((size, size))
    weights[rows[kept], columns[kept]] = link_strength[kept] * power[columns[kept]]
    totals = weights.sum(axis=1)
    openness = np.where(totals > 0, openness, 0.0)
    safe = np.where(totals > 0, totals, 1.0)
    mixing: FloatArray = (1.0 - openness)[:, None] * np.eye(size) + openness[:, None] * (weights / safe[:, None])
    return mixing


def components(mixing: FloatArray) -> list[IntArray]:
    """Propojené komponenty sítě (kdo se od koho, i nepřímo, učí).

    Výstup je seřazený podle nejmenšího člena komponenty, členové vzestupně.
    """
    parent = list(range(len(mixing)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for first, second in zip(*np.nonzero(mixing)):
        a, b = root(int(first)), root(int(second))
        if a != b:
            parent[max(a, b)] = min(a, b)
    members: dict[int, list[int]] = {}
    for index in range(len(mixing)):
        members.setdefault(root(index), []).append(index)
    return [np.array(items, dtype=np.intp) for _, items in sorted(members.items())]


def foreign_mask(languages: IntArray) -> BoolArray:
    """``mask[i, j]``: skupiny i a j mluví jiným jazykem (``languages`` jsou kódy jazyků)."""
    mask: BoolArray = languages[:, None] != languages[None, :]
    return mask


def elite_shares(is_elite: BoolArray) -> FloatArray:
    """Podíl vazby (učící se skupina × zdroj), který patří kanálu ``elite``: celý, je-li zdroj elita."""
    size = len(is_elite)
    shares: FloatArray = np.broadcast_to(np.where(is_elite, 1.0, 0.0), (size, size)).copy()
    return shares


def trade_shares(size: int, rows: IntArray, columns: IntArray, values: FloatArray, elite: FloatArray) -> FloatArray:
    """Podíl vazby, který přinesla obchodní cesta, mimo vazby kanálu elity.

    Buňky ``(rows[k], columns[k])`` dostanou ``values[k]`` (při opakování
    vyhrává pozdější); výsledek se krát ``1 − elite``.
    """
    trade = np.zeros((size, size))
    trade[rows, columns] = values
    result: FloatArray = trade * (1.0 - elite)
    return result


def neighbor_fraction(shares: Sequence[FloatArray]) -> FloatArray:
    """Podíl vazby, který patří obecnému kontaktu: to, co nepatří elitě ani obchodu."""
    total: FloatArray | int = 0
    for share in shares:
        total = total + share
    result: FloatArray = 1.0 - total
    return result


def internal_blocks(
    mixing: FloatArray, members: Sequence[IntArray], foreign: BoolArray | None
) -> list[FloatArray]:
    """Bloky matice po komponentách pro vazby uvnitř jazyka (vazby mezi jazyky vynulované, je-li ``foreign``)."""
    return [
        mixing[np.ix_(group, group)] if foreign is None
        else np.where(foreign[np.ix_(group, group)], 0.0, mixing[np.ix_(group, group)])
        for group in members
    ]


def cross_blocks(
    mixing: FloatArray, members: Sequence[IntArray], foreign: BoolArray, fraction: FloatArray | None
) -> list[FloatArray]:
    """Bloky matice po komponentách jen pro vazby mezi jazyky, krát podíl kanálu (``None`` = celé)."""
    return [
        np.where(foreign[np.ix_(group, group)],
                 mixing[np.ix_(group, group)] if fraction is None
                 else mixing[np.ix_(group, group)] * fraction[np.ix_(group, group)], 0.0)
        for group in members
    ]


def cohort_scales(
    renewal: FloatArray, population: FloatArray, sigma: float, loss_threshold: float
) -> tuple[FloatArray, FloatArray]:
    """Rozsah driftu a spodní mez podílu varianty, kterou učící se kohorta ještě slyší.

    Kohorta je podíl obnovené populace (nejméně jeden mluvčí). Drift má rozptyl
    ``σ² / N``; varianta, na kterou nepřipadá ani půl mluvčího, zaniká.
    """
    cohort = np.maximum(1.0, renewal * population)
    return sigma / np.sqrt(cohort), np.maximum(loss_threshold, 0.5 / cohort)


def channel_weights(base: float, amount: FloatArray, correction: FloatArray | None = None) -> FloatArray:
    """Váha kanálu učící se skupiny: ``base × amount`` (u interference ``× (1 − škola × oprava)``).

    ``amount`` je podíl skupiny (L2 mluvčí, gramotnost, školní docházka,
    zbožnost); ``correction`` je u interference ``school_correction × schooling``.
    """
    weights: FloatArray = base * amount if correction is None else base * amount * (1.0 - correction)
    return weights


# --- faktory proměnných: sloupce vlastností -> faktor kanálu -----------------------


def _by_kind(base: Sequence[float], kinds: IntArray) -> FloatArray:
    return np.array(base, dtype=np.float64)[kinds]


def _scaled(factor: FloatArray, weight: FloatArray, lexical: BoolArray) -> FloatArray:
    """U slov krát váha domény, je-li různá od 1 (jako ``if weight != 1.0: factor *= weight``)."""
    return np.where(lexical & (weight != 1.0), factor * weight, factor)


def borrowing_factors(
    kinds: IntArray, base: Sequence[float], transfer: FloatArray, weight: FloatArray
) -> FloatArray:
    """Filtr výpůjček kanálu pro každou proměnnou bloku.

    ``kinds`` jsou kódy druhů (``KINDS``), ``base`` základ podle druhu
    (``kind_table(contact.BORROWING)``), ``transfer`` váha pojmu při přenosu
    slova z cizího kódu (``contact.transfer``) a ``weight`` váha domény pojmu
    v kanálu; obojí jen u slov (jinde se nepoužije).
    """
    lexical = kinds == LEXICAL
    factor = _by_kind(base, kinds)
    factor = np.where(lexical, factor * transfer, factor)
    return _scaled(factor, weight, lexical)


def interference_factors(kinds: IntArray, base: Sequence[float]) -> FloatArray:
    """Filtr interference při osvojování druhého jazyka (``base`` = ``kind_table(contact.INTERFERENCE)``)."""
    return _by_kind(base, kinds)


def reading_factors(
    kinds: IntArray, base: Sequence[float], frequency: FloatArray, resistance: float, weight: FloatArray
) -> FloatArray:
    """Filtr čtení: učená slova, častá šetří podle ``resistance`` a váhy domény ``learned``."""
    lexical = kinds == LEXICAL
    factor = _by_kind(base, kinds)
    factor = np.where(lexical, factor * (1.0 - resistance * frequency), factor)
    return _scaled(factor, weight, lexical)


def school_factors(kinds: IntArray, base: Sequence[float], weight: FloatArray) -> FloatArray:
    """Filtr školy: všechna slova, formy a konstrukce, procesy z desetiny."""
    return _scaled(_by_kind(base, kinds), weight, kinds == LEXICAL)


def liturgy_factors(kinds: IntArray, frequency: FloatArray, weight: FloatArray) -> FloatArray:
    """Filtr liturgie: jen slova, vzácná a podle váhy domény ``religion``."""
    lexical = kinds == LEXICAL
    factor = 1.0 - frequency
    factor = np.where(weight == 1.0, factor, factor * weight)
    return np.where(lexical, factor, 0.0)


# --- přenos bloku ------------------------------------------------------------------


def normalized(array: FloatArray, fallback: FloatArray) -> FloatArray:
    """Podíly slotů (osa −1) dělené součtem; řádek s nulovým součtem dá ``fallback`` (Rust, jinak Python)."""
    kernel = native.kernel("normalized") if array.ndim == 3 and array.shape[-1] > 0 else None
    if kernel is None:
        return normalized_python(array, fallback)
    result: FloatArray = kernel(np.ascontiguousarray(array, dtype=np.float64),
                                np.ascontiguousarray(fallback, dtype=np.float64))
    return result


def normalized_python(array: FloatArray, fallback: FloatArray) -> FloatArray:
    """Podíly slotů (osa −1) dělené součtem; řádek s nulovým součtem dá ``fallback``.

    Součet seřazených hodnot nezávisí na tom, ve kterých slotech varianty
    leží. Pořadí slotů ovlivňují i inovace v nepropojených skupinách, a bez
    toho by tak přes poslední bity zaokrouhlení měnily výsledek jinde.
    Součet dvou čísel je komutativní i v plovoucí čárce, řadit stačí od tří.
    Sčítání provádíme striktně sekvenčně zleva doprava po seřazených slotech:
    vestavěný np.sum() používá pro různé délky (např. 4 vs. 8) odlišné
    párové/SIMD redukce. V IEEE-754 platí +0.0 + x == x pro x >= 0, takže
    sekvenční součet zleva doprava zajistí bitovou shodu bez ohledu na to,
    kolika úvodními nulami je řádek doplněn v blocích různé kapacity.
    """
    ordered = array if array.shape[-1] <= 2 else np.sort(array, axis=-1)
    totals = ordered[..., :1] + 0.0
    for slot in range(1, ordered.shape[-1]):
        totals = totals + ordered[..., slot : slot + 1]
    result: FloatArray = np.where(totals > 0, array / np.where(totals > 0, totals, 1.0), fallback)
    return result


def _by_rank(matrix: FloatArray) -> list[tuple[IntArray, IntArray, FloatArray]]:
    """Nenulové buňky matice po pořadí ve svém řádku: ``(cíle, zdroje, váhy)`` pro k-tou nenulovou buňku řádků.

    Řádek má buňky seřazené podle zdroje vzestupně (tak je vrací ``nonzero``);
    k-tý prvek seznamu obsahuje k-tou buňku každého řádku, který jich má víc než
    k. Cíle jsou v prvku navzájem různé, takže se přičítá bez kolizí.
    """
    targets, sources = np.nonzero(matrix)
    if not len(targets):
        return []
    counts = np.bincount(targets, minlength=len(matrix))
    rank = np.arange(len(targets)) - (np.cumsum(counts) - counts)[targets]
    order = np.argsort(rank, kind="stable")
    bounds = np.cumsum(np.bincount(rank))
    found = []
    first = 0
    for last in bounds:
        chosen = order[first:last]
        found.append((targets[chosen], sources[chosen], matrix[targets[chosen], sources[chosen]]))
        first = int(last)
    return found


def _sequential(matrix: FloatArray, part: FloatArray) -> FloatArray:
    """Součin ``matice × part`` (``part`` má skupiny na ose 1) sčítaný postupně přes zdroje, viz :func:`mix`."""
    result = np.zeros_like(part)
    shape = (1, -1) + (1,) * (part.ndim - 2)
    for targets, sources, weights in _by_rank(matrix):
        result[:, targets] += weights.reshape(shape) * part[:, sources]
    return result


def mix(
    values: FloatArray,
    members: Sequence[IntArray],
    blocks: Sequence[FloatArray],
    alone: IntArray | None = None,
    alone_weight: FloatArray | None = None,
) -> FloatArray:
    """Vážený vstup od sousedů: ``values`` má skupiny na ose 1.

    Každá skupina dostane součet ``váha × podíl`` přes své zdroje, sčítaný
    postupně podle vzestupného čísla zdroje (viz začátek modulu); nulové váhy se
    přeskočí. Výsledek tak nezávisí na tvaru matice ani na tom, zda je svět
    rozdělený na komponenty: ``blocks[i]`` jsou bloky pro skupiny ``members[i]``
    a přidání nepropojených skupin nemění poslední bity. Osamocené skupiny
    (učí se jen samy od sebe, ``alone`` s váhou ``alone_weight``) se vyřídí
    najednou; vazby mezi jazyky je nemají, proto se tam ``alone`` nedává.
    """
    result = np.zeros_like(values)
    if alone is not None and len(alone):
        assert alone_weight is not None
        shape = (1, -1) + (1,) * (values.ndim - 2)
        result[:, alone] = alone_weight.reshape(shape) * values[:, alone]
    for group, matrix in zip(members, blocks):
        result[:, group] = _sequential(matrix, values[:, group])
    return result


def hear(
    current: FloatArray,
    present: BoolArray,
    members: Sequence[IntArray],
    blocks: Sequence[FloatArray],
    alone: IntArray,
    alone_weight: FloatArray,
    flows: Sequence[tuple[FloatArray, Sequence[FloatArray]]],
    channels: Sequence[tuple[FloatArray, IntArray, IntArray, FloatArray]],
) -> FloatArray:
    """Co skupiny slyší (viz :func:`hear_python`); v Rustu, když je k dispozici."""
    kernel = native.kernel("hear")
    if kernel is None:
        return hear_python(current, present, members, blocks, alone, alone_weight, flows, channels)
    floats, ints = np.float64, np.int64
    result: FloatArray = kernel(
        np.ascontiguousarray(current, dtype=floats), np.ascontiguousarray(present, dtype=np.bool_),
        [np.ascontiguousarray(group, dtype=ints) for group in members],
        [np.ascontiguousarray(block, dtype=floats) for block in blocks],
        np.ascontiguousarray(alone, dtype=ints), np.ascontiguousarray(alone_weight, dtype=floats),
        [(np.ascontiguousarray(factor, dtype=floats), [np.ascontiguousarray(cross, dtype=floats) for cross in crossing])
         for factor, crossing in flows],
        [(np.ascontiguousarray(factor, dtype=floats), np.ascontiguousarray(learners, dtype=ints),
          np.ascontiguousarray(sources, dtype=ints), np.ascontiguousarray(weights, dtype=floats))
         for factor, learners, sources, weights in channels],
        native.threads(),
    )
    return result


def hear_python(
    current: FloatArray,
    present: BoolArray,
    members: Sequence[IntArray],
    blocks: Sequence[FloatArray],
    alone: IntArray,
    alone_weight: FloatArray,
    flows: Sequence[tuple[FloatArray, Sequence[FloatArray]]],
    channels: Sequence[tuple[FloatArray, IntArray, IntArray, FloatArray]],
) -> FloatArray:
    """Co skupiny slyší: podíly variant od sousedů, jiných jazyků a z kanálů.

    ``current`` (proměnné × skupiny × sloty) a ``present`` (proměnné × skupiny)
    jsou stav bloku. ``flows`` jsou vazby mezi jazyky po kanálech:
    ``(faktor proměnných, bloky matice po komponentách)``; faktor je filtr
    přenositelnosti kanálu (``borrowing_factors``). ``channels`` jsou vstupy
    mimo vazby sítě v pořadí interference, čtení, škola a liturgie:
    ``(faktor proměnných, učící se skupiny, zdroje, váhy)``. Skupiny bez této
    proměnné se z míšení vyřadí a zbytek vstupu se převáží.
    """
    present_weight = present.astype(np.float64)
    heard = mix(current, members, blocks, alone, alone_weight)
    weight = mix(present_weight, members, blocks, alone, alone_weight)
    for factor, cross in flows:
        # Vazby mezi jazyky: jen tolik, kolik filtr přenositelnosti propustí.
        heard = heard + factor[:, None, None] * mix(current, members, cross)
        weight = weight + factor[:, None] * mix(present_weight, members, cross)
    heard = np.where(weight[:, :, None] > 0, heard / np.where(weight > 0, weight, 1.0)[:, :, None], 0)
    for factor, learners, sources, weights in channels:
        # Váha domény nad 1 smí podíl zvýšit nejvýš na celý vstup.
        share = np.minimum(factor[:, None] * weights[None, :], 1.0)
        share = np.where(present[:, sources], share, 0.0)[:, :, None]
        heard[:, learners] = (1.0 - share) * heard[:, learners] + share * current[:, sources]
    return heard


def settle(
    current: FloatArray,
    previous: FloatArray,
    present: BoolArray,
    heard: FloatArray,
    fitness: FloatArray,
    slot_keys: KeyArray,
    row_keys: KeyArray,
    drift_scale: FloatArray,
    renewal: FloatArray,
    loss_floor: FloatArray,
    selection: float,
    kappa: float,
    adult_rate: float,
    establish_threshold: float,
) -> tuple[FloatArray, FloatArray]:
    """Nové frekvence a trendová základna bloku (viz :func:`settle_python`); v Rustu, když knihovna sedí."""
    kernel = native.kernel("settle") if native.libm_matches() else None
    if kernel is None:
        return settle_python(current, previous, present, heard, fitness, slot_keys, row_keys, drift_scale,
                             renewal, loss_floor, selection, kappa, adult_rate, establish_threshold)
    floats = np.float64
    result: tuple[FloatArray, FloatArray] = kernel(
        *(np.ascontiguousarray(array, dtype=floats) for array in (current, previous)),
        np.ascontiguousarray(present, dtype=np.bool_),
        *(np.ascontiguousarray(array, dtype=floats) for array in (heard, fitness)),
        np.ascontiguousarray(slot_keys, dtype=np.uint64), np.ascontiguousarray(row_keys, dtype=np.uint64),
        *(np.ascontiguousarray(array, dtype=floats) for array in (drift_scale, renewal, loss_floor)),
        selection, kappa, adult_rate, establish_threshold, native.threads(),
    )
    return result


def settle_python(
    current: FloatArray,
    previous: FloatArray,
    present: BoolArray,
    heard: FloatArray,
    fitness: FloatArray,
    slot_keys: KeyArray,
    row_keys: KeyArray,
    drift_scale: FloatArray,
    renewal: FloatArray,
    loss_floor: FloatArray,
    selection: float,
    kappa: float,
    adult_rate: float,
    establish_threshold: float,
) -> tuple[FloatArray, FloatArray]:
    """Nové frekvence a trendová základna bloku ze slyšeného a tlaků.

    Výběr váží slyšené podíly ``exp(selection × fitness)``; trend je
    ``kappa × (current − previous)``; Wright–Fisherův drift má rozptyl
    ``p(1 − p) / N`` učící se kohorty (jen tam, kde soutěží varianty; šum závisí
    na ``row_keys`` skupiny a ``slot_keys`` varianty); děti se učí z výsledku,
    dospělí jen přibližují ``adult_rate``; varianta pod ``loss_floor``
    zaniká a varianta nad ``establish_threshold`` se ustálí (sama zbude).
    Vrací ``(updated, baseline)``: nové frekvence a základnu trendu příštího kroku.
    """
    selected = normalized_python(heard * np.exp(selection * fitness), heard)
    trend = kappa * (current - previous)
    # Wright–Fisherův drift: rozptyl p(1 − p) / N učící se kohorty. Varianta,
    # kterou kohorta vůbec neslyší, nemůže driftem vzniknout. Šum se počítá
    # jen tam, kde opravdu soutěží varianty; jinde je nulový.
    spread = selected * (1.0 - selected)
    drift = np.zeros_like(selected)
    rows, columns, cells = np.nonzero(spread > 0)
    if len(rows):
        noise = hash_normal(row_keys[columns], slot_keys[rows, cells], pairwise=True)
        drift[rows, columns, cells] = noise * drift_scale[columns] * np.sqrt(spread[rows, columns, cells])
    children = normalized_python(np.clip(selected + trend + drift, 0.0, None), selected)
    adults = current + adult_rate * (heard - current)
    renewed = renewal[None, :, None]
    updated = (1.0 - renewed) * adults + renewed * children

    updated[updated < loss_floor[None, :, None]] = 0.0
    updated = normalized_python(updated, current)
    leaders = updated.argmax(axis=2)
    top = np.take_along_axis(updated, leaders[:, :, None], axis=2)[:, :, 0]
    established = (top >= establish_threshold) & (top < 1.0)
    if established.any():
        one_hot = np.zeros_like(updated)
        np.put_along_axis(one_hot, leaders[:, :, None], 1.0, axis=2)
        updated = np.where(established[:, :, None], one_hot, updated)
    if not present.all():
        updated = np.where(present[:, :, None], updated, 0.0)
    baseline = np.where(updated > 0, previous + renewed * (current - previous), 0.0)
    # Skupina s jedinou variantou nemá trend. Bez toho by základna závisela
    # na tom, zda proměnná mezitím ležela v repertoáru, nebo ve skladu, a to
    # mohou ovlivnit i inovace v nepropojené části světa.
    single = (updated > 0).sum(axis=2, keepdims=True) == 1
    baseline = np.where(single, updated, baseline)
    return updated, baseline
