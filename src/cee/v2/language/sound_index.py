"""Prostředí hlásek a opory zvukových změn jako čísla a pole (krok B5, Python reference).

Dřív držel stav ``ContextIndex`` (``Counter`` pětic) a ``SoundSupportIndex``
(opory kandidátů, místa rodin jako řetězce) a oba se dorovnávaly po jednotlivých
slovech podle deníků řetězců. Tady je totéž v plochých polích podle čísel
z registru; Rust (``cee_core.SoundIndex``, ``rust/cee_core/src/index.rs``) je
přepisuje 1:1 a tato třída je jeho fallback (``CEE_NATIVE=0``) a reference
testu Rust proti Pythonu.

**Stav jednoho kódu** (řádek ``Slot``, klíč je ``FormStore.token``):

- ``counted_form`` / ``counted_rule``: pro každý morfém (číslo z registru) číslo
  tvaru v bance, který index započítal, a pravidlo přízvuku při započtení
  (−2 = nezapočítáno). Prostředí slova jsou čistá funkce (tvar, pravidlo), takže
  z těchto dvou čísel jde příspěvek vždy znovu vyrobit a odečíst;
- ``counts``: kolikrát se které prostředí (číslo ze společné tabulky
  ``ContextTable``) ve slovní zásobě vyskytuje;
- ``occurrences``: výskyty hlásek (inventář = hlásky s aspoň jedním výskytem);
- ``supports`` a ``effective``: opory kandidátů sady pro daný inventář;
- ``families``: pro každou rodinu místa (pořadí v rodině), míry a jejich součet.

**Bez deníků.** Změny se hledají hustým porovnáním dvou polí podle čísla
morfému (tvary kódu, příznaky slovní zásoby) s tím, co je započítáno. Index tak
nezávisí na deníku, který by kopie světa mohla rozejít. Výchozí tvar morfému, který
kód nepřepsal, se do banky tvarů světa nezařazuje (číslo ``PRIVATE_BASE`` + číslo
morfému, obsah čte index z morfému světa): banka tak nenese tvary, které model
nepoužívá, a čísla tvarů v ní zůstávají v pořadí skutečného užití.
Po změně pravidla přízvuku se prostředí nepřepočítají, dokud se tvar slova
nezmění (tak se to chovalo vždy); ``counted_rule`` drží, jak je které slovo
započítáno, ať se dá správně odečíst.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np
import numpy.typing as npt

from cee.v2 import native

if TYPE_CHECKING:
    from cee.v2.language.segments import SegmentTable
    from cee.v2.world import Code, World

#: V poli ``counted_form``: morfém není započítán.
UNCOUNTED = -2
#: Číslo tvaru od tohoto čísla výš je výchozí tvar morfému mimo banku: ``PRIVATE_BASE`` plus číslo morfému.
#: Výchozí tvary, které kód nepřepsal, drží index ve vlastní aréně (obsah čte z morfému světa), aby se
#: do banky tvarů světa nezařazoval tvar, který model nepoužívá.
PRIVATE_BASE = 1 << 30
#: Opora, od které se kandidát nabízí, a opora plné šance (viz ``changes.sound``).
MIN_SUPPORT = 2
FULL_SUPPORT = 8

#: Čísla pravidel přízvuku, jak je zná Rust (``cee.v2.native.RULES``).
RULES = ("initial", "second", "antepenult", "penult", "final")


class Catalog(Protocol):
    """Sady kandidátů zvukových změn pro inventář (vyrábí je ``changes.sound``)."""

    #: Míra jedné rodiny na jednotku opory (``SOUND_INNOVATIONS_PER_GENERATION · prior / součet priorů``).
    scales: list[float]

    def candidates(self, table: SegmentTable, inventory: tuple[int, ...]) -> Any:
        """Sada s ``family_ends`` (konce rodin v řádcích kandidátů) a ``eval_supports_python``."""


class ContextTable:
    """Prostředí (předchozí, hláska, další, přízvuk, druhá další) jako čísla, společná všem kódům.

    Prostředí dostane číslo při prvním výskytu; čísla jen určují místo v poli.
    ``of_form`` vrací čísla prostředí všech hlásek tvaru (čistá funkce tvaru a
    pravidla přízvuku, proto zapamatovaná).
    """

    def __init__(self) -> None:
        self._ids: dict[tuple[int, int, int, bool, int], int] = {}
        self.size = 0
        capacity = 1024
        self.previous = np.empty(capacity, dtype=np.int32)
        self.segment = np.empty(capacity, dtype=np.int32)
        self.following = np.empty(capacity, dtype=np.int32)
        self.stressed = np.empty(capacity, dtype=bool)
        self.following2 = np.empty(capacity, dtype=np.int32)
        self._forms: dict[tuple[int, int], npt.NDArray[np.int32]] = {}

    def _intern(self, key: tuple[int, int, int, bool, int]) -> int:
        found = self._ids.get(key)
        if found is None:
            found = self._ids[key] = self.size
            if found >= len(self.segment):
                grow = len(self.segment)
                self.previous = np.concatenate([self.previous, np.empty(grow, dtype=np.int32)])
                self.segment = np.concatenate([self.segment, np.empty(grow, dtype=np.int32)])
                self.following = np.concatenate([self.following, np.empty(grow, dtype=np.int32)])
                self.stressed = np.concatenate([self.stressed, np.empty(grow, dtype=bool)])
                self.following2 = np.concatenate([self.following2, np.empty(grow, dtype=np.int32)])
            self.previous[found], self.segment[found], self.following[found] = key[0], key[1], key[2]
            self.stressed[found], self.following2[found] = key[3], key[4]
            self.size += 1
        return found

    def of_form(
        self, form_id: int, rule: int, forms: list[tuple[int, ...]], table: SegmentTable,
        private: Callable[[int], tuple[int, ...]] | None = None,
    ) -> npt.NDArray[np.int32]:
        found = self._forms.get((form_id, rule))
        if found is None:
            from cee.v2.changes.sound import form_contexts

            form = forms[form_id] if form_id < PRIVATE_BASE else private(form_id - PRIVATE_BASE)  # type: ignore[misc]
            found = np.array([self._intern(key) for key in form_contexts(form, table, RULES[rule])], dtype=np.int32)
            self._forms[(form_id, rule)] = found
        return found


class Family:
    """Místa jedné rodiny u jednoho kódu: pořadí v rodině, míry a jejich součet."""

    __slots__ = ("sites", "rates", "total")

    def __init__(self, sites: npt.NDArray[np.int64], rates: npt.NDArray[np.float64], total: float) -> None:
        self.sites, self.rates, self.total = sites, rates, total


class Slot:
    """Stav indexu jednoho kódu."""

    def __init__(self) -> None:
        self.counted_form = np.zeros(0, dtype=np.int32)
        self.counted_rule = np.zeros(0, dtype=np.int8)
        self.counts = np.zeros(0, dtype=np.int64)
        self.occurrences: dict[int, int] = {}
        self.inventory: tuple[int, ...] = ()
        self.supports: npt.NDArray[np.int64] | None = None
        self.effective: npt.NDArray[np.int64] | None = None
        self.families: list[Family | None] = []
        #: Co se naposledy dorovnalo (verze stavu kódu, délka deníku tvarů, deníku slovní zásoby, tabulka).
        self.key: tuple[int, ...] | None = None


def _borrow(buffer: Any, dtype: Any, size: int, fill: int) -> npt.NDArray[Any]:
    """Kopie prvních ``size`` hodnot pole (``array.array``, ``bytearray``), doplněná ``fill``."""
    out = np.full(size, fill, dtype=dtype)
    view = np.frombuffer(buffer, dtype=dtype)
    count = min(size, len(view))
    out[:count] = view[:count]
    del view  # uvolní zpřístupnění pole, ať smí Python pole zase zvětšovat
    return out


class SoundIndex:
    """Prostředí a opory zvukových změn pro všechny kódy světa (reference v Pythonu)."""

    native = False

    def __init__(self) -> None:
        self.contexts = ContextTable()
        self.slots: dict[int, Slot] = {}

    # --- dorovnání -----------------------------------------------------------

    def _effective(self, world: World, code: Code, size: int) -> npt.NDArray[np.int32]:
        """Číslo tvaru každého morfému, který kód užívá; ostatní ``UNCOUNTED``."""
        state, store = code.phonology, code.forms
        flags = state.vocabulary.flags
        in_vocabulary = np.frombuffer(flags, dtype=np.uint8)[: len(flags)] != 0
        padded = np.zeros(size, dtype=bool)
        padded[: len(in_vocabulary)] = in_vocabulary
        forms = _borrow(store.raw()[0], np.int32, size, -1)
        # Výchozí tvar (kód morfém nepřepsal) drží index mimo banku: číslo je ``PRIVATE_BASE`` + číslo morfému.
        effective = np.where(forms >= 0, forms, PRIVATE_BASE + np.arange(size, dtype=np.int32)).astype(np.int32)
        effective[~padded] = UNCOUNTED
        return effective

    def sync(self, world: World, codes: list[Code], catalog: Catalog, force: bool = False) -> None:
        """Dorovná prostředí a opory kódů na aktuální stav (kódy bez hlásek se přeskočí)."""
        table = world.table
        assert table is not None
        for code in codes:
            state, store = code.phonology, code.forms
            slot = self.slots.get(store.token)
            if slot is None:
                slot = self.slots[store.token] = Slot()
            key = (state.version, len(store.log), len(state.vocabulary_log), id(table), len(state.vocabulary))
            if not force and slot.key == key:
                continue
            slot.key = key
            self._sync_code(world, code, slot, catalog)

    def _sync_code(self, world: World, code: Code, slot: Slot, catalog: Catalog) -> None:
        table = world.table
        assert table is not None
        bank = world.form_bank()
        size = max(len(code.phonology.vocabulary.flags), len(slot.counted_form))
        effective = self._effective(world, code, size)
        if len(slot.counted_form) < size:
            grown = size - len(slot.counted_form)
            slot.counted_form = np.concatenate([slot.counted_form, np.full(grown, UNCOUNTED, dtype=np.int32)])
            slot.counted_rule = np.concatenate([slot.counted_rule, np.zeros(grown, dtype=np.int8)])
        rule = RULES.index(code.stress_rule)
        changed = np.nonzero(effective != slot.counted_form)[0]
        contexts = self.contexts
        names = world.registry.morphemes.names

        def private(number: int) -> tuple[int, ...]:
            return world.morphemes[names[number]].form

        taken: list[npt.NDArray[np.int32]] = []
        given: list[npt.NDArray[np.int32]] = []
        for number in changed.tolist():
            old = int(slot.counted_form[number])
            if old >= 0:
                taken.append(contexts.of_form(old, int(slot.counted_rule[number]), bank.forms, table, private))
            new = int(effective[number])
            if new >= 0:
                given.append(contexts.of_form(new, rule, bank.forms, table, private))
                slot.counted_rule[number] = rule
            slot.counted_form[number] = new
        net = np.zeros(0, dtype=np.int32)
        touched = np.zeros(0, dtype=np.int64)
        if taken or given:
            both = np.concatenate([*given, *taken]).astype(np.int64)
            sign = np.concatenate(
                [np.ones(sum(map(len, given)), dtype=np.int64), -np.ones(sum(map(len, taken)), dtype=np.int64)]
            )
            unique, inverse = np.unique(both, return_inverse=True)
            sums = np.zeros(len(unique), dtype=np.int64)
            np.add.at(sums, inverse, sign)
            keep = sums != 0
            touched, net = unique[keep], sums[keep]
            if len(slot.counts) < contexts.size:
                slot.counts = np.concatenate(
                    [slot.counts, np.zeros(max(contexts.size, 2 * len(slot.counts)) - len(slot.counts), dtype=np.int64)]
                )
            slot.counts[touched] += net
            for segment, diff in zip(contexts.segment[touched].tolist(), net.tolist()):
                slot.occurrences[segment] = slot.occurrences.get(segment, 0) + diff
        inventory = tuple(sorted(segment for segment, count in slot.occurrences.items() if count > 0))
        if not inventory:
            slot.inventory = ()
            slot.supports = slot.effective = None
            slot.families = []
            return
        families = len(catalog.scales)
        full = inventory != slot.inventory or slot.supports is None
        combined = catalog.candidates(table, inventory)
        if full:
            present = np.nonzero(slot.counts)[0]
            slot.supports = self._supports(combined, present, slot.counts[present], table)
            slot.inventory = inventory
            slot.effective = None
            slot.families = [None] * families
        elif len(touched):
            assert slot.supports is not None
            slot.supports = slot.supports + self._supports(combined, touched, net, table)
        else:
            return
        supports = slot.supports
        assert supports is not None
        effective_supports = np.where(supports < MIN_SUPPORT, np.int64(0), np.minimum(np.int64(FULL_SUPPORT), supports))
        ends = combined.family_ends
        begin = 0
        for family in range(families):
            end = int(ends[family])
            if (slot.effective is not None and slot.families[family] is not None
                    and np.array_equal(effective_supports[begin:end], slot.effective[begin:end])):
                begin = end
                continue
            slot.families[family] = self._family(supports[begin:end], catalog.scales[family])
            begin = end
        slot.effective = effective_supports

    def _supports(
        self, combined: Any, ids: npt.NDArray[np.int64], counts: npt.NDArray[np.int64], table: SegmentTable
    ) -> npt.NDArray[np.int64]:
        c = self.contexts
        result: npt.NDArray[np.int64] = combined.eval_supports_python(
            c.previous[ids].astype(np.intp), c.segment[ids].astype(np.intp), c.following[ids].astype(np.intp),
            c.stressed[ids], c.following2[ids].astype(np.intp), counts.astype(np.int64), table,
        )
        return result

    @staticmethod
    def _family(supports: npt.NDArray[np.int64], scale: float) -> Family:
        sites = np.nonzero(supports >= MIN_SUPPORT)[0].astype(np.int64)
        if len(sites) == 0:
            return Family(sites, np.zeros(0, dtype=np.float64), 0.0)
        share = np.minimum(1.0, supports[sites].astype(np.float64) / FULL_SUPPORT)
        rates = (scale * share) / len(sites)
        return Family(sites, rates, float(np.sum(rates)))

    # --- čtení ----------------------------------------------------------------

    def _slot(self, code: Code) -> Slot | None:
        return self.slots.get(code.forms.token)

    def inventory(self, code: Code) -> tuple[int, ...]:
        """Hlásky, které kód ve slovní zásobě užívá (seřazené)."""
        slot = self._slot(code)
        return () if slot is None else tuple(sorted(s for s, count in slot.occurrences.items() if count > 0))

    def totals(self, codes: list[Code], families: int) -> npt.NDArray[np.float64]:
        """Součty měr rodin (kód × rodina); 0 tam, kde kód nemá místa."""
        out = np.zeros((len(codes), families), dtype=np.float64)
        for row, code in enumerate(codes):
            slot = self._slot(code)
            if slot is not None:
                for family, state in enumerate(slot.families):
                    if state is not None:
                        out[row, family] = state.total
        return out

    def has_families(self, code: Code) -> bool:
        slot = self._slot(code)
        return slot is not None and bool(slot.families)

    def family(self, code: Code, family: int) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.float64], float]:
        """Místa (pořadí v rodině), jejich míry a součet měr."""
        slot = self._slot(code)
        assert slot is not None and slot.families[family] is not None
        state = slot.families[family]
        assert state is not None
        return state.sites, state.rates, state.total

    def supports(self, code: Code) -> npt.NDArray[np.int64]:
        slot = self._slot(code)
        assert slot is not None and slot.supports is not None
        return slot.supports

    def context_counts(self, code: Code, world: World | None = None) -> tuple[npt.NDArray[np.intp], ...]:
        """Počty prostředí: předchozí, hláska, další, přízvuk, druhá další a počet (jen nenulové)."""
        slot = self._slot(code)
        c = self.contexts
        if slot is None:
            empty = np.zeros(0, dtype=np.intp)
            return empty, empty, empty, empty.astype(bool), empty, empty
        ids = np.nonzero(slot.counts)[0]
        return (
            c.previous[ids].astype(np.intp), c.segment[ids].astype(np.intp), c.following[ids].astype(np.intp),
            c.stressed[ids], c.following2[ids].astype(np.intp), slot.counts[ids].astype(np.intp),
        )


_TONE_CODES: dict[int, npt.NDArray[np.int32]] = {}


def _tone_codes(table: SegmentTable) -> npt.NDArray[np.int32]:
    """Kód tónu každé hlásky (0 = bez tónu); čistá funkce tabulky, proto zapamatovaná."""
    found = _TONE_CODES.get(id(table))
    if found is None:
        found = np.zeros(len(table.ipa), dtype=np.int32)
        for segment in table._tone_base:  # type: ignore[attr-defined]
            found[segment] = table.tone_of(segment)
        _TONE_CODES[id(table)] = found
    return found


_CANONICAL: dict[int, npt.NDArray[np.int32]] = {}


def _canonical_ids(table: SegmentTable) -> npt.NDArray[np.int32]:
    """Hláska, kterou dá ``id_of(ipa[hláska])`` (−1 = zápis tabulka nerozebere); pamatované po tabulce.

    Výčtová třída jedné hlásky (``changes.sound._single``) se staví ze zápisu hlásky, takže u necelistvých
    zápisů (``cᶣ`` se čte jako ``cʷ``) je to jiná hláska; Rust tu shodu potřebuje znát.
    """
    found = _CANONICAL.get(id(table))
    if found is None:
        out = []
        for symbol in table.ipa:
            try:
                out.append(table.id_of(symbol))
            except ValueError:
                out.append(-1)
        found = _CANONICAL[id(table)] = np.array(out, dtype=np.int32)
    return found


class NativeSoundIndex:
    """Tentýž index v Rustu (``cee_core.SoundIndex``); rozhraní jako :class:`SoundIndex`.

    Stav je v Rustu. Python posílá jednou za tik pro všechny kódy dva pohledy na
    pole (tvary kódu, příznaky slovní zásoby) a doplní, co si Rust vyžádá: obsah
    výchozích tvarů (index je drží mimo banku tvarů světa). Sady kandidátů pro nový
    inventář si Rust staví sám z rysů tabulky hlásek (``rust/cee_core/src/candidates.rs``);
    Python mu tabulku pošle jednou (:meth:`_send_table`). Rust nelze zkopírovat
    ani uložit, proto se při kopii a uložení exportují jen započítané tvary a
    pravidla (``counted_form``, ``counted_rule``) a podle nich se stav obnoví.
    """

    native = True

    def __init__(self, handle: Any, scales: list[float]) -> None:
        self._handle = handle
        self._scales = list(scales)
        self._tokens: set[int] = set()
        #: Tabulka hlásek, jejíž snímek Rust dostal (nový Rust index ji dostane při prvním dorovnání).
        self._table_sent: SegmentTable | None = None
        #: Uložený stav, který se do Rustu vrátí při příštím dorovnání (banku mít po ruce).
        self._restore: dict[int, tuple[npt.NDArray[np.int32], npt.NDArray[np.int8]]] = {}

    def __getstate__(self) -> dict[str, Any]:
        saved = {token: self._handle.export(token) for token in self._tokens if token not in self._restore}
        saved.update(self._restore)
        return {"scales": self._scales, "saved": {t: (f.copy(), r.copy()) for t, (f, r) in saved.items()}}

    def __setstate__(self, state: dict[str, Any]) -> None:
        module = native._load()
        assert module is not None, "uložený svět čeká rozšíření cee_core"
        self._scales = state["scales"]
        self._handle = module.SoundIndex(self._scales)
        self._table_sent = None
        self._restore = state["saved"]
        self._tokens = set(self._restore)

    @staticmethod
    def _bank(world: World) -> Any:
        bank = world.form_bank()._native
        assert bank is not None
        return bank

    @property
    def handle(self) -> Any:
        """Index v Rustu (jeho dorovnání spolu s indexem míst dělá ``cee_core.innovation_totals``)."""
        return self._handle

    @property
    def family_count(self) -> int:
        return len(self._scales)

    def prepare(self, world: World, codes: list[Code]) -> tuple[list[int], list[int], list[Any], list[Any]]:
        """Vstupy dorovnání kódů (tokeny, pravidla přízvuku, příznaky slovní zásoby a tvary kódů bez kopie).

        Zároveň pošle Rustu tabulku hlásek, nebyla-li poslána, a vrátí do něj uložený stav (po obnově světa).
        """
        table = world.table
        assert table is not None
        bank = self._bank(world)
        self._send_table(table)
        for token, (forms, rules) in list(self._restore.items()):
            # Uložené číslo tvaru mimo banku se odvolává na výchozí tvar morfému: obsah doplní svět.
            self.supply(world, (np.unique(forms[forms >= PRIVATE_BASE]) - PRIVATE_BASE).tolist())
            self._handle.import_group(bank, token, forms, rules)
        self._restore.clear()
        tokens = [code.forms.token for code in codes]
        self._tokens.update(tokens)
        return (
            tokens, [RULES.index(code.stress_rule) for code in codes],
            [code.phonology.vocabulary.flags for code in codes], [code.forms.raw()[0] for code in codes],
        )

    def sync(self, world: World, codes: list[Code], catalog: Catalog, force: bool = False) -> None:
        bank = self._bank(world)
        tokens, rules, flags, forms = self.prepare(world, codes)
        for _ in range(64):
            missing, sets = self._handle.sync(bank, tokens, rules, flags, forms)
            assert not sets, "Rust si sady kandidátů staví sám"
            if not missing:
                return
            for _, numbers in missing:
                self.supply(world, numbers)
        raise RuntimeError("index prostředí se nepodařilo dorovnat")

    def _send_table(self, table: SegmentTable) -> None:
        """Pošle Rustu snímek tabulky hlásek (rysy, zápis, samohlásky, tóny a čísla hledaných symbolů)."""
        if self._table_sent is table:
            return
        from cee.v2.language.segments import TONES

        module = native._load()
        assert module is not None
        symbols = []
        for symbol in module.candidate_symbols():
            try:
                symbols.append(table.id_of(symbol))
            except ValueError:
                symbols.append(-1)
        self._handle.set_table(
            [*table.names, *table.detail_names], np.ascontiguousarray(table.vectors), list(table.ipa),
            np.ascontiguousarray(table.vowel_mask), _tone_codes(table), _canonical_ids(table), symbols, list(TONES),
        )
        self._table_sent = table

    def supply(self, world: World, numbers: list[int]) -> None:
        """Výchozí tvary morfémů (obsah hlásek) do arény indexu; do banky tvarů světa se nezařazují."""
        if numbers:
            names = world.registry.morphemes.names
            self._handle.set_defaults(numbers, [list(world.morphemes[names[number]].form) for number in numbers])

    def inventory(self, code: Code) -> tuple[int, ...]:
        return tuple(self._handle.inventory(code.forms.token))

    def totals(self, codes: list[Code], families: int) -> npt.NDArray[np.float64]:
        flat = self._handle.totals([code.forms.token for code in codes])
        return np.asarray(flat, dtype=np.float64).reshape(len(codes), families)

    def has_families(self, code: Code) -> bool:
        return bool(self._handle.has_families(code.forms.token))

    def family(self, code: Code, family: int) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.float64], float]:
        found = self._handle.family(code.forms.token, family)
        assert found is not None
        return found  # type: ignore[no-any-return]

    def supports(self, code: Code) -> npt.NDArray[np.int64]:
        return self._handle.supports(code.forms.token)  # type: ignore[no-any-return]

    def family_names(self, code: Code, family: int) -> list[str]:
        """ID proměnných míst rodiny v pořadí míst (sadu kandidátů drží Rust)."""
        found = self._handle.family_names(code.forms.token, family)
        assert found is not None
        return found  # type: ignore[no-any-return]

    def family_spec(self, code: Code, family: int, position: int) -> Any:
        """Popis kandidáta místa rodiny (pole procesu), z něhož Python postaví ``Process``."""
        found = self._handle.family_spec(code.forms.token, family, position)
        assert found is not None
        return found

    def family_supports(self, code: Code, family: int) -> list[int]:
        """Opory míst rodiny v pořadí míst."""
        found = self._handle.family_supports(code.forms.token, family)
        assert found is not None
        return found  # type: ignore[no-any-return]

    def context_counts(self, code: Code, world: World) -> tuple[npt.NDArray[np.intp], ...]:
        found = self._handle.context_counts(self._bank(world), code.forms.token)
        return tuple(np.asarray(column, dtype=np.intp if column.dtype != np.bool_ else bool) for column in found)
