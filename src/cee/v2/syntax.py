"""Konstrukce v běžící simulaci (milníky M4 a M4b).

Nic tu není napsané pro konkrétní funkci: vše řídí katalog
``cee/data/v2_grammar.yaml``. Konstrukční proměnná se šíří jako každá jiná;
navíc jsou tu jen tyto věci:

- **Slabost syntetického vyjádření**: kolik tvarů buňky paradigmatu zní
  stejně jako citační tvar (koncovka zvukovými změnami zanikla). Funkce bez
  buňky (jazyk ji koncovkou nevyjadřuje) má slabost 1.
- **Síla vyjádření** konstrukce (0 až 1), podklad tlaku k obnově.
- **Nadbytečnost**: funkce, jejíž roli převzala jiná (pád → pevný
  slovosled), skoro nic neztratí, když zanikne.
- **Zápis nové koncovky**: když převáží nová syntetická konstrukce (opis
  srostl, nebo exaptace převzala zbytkovou koncovku), zapíše se do tvarů
  slov; buňka paradigmatu, kterou jazyk dosud neměl, přitom vznikne. Nová
  koncovka pak podléhá zvukovým změnám jako každá jiná a cyklus může začít
  znovu.
"""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from typing import TYPE_CHECKING, cast

from cee.v2.history import History
from cee.v2.language.constructions import Construction, GrammaticalFunction, catalog, catalog_for
from cee.v2.language.lexicon import Morpheme, UnitForm
from cee.v2.language.morphology import unit_id
from cee.v2.language.segments import Form
from cee.v2.repertoire import Origin, Variable, Variant
from cee.v2.rng import stable_id

if TYPE_CHECKING:
    from cee.v2.world import Code, World


def variable_id(function: str) -> str:
    return Variable("construction", function).id


def functions(world: World, template: str | None = None) -> list[GrammaticalFunction]:
    """Funkce katalogu, které jazykový svět sleduje (mají konstrukční proměnnou)."""
    return [
        entry for name, entry in sorted(catalog_for(world).items())
        if variable_id(name) in world.variables and (template is None or entry.template == template)
    ]


@lru_cache(maxsize=None)
def _cells() -> dict[tuple[str | None, str], GrammaticalFunction]:
    return {
        (entry.word_class, entry.cell): entry
        for _, entry in sorted(catalog().items()) if entry.cell is not None
    }


def function_of_cell(word_class: str | None, cell: str) -> GrammaticalFunction | None:
    """Funkce, kterou buňka paradigmatu vyjadřuje (citační buňka žádnou).

    Čte se z globálního katalogu, takže hodnoty ``need`` a ``context`` mohou
    být bez přepisů světa; volající smí použít jen identitu funkce.
    """
    return _cells().get((word_class, cell))


def register(world: World, construction: Construction, origin: Origin) -> tuple[str, Variant]:
    """Konstrukční proměnná a varianta; stejná konstrukce = stejná varianta."""
    variable = variable_id(construction.function)
    if variable not in world.variables:
        world.variables[variable] = Variable("construction", construction.function)
    variant_id = stable_id("variant", "construction", construction.key)
    if variant_id not in world.variants:
        world.variants[variant_id] = Variant(
            variant_id, variable, {"construction": construction}, origin
        )
    return variable, world.variants[variant_id]


def construction_of(world: World, variant_id: str) -> Construction:
    return cast(Construction, world.variants[variant_id].payload["construction"])


def dominant(world: World, group_id: str, function: str) -> Construction | None:
    if variable_id(function) not in world.variables:
        return None
    found = world.dominant(group_id, variable_id(function))
    if found is None:
        return None
    return construction_of(world, found[0])


def cell_units(world: World, code: Code, entry: GrammaticalFunction) -> list[str]:
    """Tvary slov ve slovní zásobě kódu, které funkci vyjadřují koncovkou."""
    return [
        unit for unit in sorted(code.phonology.vocabulary)
        if world.morphemes[unit].kind == "word"
        and world.morphemes[unit].word_class == entry.word_class
        and world.morphemes[unit].cell == entry.cell
    ]


def _weakness_reference(world: World, code: Code, function: str) -> float:
    """Podíl tvarů buňky, které splynuly s citačním tvarem (0 = koncovka drží).

    Funkce bez buňky v paradigmatu má slabost 1: koncovkou ji jazyk
    nevyjadřuje vůbec. Funkce mimo šablonu ``inflection`` má slabost 0.
    """
    from cee.v2.morphology import citation_form

    entry = catalog_for(world).get(function)
    if entry is None or entry.cell is None:
        return 0.0
    units = cell_units(world, code, entry)
    merged = sum(world.form_of(code, unit) == citation_form(world, code, unit) for unit in units)
    value = merged / len(units) if units else 1.0
    return value



def weakness(world: World, code: Code, function: str) -> float:
    """Podíl splynulých tvarů v gramatické buňce, průběžně udržovaný."""
    from cee.v2.language.morphology_index import WeaknessIndex

    entry = catalog_for(world).get(function)
    if entry is None or entry.cell is None:
        return 0.0
    state = code.phonology
    key = ("weakness", function)
    cached = state.cache.get(key)
    if cached is not None and cached[0] == state.version:
        return cast(float, cached[1])
    held = state.cache.get("weakness-index")
    index = cast(WeaknessIndex, held[1]) if held else WeaknessIndex()
    state.cache["weakness-index"] = (state.version, index)
    index.sync(world, code)
    value = index.value((entry.word_class, entry.cell)) if entry.word_class is not None else 1.0
    state.cache[key] = (state.version, value)
    return value


def particle_form(world: World, code: Code, concept: str | None) -> Form:
    if concept is None:
        return ()
    root = code.phonology.dominant.get(concept)
    return world.form_of(code, root) if root is not None else ()


def eroded(world: World, code: Code, concept: str | None) -> bool:
    """Ztratilo slovo pro pojem zvukovými změnami hlásky? Krátké odjakživa není slabé."""
    if concept is None:
        return True
    root = code.phonology.dominant.get(concept)
    if root is None:
        return True
    return len(world.form_of(code, root)) < len(world.morphemes[root].form)


def strength(
    world: World, code: Code, construction: Construction, group_id: str | None = None
) -> float:
    """Jak zřetelně konstrukce svou funkci vyjadřuje (0 až 1).

    U nevyjádřené funkce (``zero``) odráží síla míru, do jaké funkci
    zastoupí kontext a kompenzující strategie (C2; Dryer 2013, Dahl 1985).
    """
    kind = construction.kind
    if kind == "periphrastic":
        return 1.0
    if kind == "synthetic":
        if construction.exponent is not None and not applied(code, world, construction):
            # Nová koncovka, kterou jazyk ještě nezapsal: zní, jak zněla
            # přiklonka (plně), nebo jako zbytková koncovka dárce.
            if construction.donor is None:
                return 1.0
            return 1.0 - weakness(world, code, construction.donor)
        return 1.0 - weakness(world, code, construction.function)
    if kind in ("pre", "embraced", "post"):
        # Zápor je tak výrazný, jak silné je jeho nejsilnější slovo.
        words = (construction.source, construction.reinforcer)
        return 1.0 if any(not eroded(world, code, word) for word in words if word) else 0.0
    if kind == "zero":
        entry = catalog_for(world).get(construction.function)
        ctx = entry.context if entry is not None else 0.0
        comp = compensation(world, group_id, construction.function) if group_id is not None else 0.0
        return max(ctx, comp)
    return 0.0  # free, fixed


def applied(code: Code, world: World, construction: Construction) -> bool:
    variant = stable_id("variant", "construction", construction.key)
    return variant in code.phonology.grammar_applied


def carries_role(world: World, construction: Construction) -> bool:
    """Nese konstrukce roli funkcí, které její funkce zastupuje (``compensates``)?

    Slovosled ji nese jen pevný; ostatní funkce, když se vůbec vyjadřují.
    """
    entry = catalog_for(world).get(construction.function)
    if entry is not None and entry.template == "order":
        return construction.carries_order
    return construction.kind != "zero"


def compensation(world: World, group_id: str, function: str) -> float:
    """Jakou měrou roli funkce přebírají jiné dominantní konstrukce (0 až 1).

    Zástupce nese ``coverage`` z katalogu (pevný slovosled pád 0,9, vid minulý
    čas), když ve skupině převažuje konstrukce, která roli nese.
    """
    found = 0.0
    for entry in catalog_for(world).values():
        if function in entry.compensates:
            current = dominant(world, group_id, entry.id)
            if current is not None and carries_role(world, current):
                found = max(found, entry.coverage)
    return found


def compensated(world: World, group_id: str, function: str) -> bool:
    """Převzala roli funkce jiná konstrukce (např. pevný slovosled roli pádu)?"""
    return compensation(world, group_id, function) > 0.0


def residual_exponent(world: World, code: Code, donor: GrammaticalFunction) -> str | None:
    """Koncovka dárcovské buňky, která ještě zní (je co převzít)."""
    from cee.v2.morphology import class_stats

    if donor.word_class is None or donor.cell is None:
        return None
    stats = class_stats(world, code)
    exponent = stats.productive(donor.word_class, donor.cell)
    if exponent is None or not stats.endings.get(exponent):
        return None
    return exponent


def new_affix(world: World, code: Code, construction: Construction, group_id: str, tick: int) -> str | None:
    """Koncovka z pomocného slova: srůstáním se zkrátí na první slabiku.

    Gramatikalizace jde ruku v ruce s fonetickou redukcí (Bybee): z celého
    slova zbude jeho začátek, nejvýš souhláska a samohláska.
    """
    assert world.table is not None
    entry = catalog_for(world)[construction.function]
    form = particle_form(world, code, construction.source)
    vowels = [index for index, segment in enumerate(form) if world.table.is_vowel(segment)]
    if not vowels or entry.cell is None:
        return None
    reduced = form[: vowels[0] + 1]
    affix = stable_id("affix", "grammaticalized", construction.function, group_id, tick, reduced)
    if affix not in world.morphemes:
        world.morphemes[affix] = Morpheme(
            affix, f"{entry.word_class}.{entry.cell}", reduced, kind="affix",
            word_class=entry.word_class, cell=entry.cell, origin_group=group_id, origin_tick=tick,
            etymology="grammaticalization", sources=(construction.source or "",),
            language=code.language,
        )
    return affix


def _ensure_cell(world: World, entry: GrammaticalFunction) -> None:
    """Buňka paradigmatu vznikne, až ji jazyk poprvé vyjádří koncovkou."""
    assert entry.word_class is not None and entry.cell is not None
    paradigm = world.paradigms[entry.word_class]
    if entry.cell not in paradigm.cells:
        world.paradigms[entry.word_class] = replace(
            paradigm, cells=(*paradigm.cells, entry.cell), weights=(*paradigm.weights, entry.weight)
        )


def restructure(world: World, group_id: str, tick: int, history: History, year: float) -> None:
    """Nová syntetická konstrukce, která převážila, se zapíše do tvarů slov."""
    from cee.v2.morphology import citation_form
    from cee.v2.phonology import enter_vocabulary, requeue_all

    code = world.groups[group_id].main_code
    state = code.phonology
    for entry in functions(world, "inflection"):
        distribution = world.distribution(group_id, variable_id(entry.id))
        if distribution is None or entry.word_class not in world.paradigms:
            continue
        variant, share = distribution.dominant()
        construction = construction_of(world, variant)
        if (
            share < world.params.grammar_threshold or construction.kind != "synthetic"
            or construction.exponent is None or variant in state.grammar_applied
        ):
            continue
        state.mark_grammar_applied(variant)
        _ensure_cell(world, entry)
        paradigm = world.paradigms[entry.word_class]
        donor = catalog_for(world)[construction.donor] if construction.donor else None
        ending = world.morphemes[construction.exponent].form
        rewritten = kept = 0
        roots = sorted({
            world.morphemes[unit].lexeme_id for unit in state.vocabulary
            if world.morphemes[unit].kind in ("root", "word")
            and world.morphemes[unit].word_class == entry.word_class
        })
        for root in roots:
            unit = unit_id(root, entry.cell or "", paradigm)
            exists = unit in state.vocabulary
            if donor is not None:
                # Exaptace: tvar dárcovské buňky s touto koncovkou dostane novou funkci.
                donor_unit = unit_id(root, donor.cell or "", paradigm)
                if donor_unit not in state.vocabulary:
                    continue
                new = world.unit_of(code, donor_unit)
                if new.exponent != construction.exponent:
                    continue
            elif exists and world.usage_frequency(code, root) >= world.params.conserved_frequency:
                # Velmi častá slova si starý tvar ponechají (silná slovesa vedle
                # nové pravidelné koncovky, angl. *sang* vedle *walked*).
                kept += 1
                continue
            else:
                citation = citation_form(world, code, root)
                new = UnitForm(citation + ending, len(citation), construction.exponent)
            if unit not in world.morphemes:
                lexeme = world.morphemes[root]
                world.morphemes[unit] = Morpheme(
                    id=unit, meaning=lexeme.meaning, form=new.form,
                    frequency=lexeme.frequency * entry.weight, kind="word",
                    word_class=entry.word_class, lexeme=root, cell=entry.cell,
                    exponent=new.exponent, boundary=new.boundary,
                    origin_group=group_id, origin_tick=tick, language=lexeme.language,
                )
            code.forms.set(unit, new)
            rewritten += 1
            if exists:
                requeue_all(world, code, unit)
            else:
                enter_vocabulary(world, code, unit)
        state.version += 1
        history.record(
            "exapted" if donor is not None else "grammaticalized", tick, year,
            group=group_id, function=entry.id, source=construction.source,
            donor=construction.donor, words=rewritten, kept=kept,
        )
