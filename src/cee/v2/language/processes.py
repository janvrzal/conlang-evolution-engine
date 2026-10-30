"""Zvukový proces: jedna konkrétní změna v jednom prostředí (iterace 2).

Proces je hodnota procesní proměnné. Sám nic neukládá; ``apply`` vrátí nový
tvar a pravidelnost změny vzniká až ve fonologizaci (``restructure``).
Aplikace je dvoufázová: nejdřív se na *původním* tvaru najdou všechna místa,
teprve potom se změní najednou, takže změna nemůže živit sama sebe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Literal

from cee.v2.language.segments import Form, Pattern, SegmentTable

Operation = Literal["change", "replace", "delete", "insert_before", "insert_after", "merge_next"]
Stress = Literal["stressed", "unstressed"] | None
StressRule = Literal["initial", "second", "antepenult", "penult", "final"]


def nuclei(form: Form, table: SegmentTable) -> list[int]:
    return [index for index, segment in enumerate(form) if table.is_vowel(segment)]


def stressed_nucleus(form: Form, table: SegmentTable, rule: StressRule) -> int | None:
    found = nuclei(form, table)
    if not found:
        return None
    if rule == "initial":
        return found[0]
    if rule == "second":
        return found[1] if len(found) >= 2 else found[0]
    if rule == "antepenult":
        return found[-3] if len(found) >= 3 else found[0]
    if rule == "penult":
        return found[-2] if len(found) >= 2 else found[0]
    if rule == "final":
        return found[-1]
    raise ValueError(f"Neznámé pravidlo přízvuku: {rule}")


_MISSING = object()
#: Paměť aplikací procesů; při zaplnění se vyprázdní (výsledek se nemění).
_APPLIED: dict[tuple[object, ...], object] = {}
_APPLIED_LIMIT = 1 << 18


@dataclass(frozen=True)
class Process:
    family: str
    target: Pattern
    operation: Operation
    #: Požadované rysy výstupu u operace ``change``.
    changes: tuple[tuple[str, str], ...] = ()
    #: Výstupní hláska u ``replace``, vkládaná hláska u ``insert_*``,
    #: výsledek splynutí u ``merge_next``.
    segment: int | None = None
    left: Pattern | None = None
    right: Pattern | None = None
    stress: Stress = None
    #: Jen uvnitř slova: mezi první a poslední samohláskou (synkopa).
    medial: bool = False
    #: Úspora artikulace (−1 až 1), viz tlak ``Articulation``.
    ease: float = 0.0
    #: Vlastní dopad na zřetelnost bez ohledu na lexikon, viz ``Clarity``.
    clarity: float = 0.0
    #: Redukční změny postupují dřív v častých slovech (Bybee).
    reductive: bool = False
    #: Čitelný popis pro audit.
    label: str = field(default="", compare=False)
    #: Explicitně zamýšlené diakritiky výstupu; jinak zůstává výstup plain.
    allow: tuple[str, ...] = ()
    #: Druhá následující pozice (např. /_N(C|#)).
    right2: Pattern | None = None

    @cached_property
    def key(self) -> str:
        """Kanonický klíč: stejná změna ve dvou skupinách je tatáž proměnná."""
        parts = [
            self.family, self.target.key, self.operation,
            ",".join(f"{value}{name}" for name, value in self.changes),
            "" if self.segment is None else str(self.segment),
            "" if self.left is None else self.left.key,
            "" if self.right is None else self.right.key,
            self.stress or "",
            "medial" if self.medial else "",
        ]
        if self.allow or self.right2 is not None:
            parts.extend((",".join(sorted(set(self.allow))), "" if self.right2 is None else self.right2.key))
        return "|".join(parts)

    def sites(self, form: Form, table: SegmentTable, rule: StressRule) -> list[int]:
        """Indexy, na které proces v tomto tvaru dopadne (bez minimality)."""
        stressed = stressed_nucleus(form, table, rule) if self.stress else None
        found_nuclei = nuclei(form, table) if self.medial else []
        boundary = table.boundary
        found = []
        last = len(form) - 1
        for index, segment in enumerate(form):
            if segment not in self.target:
                continue
            if self.left is not None and (form[index - 1] if index > 0 else boundary) not in self.left:
                continue
            if self.right is not None and (form[index + 1] if index < last else boundary) not in self.right:
                continue
            if self.right2 is not None and (
                form[index + 2] if index + 2 <= last else boundary
            ) not in self.right2:
                continue
            if self.stress == "stressed" and index != stressed:
                continue
            if self.stress == "unstressed" and (index == stressed or not table.is_vowel(segment)):
                continue
            if self.operation == "merge_next" and index == last:
                continue
            if self.medial and not (found_nuclei and found_nuclei[0] < index < found_nuclei[-1]):
                continue
            # Vložení vedle stejné hlásky by jen zdvojilo, co už tam je (jje).
            if self.operation == "insert_before" and index > 0 and form[index - 1] == self.segment:
                continue
            if self.operation == "insert_after" and index < last and form[index + 1] == self.segment:
                continue
            found.append(index)
        return found

    def apply(self, form: Form, table: SegmentTable, rule: StressRule) -> Form | None:
        result = self.apply_tracked(form, table, rule, None)
        return None if result is None else result[0]

    def apply_tracked(
        self, form: Form, table: SegmentTable, rule: StressRule, boundary: int | None
    ) -> tuple[Form, int | None] | None:
        """Totéž co :meth:`_apply`, ale zapamatované: proces je čistá funkce tvaru.

        Stejné tvary se opakují napříč skupinami i kroky, takže paměť ušetří
        většinu výpočtu. Výsledek je bitově stejný.
        """
        key = (self.key, form, rule, boundary, id(table))
        found = _APPLIED.get(key, _MISSING)
        if found is _MISSING:
            if len(_APPLIED) >= _APPLIED_LIMIT:
                _APPLIED.clear()
            found = _APPLIED[key] = self._apply(form, table, rule, boundary)
        return found  # type: ignore[return-value]

    def _apply(
        self, form: Form, table: SegmentTable, rule: StressRule, boundary: int | None
    ) -> tuple[Form, int | None] | None:
        """Nový tvar, nebo ``None``, když se nic nezmění či by slovo zaniklo.

        Obsahové slovo nesmí klesnout pod dvě hlásky ani ztratit poslední
        samohlásku. Takové slovo změnu nepřijme — to je běžný zdroj výjimek
        (minimální slovo), ne chyba.
        """
        sites = self.sites(form, table, rule)
        if not sites:
            return None
        result: list[int] = []
        skip = -1
        targets = set(sites)
        # Hranice kmen | koncovka: kolik výstupních hlásek vzniklo z kmene.
        # Vložená hláska na hranici patří ke koncovce, splynutí přes hranici
        # ke kmeni.
        new_boundary = boundary
        for index, segment in enumerate(form):
            if boundary is not None and index == boundary:
                new_boundary = len(result)
            if index == skip:
                continue
            if index not in targets:
                result.append(segment)
                continue
            operation = self.operation
            if operation == "change":
                output = table.changed(segment, self.changes, self.allow)
                result.append(segment if output is None else output)
            elif operation == "replace":
                assert self.segment is not None
                result.append(self.segment)
            elif operation == "delete":
                continue
            elif operation == "insert_before":
                assert self.segment is not None
                result.extend((self.segment, segment))
            elif operation == "insert_after":
                assert self.segment is not None
                result.extend((segment, self.segment))
            else:
                assert self.segment is not None
                result.append(self.segment)
                skip = index + 1
        if boundary is not None and boundary >= len(form):
            new_boundary = len(result)
        new = tuple(result)
        if new == form or len(new) < 2 or not any(table.is_vowel(segment) for segment in new):
            return None
        return new, new_boundary
