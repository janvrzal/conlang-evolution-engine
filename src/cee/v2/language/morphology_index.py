"""Morfologické indexy kódu na číslech (krok B5b, Python reference).

Dřív držely členství tvarů slov (``WordMembershipIndex``), počty koncovek tříd
(``ExponentIndex``), kandidáty analogie (``MorphologyCandidateIndex``) a slabost
buněk (``WeaknessIndex``) čtyři indexy nad množinami a slovníky s řetězcovými klíči
a dorovnávaly se po slovech podle deníků řetězců. Tady je totéž jako čísla podle
registru světa; Rust (``cee_core.SiteIndex``, ``rust/cee_core/src/morphology_index.rs``)
je přepisuje 1:1 a tyto třídy jsou jeho fallback (``CEE_NATIVE=0``) a reference testu
Rust proti Pythonu.

**Stav jednoho kódu** (klíč je ``FormStore.token``) je ve sloupcích podle čísla
morfému (stejné sloupce jako ``MorphemeTable``: druh, třída, buňka, lexém, koncovka,
hranice):

- ``WordMembershipIndex``: členové (tvary slov ve slovní zásobě kódu) a kopie příznaků
  slovní zásoby, podle které se změny členství poznají;
- ``ExponentCounts``: pro (třídu, buňku) počty tvarů podle koncovky a pro koncovku počty
  tvarů podle podoby koncovky (konec tvaru od hranice), plus počty tvarů buňky a z nich
  splynulých s citačním tvarem (slabost);
- ``MorphologyCandidateIndex``: pro člena příznak „místo vyrovnání“ a produktivní
  koncovka, kterou by mohl převzít („místo rozšíření“).

**Bez deníků.** Příspěvek člena je čistá funkce jeho tvaru, tvaru kořene a popisu buňky.
Index proto porovnává syrová čísla úložiště tvarů kódu (tvar, hranice, koncovka) a tvaru
kořene s tím, co započítal; změní se jen příspěvky těch, kde se liší. Výchozí tvar morfému,
který kód nepřepsal, je v aréně indexu (``defaults``), kterou plní volající na požádání
(``needs``); do banky tvarů světa se tím nezařazuje žádný tvar, který model nepoužívá.
Remízy (produktivní koncovka, podoba koncovky) a pořadí míst rozhodují řetězce jako dřív.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cee.v2.world import Code, World

#: Kód druhu morfému „tvar slova“ (``MORPHEME_KINDS`` v ``cee.v2.tables``).
KIND_WORD = 2
#: Syrová hodnota v úložišti tvarů kódu: morfém nemá vlastní tvar.
RAW_NONE = -1
#: Dosud nezapočítáno (žádný skutečný stav se mu nerovná).
_FRESH = (-(2**31),) * 4

Form = tuple[int, ...]


def _at(values: Any, number: int, missing: int) -> int:
    return int(values[number]) if 0 <= number < len(values) else missing


def _extension(productive: int, ends: bool, exponent: int, merged: bool) -> int:
    """Rozšíření: produktivní koncovka buňky, když tvar nese jinou nebo splynul."""
    if productive < 0 or not ends:
        return -1
    return productive if (exponent != productive or merged) else -1


class WordMembershipIndex:
    """Členové (tvary slov ve slovní zásobě kódu) vzestupně podle čísla morfému."""

    def __init__(self) -> None:
        self.synced = False
        self.flags = b""
        self.members: list[int] = []

    def changes(
        self, flags: Any, kind: Any, word_class: Any, cell: Any
    ) -> tuple[list[int], list[int]] | None:
        """Přibyli a ubyli členové, nebo ``None``, když se příznaky nezměnily."""
        current = bytes(flags)
        if self.synced and current == self.flags:
            return None
        found = [
            number for number, flag in enumerate(current)
            if flag and _at(kind, number, -1) == KIND_WORD
            and _at(word_class, number, -1) >= 0 and _at(cell, number, -1) >= 0
        ]
        before, after = set(self.members), set(found)
        return sorted(after - before), sorted(before - after)

    def apply(self, flags: Any, fresh: list[int], removed: list[int]) -> None:
        gone = set(removed)
        self.members = sorted([number for number in self.members if number not in gone] + fresh)
        self.flags = bytes(flags)
        self.synced = True


class _Cell:
    """Statistika jedné (třídy, buňky)."""

    __slots__ = ("exponents", "total", "merged", "productive", "ends")

    def __init__(self) -> None:
        self.exponents: dict[int, int] = {}
        self.total = 0
        self.merged = 0
        #: Popisovač, se kterým jsou spočítaní kandidáti rozšíření.
        self.productive = -1
        self.ends = False


class _Contribution:
    __slots__ = ("exponent", "shape", "merged", "leveling", "extension")

    def __init__(self, exponent: int, shape: Form, merged: bool, leveling: bool, extension: int) -> None:
        self.exponent, self.shape, self.merged = exponent, shape, merged
        self.leveling, self.extension = leveling, extension


class ExponentCounts:
    """Počty koncovek tříd slov a podob koncovek jednoho kódu (a slabost buněk)."""

    def __init__(self) -> None:
        self.cells: dict[tuple[int, int], _Cell] = {}
        #: Koncovka → podoba koncovky → počet tvarů.
        self.shapes: dict[int, dict[Form, int]] = {}

    def give(self, key: tuple[int, int], value: _Contribution) -> None:
        stats = self.cells.setdefault(key, _Cell())
        stats.total += 1
        stats.merged += int(value.merged)
        if value.exponent >= 0:
            stats.exponents[value.exponent] = stats.exponents.get(value.exponent, 0) + 1
            shapes = self.shapes.setdefault(value.exponent, {})
            shapes[value.shape] = shapes.get(value.shape, 0) + 1

    def take(self, key: tuple[int, int], value: _Contribution) -> None:
        stats = self.cells[key]
        stats.total -= 1
        stats.merged -= int(value.merged)
        if value.exponent >= 0:
            stats.exponents[value.exponent] -= 1
            if not stats.exponents[value.exponent]:
                del stats.exponents[value.exponent]
            shapes = self.shapes[value.exponent]
            shapes[value.shape] -= 1
            if not shapes[value.shape]:
                del shapes[value.shape]
            if not shapes:
                del self.shapes[value.exponent]

    def dominant_shape(self, exponent: int) -> Form | None:
        """Nejčastější podoba koncovky; při shodě počtů menší posloupnost hlásek."""
        shapes = self.shapes.get(exponent)
        if not shapes:
            return None
        return max(sorted(shapes), key=lambda shape: shapes[shape])

    def productive(self, key: tuple[int, int], names: list[str]) -> int:
        """Produktivní koncovka buňky: nejvíc tvarů, při shodě menší jméno koncovky."""
        stats = self.cells.get(key)
        if stats is None or not stats.exponents:
            return -1
        ordered = sorted(stats.exponents, key=lambda exponent: names[exponent])
        return max(ordered, key=lambda exponent: stats.exponents[exponent])

    def weakness(self, key: tuple[int, int]) -> float:
        stats = self.cells.get(key)
        if stats is None or not stats.total:
            return 1.0
        return stats.merged / stats.total


class _Slot:
    def __init__(self) -> None:
        self.members = WordMembershipIndex()
        self.exponents = ExponentCounts()
        #: Syrový stav (tvar, hranice, koncovka, tvar kořene) a příspěvek podle čísla morfému.
        self.seen: dict[int, tuple[int, int, int, int]] = {}
        self.contributions: dict[int, _Contribution] = {}
        self.leveling = 0
        self.extension = 0


class MorphologyCandidateIndex:
    """Místa vyrovnání a rozšíření (nad stavem kódů v ``MorphIndex``)."""

    def __init__(self, index: MorphIndex) -> None:
        self._index = index

    def counts(self, token: int) -> tuple[int, int]:
        slot = self._index.slots.get(token)
        return (0, 0) if slot is None else (slot.leveling, slot.extension)

    def candidates(self, token: int, extension: bool) -> tuple[list[int], list[int]]:
        """Místa seřazená podle řetězcového ID místa: čísla tvarů a (u rozšíření) koncovek."""
        slot = self._index.slots.get(token)
        if slot is None:
            return [], []
        names = self._index.names
        found = []
        for number in slot.members.members:
            value = slot.contributions[number]
            if extension:
                if value.extension >= 0:
                    found.append((number, value.extension))
            elif value.leveling:
                found.append((number, -1))
        found.sort(key=lambda item: (names[item[0]] + "|" + (names[item[1]] if extension else "")).encode())
        return [number for number, _ in found], [exponent for _, exponent in found]


class MorphIndex:
    """Členství, koncovky, kandidáti a slabost všech kódů světa (reference v Pythonu)."""

    native = False

    def __init__(self) -> None:
        self.names: list[str] = []
        self.defaults: dict[int, Form] = {}
        self.slots: dict[int, _Slot] = {}
        self.candidates = MorphologyCandidateIndex(self)

    # --- číselníky ------------------------------------------------------------

    def set_names(self, names: list[str]) -> None:
        self.names.extend(names)

    def set_defaults(self, numbers: list[int], forms: list[Form]) -> None:
        for number, form in zip(numbers, forms):
            self.defaults.setdefault(number, tuple(form))

    # --- dorovnání ------------------------------------------------------------

    def sync(
        self, forms: list[Form], columns: tuple[Any, ...], tokens: list[int], flags: list[Any],
        store: list[tuple[Any, Any, Any]],
    ) -> list[int]:
        """Dorovná kódy; vrací čísla morfémů, jejichž výchozí tvar je třeba doplnit (pak znovu)."""
        needs: set[int] = set()
        for token, code_flags, raw in zip(tokens, flags, store):
            needs.update(self._sync_code(forms, columns, token, code_flags, raw))
        return sorted(needs)

    def _sync_code(
        self, forms: list[Form], columns: tuple[Any, ...], token: int, flags: Any,
        store: tuple[Any, Any, Any],
    ) -> list[int]:
        kind, word_class, cell, lexeme, exponent_column, boundary_column = columns
        raw_form, raw_boundary, raw_exponent = store
        slot = self.slots.setdefault(token, _Slot())

        def form_of(number: int) -> Form | None:
            raw = _at(raw_form, number, RAW_NONE)
            return forms[raw] if raw >= 0 else self.defaults.get(number)

        def seen_of(number: int) -> tuple[int, int, int, int]:
            root = _at(lexeme, number, RAW_NONE)
            return (
                _at(raw_form, number, RAW_NONE), _at(raw_boundary, number, RAW_NONE),
                _at(raw_exponent, number, RAW_NONE), _at(raw_form, root, RAW_NONE) if root >= 0 else RAW_NONE,
            )

        changed = slot.members.changes(flags, kind, word_class, cell)
        fresh, removed = ([], []) if changed is None else changed
        gone = set(removed)
        dirty = [
            number for number in [*(n for n in slot.members.members if n not in gone), *fresh]
            if slot.seen.get(number, _FRESH) != seen_of(number)
        ]
        needs: set[int] = set()
        for number in dirty:
            root = _at(lexeme, number, RAW_NONE)
            for unit in (number, root):
                if unit >= 0 and form_of(unit) is None:
                    needs.add(unit)
        if needs:
            return sorted(needs)
        for number in removed:
            if number in slot.contributions:
                self._take(slot, number, word_class, cell)
            slot.seen.pop(number, None)
        if changed is not None:
            slot.members.apply(flags, fresh, removed)
        for number in dirty:
            if number in slot.contributions:
                self._take(slot, number, word_class, cell)
            root = _at(lexeme, number, RAW_NONE)
            form, root_form = form_of(number), form_of(root)
            assert form is not None and root_form is not None
            if _at(raw_form, number, RAW_NONE) >= 0:
                boundary = _at(raw_boundary, number, RAW_NONE)
                exponent = _at(raw_exponent, number, RAW_NONE)
            else:
                boundary = _at(boundary_column, number, RAW_NONE)
                exponent = _at(exponent_column, number, RAW_NONE)
            stem = form if boundary < 0 else form[:boundary]
            ending = () if boundary < 0 else form[boundary:]
            merged = form == root_form
            key = (int(word_class[number]), int(cell[number]))
            stats = slot.exponents.cells.get(key)
            productive, ends = (stats.productive, stats.ends) if stats is not None else (-1, False)
            value = _Contribution(
                max(exponent, -1), ending if exponent >= 0 else (), merged, stem != root_form,
                _extension(productive, ends, exponent, merged),
            )
            slot.exponents.give(key, value)
            slot.contributions[number] = value
            slot.leveling += int(value.leveling)
            slot.extension += int(value.extension >= 0)
            slot.seen[number] = seen_of(number)
        if removed or changed is not None or dirty:
            self._refresh(slot, word_class, cell)
        return []

    @staticmethod
    def _take(slot: _Slot, number: int, word_class: Any, cell: Any) -> None:
        value = slot.contributions.pop(number)
        slot.exponents.take((int(word_class[number]), int(cell[number])), value)
        slot.leveling -= int(value.leveling)
        slot.extension -= int(value.extension >= 0)

    def _refresh(self, slot: _Slot, word_class: Any, cell: Any) -> None:
        """Přepočítá popisovače buněk a kandidáty rozšíření tam, kde se popisovač změnil."""
        changed = set()
        for key, stats in slot.exponents.cells.items():
            productive = slot.exponents.productive(key, self.names)
            ends = bool(slot.exponents.dominant_shape(productive)) if productive >= 0 else False
            if (stats.productive, stats.ends) != (productive, ends):
                stats.productive, stats.ends = productive, ends
                changed.add(key)
        if not changed:
            return
        for number in slot.members.members:
            key = (int(word_class[number]), int(cell[number]))
            if key not in changed:
                continue
            value = slot.contributions[number]
            stats = slot.exponents.cells[key]
            extension = _extension(stats.productive, stats.ends, value.exponent, value.merged)
            if extension != value.extension:
                slot.extension += int(extension >= 0) - int(value.extension >= 0)
                value.extension = extension

    # --- čtení ----------------------------------------------------------------

    def counts(self, token: int) -> tuple[int, int]:
        return self.candidates.counts(token)

    def weakness(self, token: int, word_class: int, cell: int) -> float:
        slot = self.slots.get(token)
        return 1.0 if slot is None else slot.exponents.weakness((word_class, cell))

    def residual(self, token: int, word_class: int, cell: int) -> int:
        """Koncovka, kterou by buňka mohla předat jiné funkci (produktivní, s neprázdnou podobou), nebo −1."""
        slot = self.slots.get(token)
        stats = None if slot is None else slot.exponents.cells.get((word_class, cell))
        return stats.productive if stats is not None and stats.productive >= 0 and stats.ends else -1

    def members(self, token: int) -> list[int]:
        slot = self.slots.get(token)
        return [] if slot is None else list(slot.members.members)

    def stats(self, token: int) -> tuple[list[list[int]], list[tuple[int, list[int], int]]]:
        """Počty koncovek (třída, buňka, koncovka, počet) a podoby koncovek (koncovka, hlásky, počet)."""
        slot = self.slots.get(token)
        if slot is None:
            return [], []
        cells = [
            [word_class, cell, exponent, count]
            for (word_class, cell), stats in sorted(slot.exponents.cells.items())
            for exponent, count in sorted(stats.exponents.items())
        ]
        shapes = [
            (exponent, list(shape), count)
            for exponent, counted in sorted(slot.exponents.shapes.items())
            for shape, count in sorted(counted.items())
        ]
        return cells, shapes


class ExponentIndex:
    """Koncovky tvarů slov kódu jako slovníky (třída, buňka) → koncovka → počet a koncovka → podoba → počet.

    Pohled pro ``morphology.class_stats``: stav drží číselný index míst světa
    (:mod:`cee.v2.language.site_index`, v Rustu); tento objekt si z něj jen na požádání vyzvedne počty
    a převede je na jména. Je to totéž, co dřív počítal průběžný ``ExponentIndex`` nad řetězci.
    """

    def __init__(self) -> None:
        self.exponents: dict[tuple[str, str], Counter[str]] = {}
        self.shapes: dict[str, Counter[tuple[int, ...]]] = {}

    def sync(self, world: World, code: Code) -> bool:
        """Načte aktuální počty koncovek kódu; vrací, zda se něco změnilo."""
        before = (self.exponents, self.shapes)
        if world.table is None:
            self.exponents, self.shapes = _count_reference(world, code)
        else:
            from cee.v2.language.site_index import site_index

            index = site_index(world)
            index.prepare(world, [code])
            cells, shapes = index.stats(world, code)
            table, names = world.columns.morphemes, world.registry.morphemes.names
            self.exponents = {}
            for word_class, cell, exponent, count in cells:
                key = (table.word_classes.names[word_class], table.cells.names[cell])
                self.exponents.setdefault(key, Counter())[names[exponent]] = count
            self.shapes = {}
            for exponent, shape, count in shapes:
                self.shapes.setdefault(names[exponent], Counter())[tuple(shape)] = count
        return before != (self.exponents, self.shapes)


def _count_reference(
    world: World, code: Code
) -> tuple[dict[tuple[str, str], Counter[str]], dict[str, Counter[tuple[int, ...]]]]:
    """Počty koncovek úplně od nuly z celé slovní zásoby (svět bez tabulky hlásek a reference testů)."""
    exponents: dict[tuple[str, str], Counter[str]] = {}
    shapes: dict[str, Counter[tuple[int, ...]]] = {}
    for unit in sorted(code.phonology.vocabulary):
        morpheme = world.morphemes[unit]
        if morpheme.kind != "word" or morpheme.word_class is None or morpheme.cell is None:
            continue
        state = world.unit_of(code, unit)
        if state.exponent is None:
            continue
        exponents.setdefault((morpheme.word_class, morpheme.cell), Counter())[state.exponent] += 1
        shapes.setdefault(state.exponent, Counter())[state.ending] += 1
    return exponents, shapes
