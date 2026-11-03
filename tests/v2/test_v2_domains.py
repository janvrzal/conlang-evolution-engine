"""Domény slov v kanálech kontaktu (krok 3 plánu pojmů): váhy, kanály, neutralita."""

from __future__ import annotations

import dataclasses
import pickle

import numpy as np
import pytest

from cee.v2 import contact, institutions
from cee.v2.background import EliteAssimilation, ForeignElite, TradeShift, generate
from cee.v2.events import Codification, Conquest, Contact, ReligiousChange, Schooling
from cee.v2.history import History
from cee.v2.parameters import DEFAULT_CHANNEL_DOMAINS, NEUTRAL_CHANNEL_DOMAINS, Parameters
from cee.v2.scenarios import (
    Language,
    Place,
    ProtoLanguage,
    Region,
    contact_world,
    language_shift,
    region_world,
)
from cee.v2.simulation import Simulation
from cee.v2.transmission import TransmissionParams, prepare

NEUTRAL = Parameters(channel_domains=NEUTRAL_CHANNEL_DOMAINS, borrowability_strength=0.0)

# Otisky dnešního modelu (před zavedením domén), pořízené na stavu před změnou.
TRADE_ELITE_DIGEST = "ea7455be5a7efc486b8faff47b2b9f159f0e921da14466266a2a084c76c82af4"
CHURCH_SCHOOL_DIGEST = "2d5f3b8fe07232dc586b3b32a130724ca9e5108b70dd539216f14367ad7753af"
SHIFT_DIGEST = "f74dad095fcbaa129349dddd4ed74da4c3d1ced888dfe2ed81bc692212612559"


def _regions():
    return tuple(
        Region(f"r{i}", (60.0 * (i % 3), 60.0 * (i // 3)), language="b" if i >= 3 else "a", villages=2,
               neighbours=tuple(f"r{j}" for j in range(6)
                                if j != i and abs(j % 3 - i % 3) + abs(j // 3 - i // 3) == 1))
        for i in range(6)
    )


def trade_elite_world(params: Parameters):
    regions = _regions()
    world = region_world(regions, seed=3, languages=(ProtoLanguage("a"), ProtoLanguage("b")), semantics=True,
                         params=params)
    events = list(generate([(r.id, r.neighbours, r.language) for r in regions], start=0.0, end=600.0,
                           level_name="turbulent", seed=3, params=params))
    events += [ForeignElite(50.0, "r3", "r0"), TradeShift(60.0, ("r1", "r4"), 2.0),
               TradeShift(300.0, ("r1", "r4"), 0.5), EliteAssimilation(300.0, "r3", "r0")]
    return world, events


def church_school_world(params: Parameters):
    world = contact_world([
        Language("v", tuple(Place(f"v{i}", (i * 10.0, 0.0), population=600) for i in range(4))),
        Language("r", (Place("r0", (500.0, 0.0), population=5000, prestige=1.0),),
                 consonants=("t", "k", "s", "n", "m", "l", "r", "f", "x", "kʷ", "j", "d")),
    ], seed=2, params=params)
    villages = tuple(f"v{i}" for i in range(4))
    events = [Codification(100.0, "r0", ("r0",), 0.1), ReligiousChange(150.0, "written:r0", villages, 0.3),
              Codification(200.0, "v1", villages, 0.2), Schooling(400.0, villages, 0.5, 0.5)]
    return world, events


def _digest(world, events, years):
    simulation = Simulation(world, events=events)
    simulation.run(years)
    return simulation.history.digest()


# --- neutralita -------------------------------------------------------------------


def test_neutralni_vahy_davaji_dnesni_otisky():
    """Domény 1 a půjčitelnost vypnutá: elita, obchod, liturgie, čtení a škola jako dřív."""
    assert _digest(*trade_elite_world(NEUTRAL), 600) == TRADE_ELITE_DIGEST
    assert _digest(*church_school_world(NEUTRAL), 800) == CHURCH_SCHOOL_DIGEST
    world, events = language_shift(2, start=300.0)
    world.params = NEUTRAL
    assert _digest(world, events, 900) == SHIFT_DIGEST


def test_vychozi_vahy_menni_svet_s_elitou_a_liturgii():
    assert _digest(*trade_elite_world(Parameters()), 600) != TRADE_ELITE_DIGEST
    assert _digest(*church_school_world(Parameters()), 800) != CHURCH_SCHOOL_DIGEST


# --- parametry --------------------------------------------------------------------


def test_vahy_domen_se_doplni_z_vychozich_a_neznamy_nazev_je_chyba():
    params = Parameters(channel_domains={"elite": {"power": 9.0}})
    assert params.channel_domains["elite"]["power"] == 9.0
    assert params.channel_domains["elite"]["core"] == DEFAULT_CHANNEL_DOMAINS["elite"]["core"]
    assert params.channel_domains["liturgy"]["religion"] == DEFAULT_CHANNEL_DOMAINS["liturgy"]["religion"]
    assert hash(params) == hash(Parameters(channel_domains={"elite": {"power": 9.0}}))
    assert dataclasses.replace(params, shift_rate=2.0).channel_domains == params.channel_domains
    with pytest.raises(ValueError, match="kanál"):
        Parameters(channel_domains={"posta": {"power": 2.0}})
    with pytest.raises(ValueError, match="doména"):
        Parameters(channel_domains={"elite": {"magic": 2.0}})
    with pytest.raises(ValueError, match="záporná"):
        Parameters(channel_domains={"elite": {"power": -1.0}})


def test_vychozi_kanaly_zvyhodnuji_svou_domenu():
    table = Parameters().channel_domains
    for channel, domain in (("elite", "power"), ("trade", "culture"), ("liturgy", "religion"),
                            ("reading", "learned"), ("school", "learned")):
        assert table[channel][domain] > 1.0
        assert all(table[channel][other] == 1.0 for other in table[channel] if other != domain)
    assert all(weight == 1.0 for weight in table["neighbor"].values())


# --- přenositelnost z půjčitelnosti --------------------------------------------------


def _pair(params):
    regions = (Region("p", (0.0, 0.0), language="a", villages=1, neighbours=("q",)),
               Region("q", (30.0, 0.0), language="b", villages=1, neighbours=("p",)))
    return region_world(regions, languages=(ProtoLanguage("a"), ProtoLanguage("b")), semantics=True, params=params)


def test_bez_pujcitelnosti_je_vaha_pojmu_dosavadni_vzacnost():
    world = _pair(NEUTRAL)
    for concept in ("water", "law", "this"):
        assert contact.transfer(world, concept) == 1.0 - world.concept_frequency(concept)
        assert contact.borrowing_factor(world, f"lexical:{concept}") == 0.5 * (1.0 - world.concept_frequency(concept))


def test_pujcitelnost_rozlisuje_pojmy_podle_wold_a_prumer_zustane():
    world = _pair(Parameters(borrowability_strength=1.0))
    assert contact.transfer(world, "law") > 3 * contact.transfer(world, "tongue")
    assert contact.transfer(world, "this") < 0.2 * contact.transfer(world, "tongue")
    # Průměr přes výchozí pojmy se silou nemění (normalizace).
    from cee.v2 import concept_data

    concepts = list(concept_data.data()["concepts"])
    plain = _pair(NEUTRAL)
    mean_plain = np.mean([contact.transfer(plain, c) for c in concepts])
    for strength in (1.0, 3.0):
        world = _pair(Parameters(borrowability_strength=strength))
        assert np.mean([contact.transfer(world, c) for c in concepts]) == pytest.approx(mean_plain, rel=0.0, abs=0.03)


def test_domena_vlastniho_pojmu_autora_ridi_vahu_kanalu():
    from cee.v2 import vocabulary as vocab

    custom = vocab.resolve(149, [vocab.CustomConcept("regent", domain="power", borrowed=0.5)])
    regions = (Region("p", (0.0, 0.0), language="a", villages=1, neighbours=("q",)),
               Region("q", (30.0, 0.0), language="b", villages=1, neighbours=("p",)))
    world = region_world(regions, languages=(ProtoLanguage("a"), ProtoLanguage("b")), semantics=True,
                         vocabulary=custom)
    assert world.concept_traits("regent") == ("power", 0.5)
    assert contact.domain_weight(world, "elite", "regent") == DEFAULT_CHANNEL_DOMAINS["elite"]["power"]
    assert contact.domain_weight(world, "elite", "water") == 1.0


def test_liturgie_a_cteni_podle_domeny():
    world = _pair(Parameters(borrowability_strength=0.0))
    god = "lexical:god"
    assert world.concept_traits("god")[0] == "religion"
    weight = DEFAULT_CHANNEL_DOMAINS["liturgy"]["religion"]
    assert institutions.liturgy_factor(world, god) == pytest.approx(weight * (1.0 - world.concept_frequency("god")))
    assert institutions.liturgy_factor(world, "lexical:water") == 1.0 - world.concept_frequency("water")
    assert institutions.liturgy_factor(world, "construction:NEG") == 0.0
    learned = next(c for c in world.concept_frequencies if world.concept_traits(c)[0] == "learned")
    reading = institutions.reading_factor(world, f"lexical:{learned}")
    assert reading == pytest.approx(
        DEFAULT_CHANNEL_DOMAINS["reading"]["learned"]
        * (1.0 - world.params.reading_core_resistance * world.concept_frequency(learned)))
    assert institutions.school_factor(world, f"lexical:{learned}") == DEFAULT_CHANNEL_DOMAINS["school"]["learned"]


# --- kanály v přenosu ----------------------------------------------------------------


def _transmission(world, group_ids=None):
    params = TransmissionParams(dt=25.0, alpha=1.0, selection=1.0, kappa=0.0, sigma=0.0, adult_rate=0.5,
                                loss_threshold=0.0, establish_threshold=0.9)
    return prepare(world, group_ids or world.group_ids(), params, 1)


def test_elita_a_obchod_maji_vlastni_proud_jen_kdyz_se_vahy_lisi():
    world, events = trade_elite_world(Parameters())
    simulation = Simulation(world, events=events)
    simulation.run(75)
    inputs = _transmission(world)
    assert [flow.channel for flow in inputs.cross] == ["neighbor", "elite", "trade"]
    # Součet kanálů dá celé vazby mezi jazyky.
    neutral, neutral_events = trade_elite_world(NEUTRAL)
    simulation = Simulation(neutral, events=neutral_events)
    simulation.run(75)
    single = _transmission(neutral)
    assert [flow.channel for flow in single.cross] == ["neighbor"]
    for index in range(len(single.cross[0].blocks)):
        total = sum(flow.blocks[index] for flow in inputs.cross)
        assert total == pytest.approx(single.cross[0].blocks[index])


def test_conquest_znaci_elitu_a_vazba_od_elity_je_kanal_elite():
    world = _pair(Parameters())
    Conquest(0.0, "q-v0", "p-v0", ("p-v0",), population=50, prestige=2.0, strength=0.5).apply(world, History(), 0)
    elite = [g for g in world.group_ids() if world.groups[g].elite]
    assert elite == ["p-v0+q-v0"] and not world.groups["p-v0"].elite
    inputs = _transmission(world)
    by_name = {flow.channel: flow for flow in inputs.cross}
    ids = list(inputs.group_ids)
    learner, source = ids.index("p-v0"), ids.index("p-v0+q-v0")
    members = list(inputs.members[0])
    row, column = members.index(learner), members.index(source)
    assert by_name["elite"].blocks[0][row, column] > 0
    assert by_name["neighbor"].blocks[0][row, column] == 0


def test_obchodni_cesta_vznikne_a_upadne_beze_zbytku():
    world, _ = trade_elite_world(Parameters())
    pair = next(key for key in sorted(world.links) if {world.groups[key[0]].main_code.language,
                                                      world.groups[key[1]].main_code.language} == {"a", "b"}
                and key[0] < key[1])
    base = world.links[pair].strength
    assert world.trade_share(*pair) == 0.0
    region_a, region_b = (world.territories[world.groups[g].territory].parent for g in pair)
    TradeShift(1.0, (min(region_a, region_b), max(region_a, region_b)), 2.0).apply(world, History(), 1)
    assert world.trade_share(*pair) == pytest.approx(0.5)
    TradeShift(2.0, (min(region_a, region_b), max(region_a, region_b)), 0.5).apply(world, History(), 2)
    assert world.links[pair].strength == pytest.approx(base)
    assert world.trade_share(*pair) == 0.0


def test_contact_s_obchodem_je_cela_vazba_obchodni():
    world = _pair(Parameters())
    Contact(0.0, (("p-v0", "q-v0"),), 0.3, trade=True).apply(world, History(), 0)
    assert world.trade_share("p-v0", "q-v0") == 1.0 and world.trade_share("q-v0", "p-v0") == 1.0
    Contact(1.0, (("p-v0", "q-v0"),), 0.3).apply(world, History(), 1)
    assert world.trade_share("p-v0", "q-v0") == 0.0


def test_svet_s_elitou_a_obchodem_prezije_pickle():
    world, events = trade_elite_world(Parameters())
    simulation = Simulation(world, events=events)
    simulation.run(200)
    restored = pickle.loads(pickle.dumps(simulation))
    assert restored.world.trade == simulation.world.trade
    simulation.run(400)
    restored.run(400)
    assert restored.history.digest() == simulation.history.digest()
