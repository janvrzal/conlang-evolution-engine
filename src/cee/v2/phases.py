"""Fáze kroku jako čisté funkce nad poli (krok A5 přípravy na Rust).

Každá funkce tady dostane pole a čísla, vrátí pole a čísla a nesahá na svět,
kód ani deník. Třídy enginu (``Simulation``, ``Change``, ``morphology``,
``syntax``, ``prosody``) zůstávají tenkou fasádou: z objektů poskládají vstupní
pole, zavolají funkci odtud a výsledek zapíšou zpět ve stejném pořadí jako dřív.
Bitová shoda se tím nemění; Rust později přepíše právě tyto funkce.

Hranice mezi poli a objekty:

- **Na polích**: klíče a tempo inovací (``innovation_group_keys``,
  ``expected_counts``; losy počtu inovací dělá ``rng.hash_poisson``, také
  čistá funkce polí), míry a váhy míst (``uniform_rate``, ``rate_total``,
  ``site_weights``, ``category_loss_rates``), výběr místa z vah
  (``draw_site``), milníky,
  ustálení a zánik inovací v bloku živých proměnných (``change_events``),
  přechody přes práh a aktivace procesů v bloku před a po přenosu
  (``threshold_crossings``, ``activation_cells``, ``trace_cells``),
  rozhodnutí o analogiích, nových koncovkách a pravidlu přízvuku
  (``analogy_decisions``, ``grammar_ready``, ``ending_actions``,
  ``stress_updates``).
- **Na objektech zůstává**: sbírání vstupů ze světa (dominantní konstrukce,
  slovní zásoba, tvary v bance), návrh varianty (``Change.propose`` tvoří
  objekty ``Variant`` a zapisuje je do registrů), zápis tvarů a deníků a vše,
  co volá přenos nebo kontakt.

Pořadí výstupu je vždy pevné (řádkově po řádcích a skupinách, vzestupně) a je
součástí smlouvy: kdo funkci přepíše, musí ho zachovat.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from cee.v2.rng import Stream, stable_int

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]
IntArray = npt.NDArray[np.intp]
KeyArray = npt.NDArray[np.uint64]
#: Tři souřadnice buněk bloku (řádek = proměnná, sloupec = skupina, slot = varianta).
Cells = tuple[IntArray, IntArray, IntArray]

#: Rozhodnutí o živé analogii (``analogy_decisions``).
ANALOGY_WAIT = 0
ANALOGY_REMOVE = 1
ANALOGY_APPLY = 2

#: Co udělat s lexémem při zápisu nové koncovky (``ending_actions``).
ENDING_SKIP = 0
ENDING_KEPT = 1
ENDING_FROM_DONOR = 2
ENDING_FROM_CITATION = 3


# --- inovace: klíče, tempo a losy počtu ---------------------------------------


def innovation_group_keys(seed: int, tick: int, group_ids: Sequence[str], code_ids: Sequence[str]) -> KeyArray:
    """Klíč losu inovací pro každou dvojici (skupina, kód) v kroku.

    ``stable_int(seed, "innovation", tick, skupina, kód)`` (blake2b, 8 bajtů);
    klíč závisí jen na těchto částech, ne na ostatních skupinách.
    """
    return np.array(
        [stable_int(seed, "innovation", tick, group, code) for group, code in zip(group_ids, code_ids)],
        dtype=np.uint64,
    )


def expected_counts(
    rate_sums: FloatArray,
    renewals: FloatArray,
    frequencies: FloatArray,
    dt: float,
    generation: BoolArray,
    scales: FloatArray,
) -> FloatArray:
    """Očekávaný počet inovací pro každou dvojici (skupina, změna).

    ``rate_sums`` (skupiny × změny) je celková míra všech míst; nula tam, kde
    změna nemá místa nebo skupinu počítá jiný proces. Tempo je podíl obnovené
    populace (``renewals``) u změn podle generace (``generation``) a délka
    kroku ``dt`` u ostatních, vždy krát násobek četnosti skupiny
    (``frequencies``). ``scales`` jsou násobky ze ``Parameters.change_rates``
    (jedna pro změnu, 1.0 = beze změny).
    """
    tempos = np.where(generation[None, :], renewals[:, None], dt) * frequencies[:, None]
    return np.where(rate_sums > 0.0, rate_sums * tempos, 0.0) * scales[None, :]


# --- inovace: míry a váhy míst ------------------------------------------------


def uniform_rate(base_rate: float, counts: float | FloatArray, scales: float | FloatArray) -> float | FloatArray:
    """Celková míra míst se stejnou mírou: ``base_rate * počet * násobek`` (v tomto pořadí).

    Bere skalár i pole (po prvcích); pro skalár zůstává čistě pythonový výpočet.
    """
    return base_rate * counts * scales


def rate_total(rates: Sequence[float] | FloatArray) -> float:
    """Součet měr míst (``numpy.sum``, párový součet; Rust ho musí zopakovat)."""
    return float(np.sum(np.asarray(rates, dtype=np.float64)))


def normalize_rates(rates: FloatArray, total: float) -> FloatArray:
    """Váhy míst: míry dělené celkem."""
    result: FloatArray = rates / total
    return result


def site_weights(rates: Sequence[float] | FloatArray) -> tuple[float, FloatArray | None]:
    """Celek a normalizované váhy míst; bez vah (``None``), když je celek nekladný."""
    values = np.asarray(rates, dtype=np.float64)
    total = rate_total(values)
    if total <= 0.0:
        return total, None
    return total, normalize_rates(values, total)


def category_loss_rates(
    base_rate: float,
    present: BoolArray,
    free_periphrasis: BoolArray,
    bound: BoolArray,
    synthetic: BoolArray,
    weakness: FloatArray,
    l2_boost: float,
    l2_share: float,
) -> FloatArray:
    """Míry zániku kategorie na místech (funkce skupiny), ``Parameters``-řízené.

    Tlak k vypuštění výrazu je 1 u volného opisu; jinak 0, když výraz není
    vázaný; u vázaného je to slabost koncovky (jen u syntetického výrazu)
    plus ``l2_boost * l2_share``. Místo bez dominantní konstrukce
    (``present`` nepravda) má míru 0.
    """
    unreliable = np.where(synthetic, weakness, 0.0) + l2_boost * l2_share
    pressure = np.where(free_periphrasis, 1.0, np.where(bound, unreliable, 0.0))
    return np.where(present, base_rate * pressure, 0.0)


# --- inovace: výběr místa ------------------------------------------------------


def draw_site(state: int, count: int, cumulated: Sequence[float] | None) -> tuple[int, int]:
    """Výběr místa z proudu náhody ve stavu ``state``: (index, nový stav).

    Bez vah (``cumulated`` je ``None``) rovnoměrně z ``count`` míst
    (``Stream.integers``); s kumulativními součty vah (``rng.cumulative``)
    podle ``Stream.pick`` z jednoho ``random()``. Návrh varianty po výběru čerpá
    z téhož proudu dál, proto se vrací i nový stav.
    """
    stream = Stream.from_key(state)
    if cumulated is None:
        index = stream.integers(count)
    else:
        index = Stream.pick(cumulated, stream.random())
    return index, stream.state


# --- sledování inovací v bloku živých proměnných --------------------------------


def innovation_mask(slot_numbers: IntArray, change_column: npt.NDArray[np.integer]) -> BoolArray:
    """Sloty (řádky × sloty), jejichž varianta vznikla změnou (sloupec ``change`` tabulky variant).

    ``slot_numbers`` jsou čísla variant z registru, −1 = volný slot.
    """
    if not len(change_column):
        result: BoolArray = slot_numbers < -1
        return result
    result = (slot_numbers >= 0) & (change_column[slot_numbers] >= 0)
    return result


def change_events(
    before: FloatArray, after: FloatArray, innovation: BoolArray, levels: FloatArray
) -> tuple[tuple[IntArray, ...], tuple[IntArray, ...], tuple[IntArray, ...]]:
    """Milníky, ustálení a zánik inovací v bloku; ``before``/``after`` mají tvar řádky × skupiny × sloty.

    Vrací tři skupiny polí:

    - ``milestones``: (řádek, skupina, slot, od, do): inovace přešla hladiny
      ``levels[od:do]`` (vzestupně) v daném kroku;
    - ``established``: (řádek, skupina, slot): podíl dosáhl 1;
    - ``extinct``: (řádek, slot): varianta měla před krokem někde podíl a po něm
      už nikde.

    Všechny výčty jsou po řádcích, potom po skupinách a slotech vzestupně.
    """
    wide = innovation[:, None, :]
    reached_before = np.searchsorted(levels, before, side="right")
    reached_after = np.searchsorted(levels, after, side="right")
    rows, columns, slots = np.nonzero((reached_after > reached_before) & wide)
    milestones = (rows, columns, slots, reached_before[rows, columns, slots], reached_after[rows, columns, slots])
    established = np.nonzero((after == 1.0) & (before < 1.0) & wide)
    gone = (before > 0).any(axis=1) & ~(after > 0).any(axis=1) & innovation
    extinct = np.nonzero(gone)
    return milestones, established, extinct


def threshold_crossings(
    before: FloatArray, after: FloatArray, rows: BoolArray, level: float
) -> tuple[Cells, Cells]:
    """Buňky bloku, které v kroku přešly hladinu ``level`` (jen v řádcích ``rows``).

    První trojice jsou odchody (před ≥ hladina, po < hladina), druhá příchody
    (před < hladina, po ≥ hladina); obě po řádcích, skupinách a slotech vzestupně.
    """
    selected = rows[:, None, None]
    leave = np.nonzero((before >= level) & (after < level) & selected)
    enter = np.nonzero((before < level) & (after >= level) & selected)
    return leave, enter


def activation_cells(after: FloatArray, slots: IntArray, share: float) -> tuple[IntArray, IntArray]:
    """Skupiny, kde sledovaná varianta řádku dosáhla podílu ``share`` (aktivace procesu či analogie).

    ``slots[řádek]`` je slot sledované (změněné) varianty v řádku, −1 = řádek
    se nesleduje. Vrací dvojice (řádek, skupina) po řádcích a skupinách vzestupně.
    """
    rows = np.flatnonzero(slots >= 0)
    if not len(rows):
        return rows, rows
    hits = after[rows, :, slots[rows]] >= share
    which, columns = np.nonzero(hits)
    return rows[which], columns


def trace_cells(before: FloatArray, after: FloatArray) -> Cells:
    """Buňky, kde má varianta před krokem nebo po něm kladný podíl (po řádcích, skupinách, slotech)."""
    return np.nonzero((before > 0) | (after > 0))


# --- morfologie, syntax a prozódie v kroku --------------------------------------


def analogy_decisions(shares: FloatArray, threshold: float) -> npt.NDArray[np.int8]:
    """Co se stane s živou analogií podle podílu změněného tvaru ve skupině.

    ``ANALOGY_REMOVE`` (podíl nekladný: analogie zanikla), ``ANALOGY_WAIT``
    (pod prahem ``threshold``) nebo ``ANALOGY_APPLY`` (převážila, zapíše se do tvarů).
    """
    return np.where(
        shares <= 0.0, ANALOGY_REMOVE, np.where(shares < threshold, ANALOGY_WAIT, ANALOGY_APPLY)
    ).astype(np.int8)


def grammar_ready(
    shares: FloatArray, threshold: float, synthetic: BoolArray, has_exponent: BoolArray, applied: BoolArray
) -> BoolArray:
    """Které funkce mají novou syntetickou konstrukci k zapsání do tvarů slov.

    Dominantní konstrukce funkce musí mít podíl aspoň ``threshold``, být
    syntetická s koncovkou a nesmí být ve skupině už zapsaná.
    """
    ready: BoolArray = (shares >= threshold) & synthetic & has_exponent & ~applied
    return ready


def ending_actions(
    has_donor: bool,
    exists: BoolArray,
    donor_present: BoolArray,
    donor_matches: BoolArray,
    frequency: FloatArray,
    conserved: float,
) -> npt.NDArray[np.int8]:
    """Co se stane s lexémem při zápisu nové koncovky (pro každý kořen příslušné třídy slov).

    S dárcem (exaptace) se tvar převezme z dárcovské buňky, jen když v kódu je
    (``donor_present``) a nese tutéž koncovku (``donor_matches``), jinak
    ``ENDING_SKIP``. Bez dárce (gramatikalizace) si tvar ponechá už existující
    velmi častý lexém (``exists`` a ``frequency >= conserved``,
    ``ENDING_KEPT``); ostatní dostanou citační tvar + koncovku
    (``ENDING_FROM_CITATION``).
    """
    if has_donor:
        return np.where(donor_present & donor_matches, ENDING_FROM_DONOR, ENDING_SKIP).astype(np.int8)
    return np.where(exists & (frequency >= conserved), ENDING_KEPT, ENDING_FROM_CITATION).astype(np.int8)


def stress_updates(
    shares: FloatArray, dominant: npt.NDArray[np.integer], current: npt.NDArray[np.integer], threshold: float = 0.5
) -> BoolArray:
    """Skupiny, kde převládající hodnota prozodické proměnné (číslo pravidla či síly) mění vlastnost kódu.

    ``dominant`` je číslo převládající hodnoty (−1 = skupina proměnnou nemá),
    ``current`` číslo hodnoty, kterou kód právě má. Změna nastane, když
    převládající hodnota má podíl aspoň ``threshold`` a liší se od dnešní.
    """
    changed: BoolArray = (dominant >= 0) & (shares >= threshold) & (dominant != current)
    return changed
