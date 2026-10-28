"""Zvukové změny (iterace 3, oblast A).

Každá rodina je parametrický prostor: z aktuálního inventáře kódu vyrobí
konkrétní procesy (třída cíle × výstup × prostředí). Kandidát, který ve
slovní zásobě nemá aspoň pár výskytů, se nenabízí. O tom, jestli se změna
prosadí, nerozhoduje počet zasažených slov (to byla chyba legacy jádra, kde
vždy vyhrála nejširší změna samohlásek), ale tlaky a šíření.

Váhy ``prior`` jsou autorský typologický prior podle obecné literatury o
směrech zvukové změny (např. lenice je častější než fortice). Nepřebírají
žádnou databázi; viz ``docs/DIRECTIONAL_SOURCES.md``.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Literal, Mapping, Sequence, cast

import numpy as np
import numpy.typing as npt

from cee.v2.changes.base import Change, InnovationContext
from cee.v2.language.processes import Process, stressed_nucleus
from cee.v2.language.segments import Pattern, SegmentTable
from cee.v2.phonology import register
from cee.v2.pressures import (
    Actuation,
    Articulation,
    Clarity,
    Conformity,
    Dispersion,
    FunctionalLoad,
    Phonotactics,
    Pressure,
)
from cee.v2.repertoire import Origin, Variable, Variant

Domain = Literal["consonant", "vowel", "structure"]

#: Očekávaný počet zvukových inovací na skupinu a generaci (všechny rodiny
#: dohromady). Většina z nich zanikne; kalibruje se v M7.
SOUND_INNOVATIONS_PER_GENERATION = 0.6
#: Kolik výskytů prostředí ve slovní zásobě dá kandidátovi plnou šanci.
FULL_SUPPORT = 8
MIN_SUPPORT = 2

SOUND_PRESSURES: Mapping[type[Pressure], float] = {
    Articulation: 1.0,
    Clarity: 0.6,
    FunctionalLoad: 1.0,
    Dispersion: 0.5,
    Phonotactics: 0.4,
    Conformity: 0.1,
    Actuation: 1.0,
}


@dataclass(frozen=True)
class ContextStats:
    """Výskyty (předchozí, hláska, následující, přízvuk) ve slovní zásobě."""

    previous: npt.NDArray[np.intp]
    segment: npt.NDArray[np.intp]
    following: npt.NDArray[np.intp]
    stressed: npt.NDArray[np.bool_]
    count: npt.NDArray[np.float64]
    inventory: tuple[int, ...]

    def support(self, process: Process, table: SegmentTable) -> float:
        mask = process.target.mask[self.segment]
        if process.left is not None:
            mask &= process.left.mask[self.previous]
        if process.right is not None:
            mask &= process.right.mask[self.following]
        if process.stress == "stressed":
            mask &= self.stressed
        elif process.stress == "unstressed":
            mask &= ~self.stressed & table.vowel_mask[self.segment]
        return float(self.count[mask].sum())


def context_stats(context: InnovationContext) -> ContextStats | None:
    """Statistika prostředí kódu; drží se, dokud se slovní zásoba nezmění."""
    world, code = context.world, context.code
    table = world.table
    state = code.phonology
    if table is None or not state.vocabulary:
        return None
    cached = state.cache.get("context-stats")
    if cached is not None and cached[0] == state.version:
        return cast(ContextStats, cached[1])
    counts: dict[tuple[int, int, int, bool], int] = {}
    for morpheme_id in state.vocabulary:
        form = world.form_of(code, morpheme_id)
        stress = stressed_nucleus(form, table, code.stress_rule)
        for index, segment in enumerate(form):
            key = (
                form[index - 1] if index else table.boundary,
                segment,
                form[index + 1] if index + 1 < len(form) else table.boundary,
                index == stress,
            )
            counts[key] = counts.get(key, 0) + 1
    keys = sorted(counts)
    stats = ContextStats(
        previous=np.array([key[0] for key in keys], dtype=np.intp),
        segment=np.array([key[1] for key in keys], dtype=np.intp),
        following=np.array([key[2] for key in keys], dtype=np.intp),
        stressed=np.array([key[3] for key in keys], dtype=bool),
        count=np.array([counts[key] for key in keys], dtype=np.float64),
        inventory=tuple(sorted({key[1] for key in keys})),
    )
    state.cache["context-stats"] = (state.version, stats)
    return stats


class SoundChange(Change):
    """Rodina zvukových změn. Podtřída říká jen, jaké procesy umí vyrobit."""

    target = "process"
    rate_basis = "generation"
    pressures = SOUND_PRESSURES
    base_rate = 0.0  # míra se počítá z ``prior`` a opory kandidáta

    prior: ClassVar[float]
    domain: ClassVar[Domain]

    @abstractmethod
    def candidates(self, table: SegmentTable, inventory: Sequence[int]) -> list[Process]:
        """Procesy, které rodina umí v daném inventáři vyrobit."""

    def _supported(self, context: InnovationContext) -> dict[str, tuple[Process, float]]:
        state = context.code.phonology
        cache_key = ("sound-sites", self.kind)
        cached = state.cache.get(cache_key)
        if cached is not None and cached[0] == state.version:
            return cast(dict[str, tuple[Process, float]], cached[1])
        stats = context_stats(context)
        table = context.world.table
        found: dict[str, tuple[Process, float]] = {}
        if stats is not None and table is not None:
            for process in self.candidates(table, stats.inventory):
                support = stats.support(process, table)
                variable_id = Variable("process", process.key).id
                if support >= MIN_SUPPORT and variable_id not in found:
                    found[variable_id] = (process, support)
        state.cache[cache_key] = (state.version, found)
        return found

    def sites(self, context: InnovationContext) -> Sequence[str]:
        if context.world.table is None:
            return ()  # svět bez hláskových tvarů (M1)
        return sorted(self._supported(context))

    def rate(self, context: InnovationContext, site: str) -> float:
        supported = self._supported(context)
        share = self.prior / _total_prior()
        _, support = supported[site]
        return SOUND_INNOVATIONS_PER_GENERATION * share * min(1.0, support / FULL_SUPPORT) / len(supported)

    def propose(
        self, context: InnovationContext, site: str, rng: np.random.Generator, index: int
    ) -> Variant | None:
        process, _ = self._supported(context)[site]
        _, variant = register(
            context.world, process,
            Origin(self.kind, context.tick, context.year, context.group.id),
        )
        return variant


def _present(table: SegmentTable, inventory: Sequence[int], pattern: Pattern) -> list[int]:
    return [segment for segment in inventory if segment in pattern]


def _single(table: SegmentTable, segment: int) -> Pattern:
    return table.segments([table.ipa[segment]])


def _make(family: str, label: str, **fields: object) -> Process:
    return Process(family=family, label=label, **fields)  # type: ignore[arg-type]


class Voicing(SoundChange):
    """Lenice 1: znělost neznělých obstruentů mezi samohláskami (p → b)."""

    kind, prior, domain = "voicing", 1.0, "consonant"

    def candidates(self, table, inventory):
        stops = table.pattern({"syl": "-", "son": "-", "voi": "-"})
        found = [
            _make(self.kind, f"{table.ipa[s]} → zněle /V_V", target=_single(table, s),
                  operation="change", changes=(("voi", "+"),), left=table.VOWEL, right=table.VOWEL,
                  ease=0.15, clarity=-0.1, reductive=True)
            for s in _present(table, inventory, stops)
        ]
        if len(_present(table, inventory, table.pattern({"syl": "-", "son": "-", "voi": "-", "cont": "-"}))) >= 2:
            found.append(_make(
                self.kind, "řada neznělých okluziv → zněle /V_V",
                target=table.pattern({"syl": "-", "son": "-", "voi": "-", "cont": "-"}),
                operation="change", changes=(("voi", "+"),), left=table.VOWEL, right=table.VOWEL,
                ease=0.15, clarity=-0.1, reductive=True,
            ))
        return found


class Spirantization(SoundChange):
    """Lenice 2: okluziva mezi samohláskami se stane frikativou (b → β)."""

    kind, prior, domain = "spirantization", 0.8, "consonant"

    def candidates(self, table, inventory):
        stops = table.pattern({"syl": "-", "son": "-", "cont": "-", "delrel": "-"})
        found = []
        for s in _present(table, inventory, stops):
            found.append(_make(
                self.kind, f"{table.ipa[s]} → frikativa /V_V", target=_single(table, s),
                operation="change", changes=(("cont", "+"), ("strid", "-")),
                left=table.VOWEL, right=table.VOWEL, ease=0.15, clarity=-0.15, reductive=True,
            ))
        voiced = table.pattern({"syl": "-", "son": "-", "cont": "-", "delrel": "-", "voi": "+"})
        if len(_present(table, inventory, voiced)) >= 2:
            found.append(_make(
                self.kind, "řada znělých okluziv → frikativy /V_V", target=voiced,
                operation="change", changes=(("cont", "+"), ("strid", "-")),
                left=table.VOWEL, right=table.VOWEL, ease=0.15, clarity=-0.15, reductive=True,
            ))
        return found


class Debuccalization(SoundChange):
    """Ztráta ústního místa: s, f, x → h mezi samohláskami nebo na konci."""

    kind, prior, domain = "debuccalization", 0.4, "consonant"

    def candidates(self, table, inventory):
        h = table.id_of("h")
        fricatives = table.pattern({"syl": "-", "son": "-", "cont": "+", "voi": "-"})
        found = []
        for s in _present(table, inventory, fricatives):
            if s == h:
                continue
            for left, right, where in ((table.VOWEL, table.VOWEL, "V_V"), (table.VOWEL, table.BOUNDARY, "V_#")):
                found.append(_make(
                    self.kind, f"{table.ipa[s]} → h /{where}", target=_single(table, s),
                    operation="replace", segment=h, left=left, right=right,
                    ease=0.125, clarity=-0.2, reductive=True,
                ))
        return found


class IntervocalicLoss(SoundChange):
    """Lenice 3: znělá frikativa, h nebo polosamohláska mezi samohláskami zmizí."""

    kind, prior, domain = "intervocalic_loss", 0.4, "consonant"

    def candidates(self, table, inventory):
        weak = sorted(
            s for s in inventory
            if not table.is_vowel(s) and (
                table.ipa[s] in ("h", "j", "w")
                or (table.feature(s, "cont") == 1 and table.feature(s, "voi") == 1
                    and table.feature(s, "son") != 1 and table.feature(s, "strid") != 1)
            )
        )
        return [
            _make(self.kind, f"{table.ipa[s]} → ∅ /V_V", target=_single(table, s), operation="delete",
                  left=table.VOWEL, right=table.VOWEL, ease=0.15, clarity=-0.4, reductive=True)
            for s in weak
        ]


class Fortition(SoundChange):
    """Zesílení na začátku slova: frikativa → okluziva, j → d͡ʒ."""

    kind, prior, domain = "fortition", 0.3, "consonant"

    def candidates(self, table, inventory):
        found = []
        fricatives = table.pattern({"syl": "-", "son": "-", "cont": "+", "voi": "+"})
        for s in _present(table, inventory, fricatives):
            found.append(_make(
                self.kind, f"{table.ipa[s]} → okluziva /#_", target=_single(table, s),
                operation="change", changes=(("cont", "-"), ("strid", "-"), ("delrel", "-")),
                left=table.BOUNDARY, ease=-0.1, clarity=0.3,
            ))
        if table.id_of("j") in inventory:
            found.append(_make(
                self.kind, "j → d͡ʒ /#_", target=table.segments(["j"]), operation="replace",
                segment=table.id_of("d͡ʒ"), left=table.BOUNDARY, ease=-0.1, clarity=0.3,
            ))
        return found


class Palatalization(SoundChange):
    """Velára, dentála nebo s před předním vokálem či j se posune k patru."""

    kind, prior, domain = "palatalization", 0.8, "consonant"

    def candidates(self, table, inventory):
        place = ["cor", "ant", "distr", "hi", "lo", "back", "delrel", "strid", "lab"]
        front = table.pattern({"hi": "+", "back": "-"})
        outputs = {
            "k": table.features_of("t͡ʃ", place), "ɡ": table.features_of("d͡ʒ", place),
            "t": table.features_of("t͡s", place), "d": table.features_of("d͡z", place),
            "s": table.features_of("ʃ", ["ant", "distr", "cor"]),
        }
        found = []
        for symbol, changes in outputs.items():
            segment = table.id_of(symbol)
            if segment in inventory:
                found.append(_make(
                    self.kind, f"{symbol} → palatála /_i", target=_single(table, segment),
                    operation="change", changes=changes, right=front, ease=0.15, clarity=0.0,
                    reductive=True,
                ))
        return found


class NasalAssimilation(SoundChange):
    """Nazála převezme místo následující okluzivy (n → m /_p)."""

    kind, prior, domain = "nasal_assimilation", 0.8, "consonant"

    def candidates(self, table, inventory):
        nasals = _present(table, inventory, table.pattern({"nas": "+", "syl": "-"}))
        places = (
            ("m", table.pattern({"syl": "-", "son": "-", "lab": "+"})),
            ("n", table.pattern({"syl": "-", "son": "-", "cor": "+"})),
            ("ŋ", table.pattern({"syl": "-", "son": "-", "hi": "+", "back": "+"})),
        )
        found = []
        for nasal in nasals:
            for symbol, before in places:
                output = table.id_of(symbol)
                if output != nasal:
                    found.append(_make(
                        self.kind, f"{table.ipa[nasal]} → {symbol} před homorganní okluzivou",
                        target=_single(table, nasal), operation="replace", segment=output,
                        right=before, ease=0.2, clarity=-0.05,
                    ))
        return found


class VoicingAssimilation(SoundChange):
    """Obstruent převezme znělost následujícího obstruentu."""

    kind, prior, domain = "voicing_assimilation", 0.6, "consonant"

    def candidates(self, table, inventory):
        found = []
        for value, opposite in (("+", "-"), ("-", "+")):
            target = table.pattern({"syl": "-", "son": "-", "voi": opposite})
            if _present(table, inventory, target):
                found.append(_make(
                    self.kind, f"obstruent → {value}zněle před {value}znělým",
                    target=target, operation="change", changes=(("voi", value),),
                    right=table.pattern({"syl": "-", "son": "-", "voi": value}),
                    ease=0.15, clarity=-0.05,
                ))
        return found


class FinalDevoicing(SoundChange):
    kind, prior, domain = "final_devoicing", 0.5, "consonant"

    def candidates(self, table, inventory):
        target = table.pattern({"syl": "-", "son": "-", "voi": "+"})
        if not _present(table, inventory, target):
            return []
        return [_make(self.kind, "znělý obstruent → nezněle /_#", target=target, operation="change",
                      changes=(("voi", "-"),), right=table.BOUNDARY, ease=0.1, clarity=-0.1)]


_CONSONANT_CLASSES = {
    "okluzivy": {"syl": "-", "son": "-", "cont": "-"},
    "nazály": {"syl": "-", "nas": "+"},
    "frikativy": {"syl": "-", "son": "-", "cont": "+"},
    "likvidy": {"syl": "-", "son": "+", "cons": "+", "nas": "-"},
}


class CodaLoss(SoundChange):
    """Koncová souhláska (třída nebo jedna hláska) zmizí."""

    kind, prior, domain = "coda_loss", 0.5, "consonant"

    def candidates(self, table, inventory):
        found = []
        for name, features in _CONSONANT_CLASSES.items():
            pattern = table.pattern(features)
            present = _present(table, inventory, pattern)
            if present:
                found.append(_make(self.kind, f"{name} → ∅ /V_#", target=pattern, operation="delete",
                                   left=table.VOWEL, right=table.BOUNDARY, ease=0.15, clarity=-0.3,
                                   reductive=True))
            for segment in present:
                found.append(_make(self.kind, f"{table.ipa[segment]} → ∅ /V_#",
                                   target=_single(table, segment), operation="delete",
                                   left=table.VOWEL, right=table.BOUNDARY, ease=0.15, clarity=-0.3,
                                   reductive=True))
        return found


class ClusterSimplification(SoundChange):
    """První souhláska vnitřního shluku zmizí (VCCV → VCV)."""

    kind, prior, domain = "cluster_simplification", 0.6, "consonant"

    def candidates(self, table, inventory):
        found = []
        for name, features in _CONSONANT_CLASSES.items():
            pattern = table.pattern(features)
            if _present(table, inventory, pattern):
                found.append(_make(self.kind, f"{name} → ∅ /V_C", target=pattern, operation="delete",
                                   left=table.VOWEL, right=table.CONSONANT, ease=0.15, clarity=-0.2,
                                   reductive=True))
        return found


def _vowels(table: SegmentTable, inventory: Sequence[int]) -> list[int]:
    return [segment for segment in inventory if table.is_vowel(segment)]


class VowelReduction(SoundChange):
    """Nepřízvučný vokál se oslabí na ə."""

    kind, prior, domain = "vowel_reduction", 0.8, "vowel"

    def candidates(self, table, inventory):
        schwa = table.id_of("ə")
        found = [
            _make(self.kind, f"{table.ipa[v]} → ə v nepřízvučné slabice", target=_single(table, v),
                  operation="replace", segment=schwa, stress="unstressed", ease=0.15, clarity=-0.2,
                  reductive=True)
            for v in _vowels(table, inventory) if v != schwa
        ]
        found.append(_make(self.kind, "nevysoké vokály → ə v nepřízvučné slabice",
                           target=table.pattern({"syl": "+", "hi": "-"}), operation="replace",
                           segment=schwa, stress="unstressed", ease=0.15, clarity=-0.2, reductive=True))
        return found


class Syncope(SoundChange):
    """Nepřízvučný vokál mezi souhláskami zmizí."""

    kind, prior, domain = "syncope", 0.5, "vowel"

    def candidates(self, table, inventory):
        found = [
            _make(self.kind, f"{table.ipa[v]} → ∅ /C_C nepřízvučně", target=_single(table, v),
                  operation="delete", left=table.CONSONANT, right=table.CONSONANT,
                  stress="unstressed", medial=True, ease=0.15, clarity=-0.15, reductive=True)
            for v in _vowels(table, inventory)
        ]
        found.append(_make(self.kind, "vysoké vokály → ∅ /C_C nepřízvučně",
                           target=table.pattern({"syl": "+", "hi": "+"}), operation="delete",
                           left=table.CONSONANT, right=table.CONSONANT, stress="unstressed",
                           medial=True, ease=0.15, clarity=-0.15, reductive=True))
        return found


class Apocope(SoundChange):
    """Koncový nepřízvučný vokál zmizí."""

    kind, prior, domain = "apocope", 0.5, "vowel"

    def candidates(self, table, inventory):
        found = [
            _make(self.kind, f"{table.ipa[v]} → ∅ /C_# nepřízvučně", target=_single(table, v),
                  operation="delete", left=table.CONSONANT, right=table.BOUNDARY,
                  stress="unstressed", ease=0.15, clarity=-0.15, reductive=True)
            for v in _vowels(table, inventory)
        ]
        found.append(_make(self.kind, "vokály → ∅ /C_# nepřízvučně",
                           target=table.VOWEL, operation="delete", left=table.CONSONANT,
                           right=table.BOUNDARY, stress="unstressed", ease=0.15, clarity=-0.15,
                           reductive=True))
        return found


#: Obyčejné vokály, mezi kterými se posouvá kvalita.
_VOWEL_SPACE = ("i", "y", "ɨ", "u", "e", "ø", "ə", "o", "ɛ", "ɔ", "a", "ɑ", "æ")


class VowelShift(SoundChange):
    """Posun kvality jednoho vokálu o krok v prostoru (zvýšení, snížení, …).

    Řetězové posuny se tu neprogramují: vzniknou, když uvolněné místo
    zvýhodní tlak disperze a funkční zátěž brání splynutí (iterace 3).
    """

    kind, prior, domain = "vowel_shift", 1.2, "vowel"

    def candidates(self, table, inventory):
        space = [table.id_of(symbol) for symbol in _VOWEL_SPACE]
        found = []
        for vowel in _vowels(table, inventory):
            if vowel not in space:
                continue
            origin = table.vowel_coordinates(vowel)
            for other in space:
                if other == vowel:
                    continue
                target = table.vowel_coordinates(other)
                steps = [abs(a - b) for a, b in zip(origin, target)]
                # Jeden krok v jediném rozměru: sousední vokál, ne skok přes systém.
                if sum(1 for step in steps if step > 0) != 1 or max(steps) > 1.0:
                    continue
                for stress, where in ((None, "všude"), ("stressed", "v přízvučné slabice")):
                    found.append(_make(
                        self.kind, f"{table.ipa[vowel]} → {table.ipa[other]} {where}",
                        target=_single(table, vowel), operation="replace", segment=other,
                        stress=stress, ease=0, clarity=0.0,
                    ))
        return found


class Diphthongization(SoundChange):
    """Přízvučné středové e, o získá polosamohlásku (e → je, o → wo)."""

    kind, prior, domain = "diphthongization", 0.4, "vowel"

    def candidates(self, table, inventory):
        found = []
        for symbol, glide in (("e", "j"), ("ɛ", "j"), ("o", "w"), ("ɔ", "w")):
            segment = table.id_of(symbol)
            if segment in inventory:
                found.append(_make(self.kind, f"{symbol} → {glide}{symbol} v přízvučné slabice",
                                   target=_single(table, segment), operation="insert_before",
                                   segment=table.id_of(glide), stress="stressed",
                                   ease=-0.05, clarity=0.2))
        return found


class Monophthongization(SoundChange):
    """Dvojice vokálů splyne v jeden (ai → e, au → o)."""

    kind, prior, domain = "monophthongization", 0.5, "vowel"

    def candidates(self, table, inventory):
        found = []
        for first, second, output in (("a", "i", "e"), ("a", "u", "o"), ("e", "i", "i"),
                                      ("o", "u", "u"), ("o", "i", "ø"), ("a", "e", "ɛ")):
            a, b = table.id_of(first), table.id_of(second)
            if a in inventory and b in inventory:
                found.append(_make(self.kind, f"{first}{second} → {output}", target=_single(table, a),
                                   operation="merge_next", segment=table.id_of(output),
                                   right=_single(table, b), ease=0.15, clarity=-0.1))
        return found


class GlideFormation(SoundChange):
    """Vysoký vokál před jiným vokálem se stane polosamohláskou (ia → ja)."""

    kind, prior, domain = "glide_formation", 0.5, "structure"

    def candidates(self, table, inventory):
        found = []
        for vowel, glide in (("i", "j"), ("u", "w")):
            segment = table.id_of(vowel)
            if segment in inventory:
                found.append(_make(self.kind, f"{vowel} → {glide} /_V", target=_single(table, segment),
                                   operation="replace", segment=table.id_of(glide), right=table.VOWEL,
                                   ease=0.1, clarity=-0.05))
        return found


def _epenthetic_vowel(table: SegmentTable, inventory: Sequence[int]) -> int:
    for symbol in ("ə", "e", "i", "a"):
        segment = table.id_of(symbol)
        if segment in inventory:
            return segment
    return table.id_of("e")


class Epenthesis(SoundChange):
    """Vložený vokál rozbije koncový shluk souhlásek (-CC → -CVC)."""

    kind, prior, domain = "epenthesis", 0.4, "structure"

    def candidates(self, table, inventory):
        vowel = _epenthetic_vowel(table, inventory)
        return [_make(self.kind, f"∅ → {table.ipa[vowel]} /C_C#", target=table.CONSONANT,
                      operation="insert_before", segment=vowel, left=table.CONSONANT,
                      right=table.BOUNDARY, ease=-0.1, clarity=0.2)]


class Prothesis(SoundChange):
    """Vokál před počátečním s + souhláska (sp- → esp-)."""

    kind, prior, domain = "prothesis", 0.15, "structure"

    def candidates(self, table, inventory):
        s = table.id_of("s")
        if s not in inventory:
            return []
        vowel = table.id_of("e") if table.id_of("e") in inventory else _epenthetic_vowel(table, inventory)
        return [_make(self.kind, f"∅ → {table.ipa[vowel]} /#_sC", target=table.segments(["s"]),
                      operation="insert_before", segment=vowel, left=table.BOUNDARY,
                      right=table.CONSONANT, ease=-0.05, clarity=0.1)]


SOUND_CHANGES: tuple[SoundChange, ...] = (
    Voicing(), Spirantization(), Debuccalization(), IntervocalicLoss(), Fortition(),
    Palatalization(), NasalAssimilation(), VoicingAssimilation(), FinalDevoicing(), CodaLoss(),
    ClusterSimplification(), VowelReduction(), Syncope(), Apocope(), VowelShift(),
    Diphthongization(), Monophthongization(), GlideFormation(), Epenthesis(), Prothesis(),
)


def _total_prior() -> float:
    return sum(change.prior for change in SOUND_CHANGES)
