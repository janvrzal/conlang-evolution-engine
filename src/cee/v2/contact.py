"""Kontakt jazyků (iterace 3, oblast E, a iterace 4; milník M5).

Kontakt nemá vlastní mechanismus šíření. Varianta jiného jazyka vstupuje do
proměnné stejně jako varianta sousedního dialektu, jen přes dva filtry
přenositelnosti (Thomason & Kaufman 1988):

- **Výpůjčka** (mluvčí si drží svůj jazyk a přejímají z cizího): nejsnáz
  slova, a to spíš vzácná než základní (Haspelmath & Tadmor 2009); stavba
  jazyka jen výjimečně.
- **Interference** (dospělí se učí cizí kód a nesou do něj svůj první
  jazyk): naopak hlavně výslovnost a konstrukce, slov málo.

Vícejazyčná komunita je v simulaci víc skupin (jedna na kód) se společným
``community``. Přechod na jiný jazyk je přesun mluvčích mezi nimi podle
modelu Abramse a Strogatze (2003); kód, kterému se přestanou učit děti,
vymře a v novém jazyce po něm zůstane substrát.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Sequence

import numpy as np
import numpy.typing as npt

from cee.v2.history import History
from cee.v2.language.segments import Form

if TYPE_CHECKING:
    from cee.v2.parameters import Parameters
    from cee.v2.world import Code, World

FloatArray = npt.NDArray[np.float64]

#: Filtr výpůjček podle typu proměnné. U slov se násobí váhou pojmu
#: (:func:`transfer`, dřív ``1 − frekvence``: základní slovní zásoba se půjčuje
#: nejméně) a váhou domény pojmu v kanálu (:func:`domain_weight`).
BORROWING = {"lexical": 0.5, "process": 0.1, "construction": 0.1, "form": 0.0}
#: Filtr interference při osvojování druhého jazyka.
INTERFERENCE = {"lexical": 0.05, "process": 1.0, "construction": 1.0, "form": 0.0}
# Váhy interference, rychlost přechodu a práh předávání dětem jsou data světa
# (``world.params``: ``interference_weight``, ``school_correction``,
# ``shift_rate``, ``shift_exponent``, ``child_threshold``).
#: Skupina s menší populací zaniká (poslední mluvčí).
LAST_SPEAKERS = 1.0


#: Půjčitelnost pod touto hodnotou se bere jako tato hodnota: slovo, které WOLD nikde
#: nenašla přejaté (*this*, *we*), se v modelu nepůjčuje skoro, ale ne nikdy.
BORROWED_FLOOR = 0.01


@lru_cache(maxsize=1)
def reference() -> float:
    """Průměrná půjčitelnost výchozích 149 pojmů z dat (kotva ``Parameters.borrowability_strength``)."""
    from cee.v2 import concept_data

    scores = [float(entry["borrowed"]) for entry in concept_data.data()["concepts"].values()
              if entry["borrowed"] is not None]
    return sum(scores) / len(scores)


@lru_cache(maxsize=32)
def _normalizer(strength: float) -> float:
    """Průměr váhy pojmu (bez normalizace) přes výchozích 149 pojmů vůči průměru ``1 − frekvence``.

    Díky tomu ``s`` nezmění průměrnou míru výpůjček výchozího slovníku.
    """
    from cee.v2 import concept_data

    mean = reference()
    rarity = [1.0 - float(concept_data.frequency(concept) or 0.0) for concept in concept_data.data()["concepts"]]
    values = [
        (1.0 - float(concept_data.frequency(concept) or 0.0)) ** max(0.0, 1.0 - strength)
        * (max(float(entry["borrowed"]), BORROWED_FLOOR) / mean) ** strength
        for concept, entry in concept_data.data()["concepts"].items() if entry["borrowed"] is not None
    ]
    return (sum(values) / len(values)) / (sum(rarity) / len(rarity))


def transfer(world: World, concept: str) -> float:
    """Váha pojmu při přenosu slova z cizího kódu (vazby mezi jazyky), bez kanálu a domény.

    Dřív ``1 − frekvence``: základní slovní zásoba se půjčuje nejméně. S
    ``Parameters.borrowability_strength`` *s* je to
    ``(1 − frekvence) ** max(0, 1 − s) · (půjčitelnost / průměr) ** s``, přepočtené
    tak, aby měly přes výchozích 149 pojmů stejný průměr jako ``1 − frekvence``
    (průměrná míra výpůjček se nemění). Půjčitelnost je ze WOLD (``concept_data.borrowed``) a frekvenci
    částečně obsahuje: v datech s ní nekoreluje (Spearman −0,05 přes katalog)
    a engine ji uplatní zažitostí slova (``Entrenchment``), proto s ``s`` ≥ 1
    z váhy vypadne. ``s`` nad 1 zvýrazní rozdíly mezi pojmy.
    """
    rarity = 1.0 - world.concept_frequency(concept)
    strength = world.params.borrowability_strength
    if strength == 0.0:
        return rarity
    borrowed = max(world.concept_traits(concept)[1], BORROWED_FLOOR)
    weight = (borrowed / reference()) ** strength
    if strength < 1.0:
        weight *= rarity ** (1.0 - strength)
    return weight / _normalizer(strength)


def domain_weight(world: World, channel: str, concept: str) -> float:
    """Váha domény pojmu v kanálu (``Parameters.channel_domains``)."""
    return float(world.params.channel_domains[channel][world.concept_traits(concept)[0]])


def borrowing_factor(world: World, variable_id: str, channel: str = "neighbor") -> float:
    variable = world.variables[variable_id]
    factor = BORROWING.get(variable.kind, 0.0)
    if variable.kind == "lexical":
        factor *= transfer(world, variable.key)
        weight = domain_weight(world, channel, variable.key)
        if weight != 1.0:
            factor *= weight
    return factor


# --- kanály vazeb mezi jazyky ---------------------------------------------------

#: Kanály, které se v přenosu odlišují od obecného kontaktu sousedů (pořadí je pevné).
FLOW_CHANNELS = ("elite", "trade")


def distinct_channels(params: Parameters) -> tuple[str, ...]:
    """Kanály vazeb mezi jazyky s jinými vahami domén než obecný kontakt sousedů.

    Jen ty se v přenosu počítají zvlášť; kanál s týmiž vahami splyne se sousedy
    (výsledek je pak bitově stejný jako bez kanálů).
    """
    table = params.channel_domains
    base = dict(table["neighbor"])
    return tuple(channel for channel in FLOW_CHANNELS if dict(table[channel]) != base)


def channel_shares(
    world: World, group_ids: Sequence[str], distinct: Sequence[str]
) -> dict[str, FloatArray]:
    """Podíl vazby (učící se skupina × zdroj), který patří kanálu ``elite`` a ``trade``.

    Zdroj-elita (``SpeechGroup.elite``) je celý kanál ``elite``. Z ostatních vazeb
    patří kanálu ``trade`` podíl síly, který přinesla obchodní cesta
    (:meth:`cee.v2.world.World.trade_share`). Zbytek je kanál ``neighbor``.
    """
    size = len(group_ids)
    shares: dict[str, FloatArray] = {}
    elite = np.zeros((size, size))
    if "elite" in distinct:
        sources = np.array([world.groups[group_id].elite for group_id in group_ids])
        elite = np.broadcast_to(np.where(sources, 1.0, 0.0), (size, size)).copy()
        shares["elite"] = elite
    if "trade" in distinct and world.trade:
        place = {group_id: position for position, group_id in enumerate(group_ids)}
        trade = np.zeros((size, size))
        for first, second in sorted(world.trade):
            if first in place and second in place:
                trade[place[first], place[second]] = world.trade_share(first, second)
                trade[place[second], place[first]] = world.trade_share(second, first)
        shares["trade"] = trade * (1.0 - elite)
    return shares


def donor_channels(world: World, group_id: str, donor_id: str, distinct: Sequence[str]) -> list[tuple[str, float]]:
    """Kanály, kterými slova od dárce přicházejí, a jejich podíl (součet 1)."""
    if "elite" in distinct and world.groups[donor_id].elite:
        return [("elite", 1.0)]
    share = world.trade_share(group_id, donor_id) if "trade" in distinct else 0.0
    if share > 0.0:
        return [("neighbor", 1.0 - share), ("trade", share)] if share < 1.0 else [("trade", 1.0)]
    return [("neighbor", 1.0)]


def interference_factor(world: World, variable_id: str) -> float:
    return INTERFERENCE.get(world.variables[variable_id].kind, 0.0)


def language_of(world: World, group_id: str) -> str:
    return world.groups[group_id].main_code.language


# --- adaptace výpůjček ----------------------------------------------------


def inventory(world: World, code: Code) -> tuple[int, ...]:
    """Hlásky, které kód ve slovní zásobě užívá (seřazené).

    Čte je z průběžného indexu prostředí hlásek (``ContextIndex``), který
    dorovná jen změněná slova; dřív se inventář stavěl z celé slovní zásoby
    po každé změně slova, tedy při každé výpůjčce.
    """
    from typing import cast

    from cee.v2.language.index import ContextIndex

    state = code.phonology
    if world.table is None:
        return tuple(sorted({segment for unit in state.vocabulary for segment in world.form_of(code, unit)}))
    holder = state.cache.get("context-index")
    if holder is None:
        holder = state.cache["context-index"] = (0, ContextIndex())
    contexts = cast(ContextIndex, holder[1])
    contexts.sync(world, code)
    return contexts.inventory()


def adapt(world: World, code: Code, form: Form) -> Form:
    """Cizí hlásky se nahradí nejbližší hláskou příjemce (podle rysů PanPhonu)."""
    assert world.table is not None
    native = inventory(world, code)
    if not native:
        return form
    if all(segment in native for segment in form):
        return form
    table = world.table
    vectors = table.vectors
    pool = np.array(native)
    pool_vowels = np.array([table.is_vowel(int(other)) for other in pool])
    known = set(native)
    result = []
    for segment in form:
        if segment in known:
            result.append(segment)
            continue
        distance = (vectors[pool] != vectors[segment]).sum(axis=1)
        # Samohláska zůstane samohláskou, souhláska souhláskou.
        same = pool_vowels == table.is_vowel(segment)
        distance = np.where(same, distance, distance + 1000)
        result.append(int(pool[int(np.argmin(distance))]))
    return tuple(result)


def donor_form(world: World, group_id: str, morpheme_id: str) -> Form:
    """Tvar slova u nejbližšího mluvčího jeho jazyka, jak ho skupina slyší."""
    language = world.morphemes[morpheme_id].language
    group = world.groups[group_id]
    candidates = [(link.strength, link.target) for link in world.neighbors(group_id)]
    for source in (group.main_code.l1_source, group.standard, group.liturgy):
        if source in world.groups:
            candidates.append((1.0, source))
    for _, donor in sorted(candidates, key=lambda item: (-item[0], item[1])):
        code = world.groups[donor].main_code
        if code.language == language and morpheme_id in code.phonology.vocabulary:
            return world.form_of(code, morpheme_id)
    return world.morphemes[morpheme_id].form


def adopt(world: World, group_id: str, morpheme_id: str) -> None:
    """Cizí kořen vstupuje do slovní zásoby: převezme a adaptuje jeho tvar.

    Tvary buněk paradigmatu pak dostane výpůjčka podle produktivních koncovek
    příjemce (:func:`cee.v2.morphology.units_of`), jak to dělají reálné
    jazyky (*pizza → pizzy*).
    """
    code = world.groups[group_id].main_code
    morpheme = world.morphemes[morpheme_id]
    if morpheme.language == code.language or code.forms.get(morpheme_id) is not None:
        return
    from cee.v2.language.lexicon import UnitForm

    code.forms.set(morpheme_id, UnitForm(adapt(world, code, donor_form(world, group_id, morpheme_id)), None, None))


# --- komunity: migrace, přistěhovalectví a přechod na jiný jazyk ------------


def community_step(world: World, dt: float, tick: int, year: float, history: History) -> bool:
    """Jeden krok demografie kódů; vrací ``True``, když nějaká skupina zanikla nebo vznikla."""
    if world.migration > 0:
        _migrate(world, dt)
    removed = False
    for group_id in world.group_ids():
        if group_id not in world.groups:
            continue
        group = world.groups[group_id]
        if group.written:
            continue
        code = group.main_code
        renewal = min(1.0, dt / group.generation_years)
        source = code.l1_source if code.l1_source in world.groups else None
        if group.domain == "public":
            # Veřejný kód se každá generace učí znovu v dospělosti.
            code.l2_share = 1.0
            if group.home_pull > 0 and source is not None:
                removed |= _nativize(world, group_id, source, renewal, tick, year, history)
            continue
        if source is None:
            # Stárnoucí L2 mluvčí nahradí děti, které se kód učí od narození;
            # přistěhovalci podíl drží.
            code.l2_share += renewal * (group.immigration - code.l2_share)
            continue
        removed |= _shift(world, group_id, source, renewal, tick, year, history)
    return removed


def _migrate(world: World, dt: float) -> None:
    """Gravitační migrace: podíl přistěhovalců každé skupiny za generaci.

    Ze skupiny odchází podíl ``world.migration`` lidí za generaci k
    sousedům, úměrně síle vazby, velikosti a prestiži cíle (Ravenstein 1885;
    města přitahují). Populace se nemění: úbytek doplní přirozený přírůstek.
    Přistěhovalci se místní řeč učí v dospělosti (Trudgill: koineizace).
    """
    inflow = {group_id: 0.0 for group_id in world.groups}
    for group_id in world.group_ids():
        group = world.groups[group_id]
        if group.written or group.domain == "public":
            continue
        targets = [
            (link.target, link.strength * world.groups[link.target].population * world.groups[link.target].prestige)
            for link in world.neighbors(group_id)
            if not world.groups[link.target].written and world.groups[link.target].domain == "home"
        ]
        total = sum(weight for _, weight in targets)
        if total <= 0:
            continue
        leaving = world.migration * group.population
        for target, weight in targets:
            inflow[target] += leaving * weight / total
    for group_id, arriving in sorted(inflow.items()):
        group = world.groups[group_id]
        if not group.written and group.domain == "home":
            group.immigration = min(1.0, arriving / group.population)


def demographic_share(world: World, source_id: str, target_id: str) -> float:
    """Podíl mluvčích cílového jazyka mezi lidmi, se kterými komunita mluví.

    Počítá se komunita sama a její sousedé vážení silou vazby. Elita uprostřed
    poddaných tak slyší jazyk většiny, i když ho v ní zatím mluví málokdo.
    """
    language = world.groups[target_id].main_code.language
    weights = [(1.0, source_id), (1.0, target_id)]
    for member in (source_id, target_id):
        weights += [(link.strength, link.target) for link in world.neighbors(member)
                    if link.target not in (source_id, target_id)]
    speakers = total = 0.0
    seen: set[str] = set()
    for weight, group_id in sorted(weights, key=lambda item: (item[1], -item[0])):
        if group_id in seen or world.groups[group_id].written:
            continue
        seen.add(group_id)
        people = weight * world.groups[group_id].population
        total += people
        if world.groups[group_id].main_code.language == language:
            speakers += people
    return speakers / total if total else 0.0


def own_schooling(world: World, group_id: str) -> float:
    """Školní docházka skupiny v jejím vlastním jazyce (0, když škola učí cizí normu)."""
    group = world.groups[group_id]
    standard = world.groups.get(group.standard) if group.standard is not None else None
    if standard is None or standard.main_code.language != group.main_code.language:
        return 0.0
    return group.schooling


def _nativize(
    world: World, public_id: str, home_id: str, renewal: float, tick: int, year: float, history: History
) -> bool:
    """Veřejný kód proniká domů: dvojjazyčné rodiny s ním vychovávají děti.

    Za generaci přejde podíl ``home_pull × status × dvojjazyčnost^1,31``
    domácnosti (jako u přechodu, Abrams & Strogatz 2003), zpomalený loajalitou
    komunity a školou ve vlastním jazyce. Přešlé rodiny tvoří domácí skupinu cílového jazyka, kterou pak
    dál vede :func:`_shift`: jestli starý jazyk vymře, rozhodne místní
    demografie a loajalita, ne politika sama. Přiblížení, ne model rodin.
    """
    params = world.params
    public, home = world.groups[public_id], world.groups[home_id]
    if home.preserved:
        return False
    status = public.prestige / (public.prestige + home.prestige)
    bilingual = min(1.0, public.population / home.population)
    moving = (
        home.population * renewal * params.shift_rate * public.home_pull * (1.0 - home.loyalty) * status
        * bilingual**params.shift_exponent * (1.0 - own_schooling(world, home_id))
    )
    moving = min(moving, home.population - 1.0)
    language = public.main_code.language
    community = home.community or home.id
    # Domácí skupina cílového jazyka v komunitě vzniká jen jako přechod
    # (``LanguageShift``, ID ``home>jazyk``) nebo pronikáním domů (``:home``).
    existing = [
        other for other in (f"{home_id}>{language}", f"{home_id}>{language}:home")
        if other in world.groups
        and world.groups[other].community == community and world.groups[other].domain == "home"
        and world.groups[other].main_code.language == language and world.groups[other].main_code.l1_source == home_id
    ]
    if existing:
        target = world.groups[existing[0]]
        target.population = max(1, round(target.population + moving))
        home.population = max(1, round(home.population - moving))
        return False
    if moving < LAST_SPEAKERS:
        return False
    world.materialize(public_id)
    code = public.main_code.branch()
    code.acquisition, code.l1_source, code.l2_share = "L2", home_id, 1.0
    from cee.v2.world import SpeechGroup

    created = world.add_group(SpeechGroup(
        id=f"{home_id}>{language}:home", territory=home.territory, population=max(1, round(moving)),
        codes=[code], generation_years=home.generation_years, prestige=public.prestige,
        openness=public.openness, community=community, loyalty=home.loyalty, home_pull=public.home_pull,
        standard=public.standard, literacy=public.literacy, schooling=public.schooling,
    ))
    home.population = max(1, round(home.population - moving))
    for link in world.neighbors(public_id):
        if link.target != home_id:
            world.connect(created.id, link.target, link.strength, link.kind)
            # Vazba převzala sílu oslabenou hranicí; zapamatuje si i násobek.
            factor = world.border_factors.get((public_id, link.target))
            if factor is not None:
                world.border_factors[(created.id, link.target)] = factor
                world.border_factors[(link.target, created.id)] = factor
    if public_id in world.prestige_mirror:
        world.prestige_mirror[created.id] = world.prestige_mirror[public_id]
    world.connect(created.id, public_id, 0.8, "strong")
    world.connect(created.id, home_id, 0.8, "strong")
    history.record("nativization", tick, year, group=home_id, into=created.id, language=language,
                   population=created.population)
    return True


def _shift(
    world: World, target_id: str, source_id: str, renewal: float, tick: int, year: float, history: History
) -> bool:
    """Mluvčí skupiny ``source`` přecházejí na kód skupiny ``target``.

    Abrams & Strogatz (2003): za generaci přejde podíl ``status ×
    podíl^1,31``, kde status plyne z prestiže a podíl je demografie
    (:func:`demographic_share`). Loajalita komunity přechod zpomalí.

    Přechod, který začal tlakem státu nebo obrozením (``home_pull`` > 0), je
    obousměrný jako u Abramse a Strogatze: rodiny se vracejí ke starému
    jazyku podle jeho statusu a demografie, tempem obrozeneckého hnutí
    (``revival``) a školy ve vlastním jazyce. Jazyk s takovou oporou si děti
    předávají dál i pod prahem užívání.
    """
    params = world.params
    source, target = world.groups[source_id], world.groups[target_id]
    total = source.population + target.population
    status = target.prestige / (target.prestige + source.prestige)
    driven = target.home_pull > 0
    resist = min(1.0, source.revival + own_schooling(world, source_id)) if driven else 0.0
    moving = births = back = 0.0
    if not source.preserved:
        share = demographic_share(world, source_id, target_id)
        # Přechod, který začal tlakem státu (``_nativize``) nebo obrozením, jde
        # tempem politiky či hnutí: jejich uvolnění ho zpomalí. Škola ve vlastním
        # jazyce ho brzdí, škola v cílovém jazyce urychlí.
        pace = (target.home_pull * (1.0 - own_schooling(world, source_id))
                * (1.0 + own_schooling(world, target_id))) if driven else 1.0
        # Loajalita brzdí odchod od jazyka, ne návrat k němu (obrozený kód).
        brake = 1.0 - source.loyalty if target.revival == 0.0 else 1.0
        moving = (
            source.population * renewal * params.shift_rate * pace * brake * status
            * share**params.shift_exponent
        )
        if source.population / total < params.child_threshold and resist == 0.0:
            # Děti se starý kód už neučí: rodí se do nového.
            if source.transmitted:
                source.transmitted = False
                history.record("transmission_stopped", tick, year, group=source_id,
                               language=source.main_code.language)
            births = source.population * renewal
        moving = min(moving, source.population - births)
    if resist > 0.0:
        if not source.transmitted:
            source.transmitted = True
            history.record("transmission_resumed", tick, year, group=source_id, language=source.main_code.language)
        back = (
            target.population * renewal * params.shift_rate * resist * (1.0 - status)
            * demographic_share(world, target_id, source_id)**params.shift_exponent
        )
        back = min(back, target.population + moving + births)
    learners = target.main_code.l2_share * target.population * (1.0 - renewal) + moving
    remaining = source.population - moving - births + back
    target_population = target.population + moving + births - back
    if target_population < LAST_SPEAKERS:
        # Všichni se vrátili ke starému jazyku.
        source.population = max(1, round(remaining + target_population))
        world.materialize(target_id)
        world.remove_group(target_id)
        history.record("revival", tick, year, group=source_id, left=target_id,
                       language=source.main_code.language, from_language=target.main_code.language)
        return True
    target.main_code.l2_share = min(1.0, learners / target_population)
    target.population = max(1, round(target_population))
    if remaining < LAST_SPEAKERS:
        world.materialize(source_id)
        world.remove_group(source_id)
        # Veřejná dvojjazyčnost zaniká se starým jazykem: jeho mluvčí už
        # cílový kód mají doma.
        for other in world.group_ids():
            peer = world.groups[other]
            if peer.domain == "public" and peer.main_code.l1_source == source_id and peer.home_pull > 0:
                world.remove_group(other)
        target.main_code.l1_source = None
        # Komunita už mluví novým kódem od dětství: je to zase obyčejná
        # skupina se svou dřívější otevřeností.
        target.openness = source.openness
        history.record(
            "language_shift", tick, year, group=source_id, into=target_id,
            language=source.main_code.language, target_language=target.main_code.language,
        )
        return True
    source.population = max(1, round(remaining))
    return False
