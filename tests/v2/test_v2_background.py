"""Pozadí dějin (``cee.v2.background``): události, které svět generuje sám."""

from cee.v2.background import (
    ForeignElite,
    Plague,
    PrestigeShift,
    Recovery,
    Resettlement,
    TradeShift,
    generate,
)
from cee.v2.history import History
from cee.v2.polity import groups_in, region_of
from cee.v2.simulation import Simulation
from cee.v2.spec import build, check
from tests.v2.test_v2_spec import small

REGIONS = [("a", ["b"], "x"), ("b", ["a", "c"], "x"), ("c", ["b"], "y")]


def world():
    built, _, _ = build(small(events=[]))
    return built


def test_vychozi_svet_pozadi_nema():
    _, events, spec = build(small())
    assert spec.background == "none"
    assert len(events) == 1
    assert generate(REGIONS, start=0, end=1000, level_name="none", seed=1) == []


def test_generator_je_deterministicky_a_mira_ridi_cetnost():
    first = generate(REGIONS, start=0, end=2000, level_name="normal", seed=3)
    assert first == generate(REGIONS, start=0, end=2000, level_name="normal", seed=3)
    assert first != generate(REGIONS, start=0, end=2000, level_name="normal", seed=4)
    counts = {
        name: sum(len(generate(REGIONS, start=0, end=2000, level_name=name, seed=seed)) for seed in range(10))
        for name in ("calm", "normal", "turbulent")
    }
    assert counts["calm"] < counts["normal"] < counts["turbulent"]
    events = [event for seed in range(10) for event in generate(REGIONS, start=0, end=2000,
                                                                 level_name="turbulent", seed=seed)]
    assert all(0 < event.year < 2000 for event in events)
    # Cizí elitu dosadí jen soused jiného jazyka (b ↔ c).
    assert {(event.conqueror, event.region) for event in events if isinstance(event, ForeignElite)} <= {
        ("b", "c"), ("c", "b")}
    # Po moru přijde obnova, po vzestupu obchodu úpadek.
    assert any(isinstance(event, Recovery) for event in events)
    assert any(isinstance(event, TradeShift) and event.factor < 1 for event in events)


def test_neznama_mira_je_chyba_popisu():
    issues = {issue.path: issue.message for issue in check(small(background="apokalypsa"))}
    assert "turbulent" in issues["background"]


def test_mor_a_obnova():
    w = world()
    before = {g: w.groups[g].population for g in groups_in(w, ("c",))}
    history = History()
    Plague(25, ("c",), 0.5).apply(w, history, 1)
    assert all(w.groups[g].population < before[g] for g in before)
    assert all(w.groups[g].population == before[g] for g in groups_in(w, ("x",)) if g in before)
    Recovery(100, ("c",), 2.0).apply(w, history, 4)
    assert all(abs(w.groups[g].population - before[g]) <= 2 for g in before)
    assert [event["kind"] for event in history.events] == ["plague", "recovery"]
    assert all(event["background"] is True for event in history.events)


def test_presidleni_obchod_prestiz_a_cizi_elita():
    w = world()
    source = sum(w.groups[g].population for g in groups_in(w, ("c",)))
    Resettlement(25, "c", "x", 0.1).apply(w, History(), 1)
    assert sum(w.groups[g].population for g in groups_in(w, ("c",))) < source

    cross = sorted(key for key in w.links if {region_of(w, key[0]), region_of(w, key[1])} == {"c", "x"})
    assert cross
    strength = {key: w.links[key].strength for key in cross}
    TradeShift(50, ("c", "x"), 2.0).apply(w, History(), 2)
    assert all(w.links[key].strength >= strength[key] for key in cross)
    assert any(w.links[key].strength > strength[key] for key in cross)

    group = groups_in(w, ("x",))[0]
    base = w.base_prestige.get(group, w.groups[group].prestige)
    PrestigeShift(75, "x", 1.5).apply(w, History(), 3)
    assert w.base_prestige[group] == base * 1.5

    history = History()
    ForeignElite(100, "c", "x").apply(w, history, 4)
    ForeignElite(125, "c", "x").apply(w, history, 5)
    elites = [g for g in w.group_ids() if "+" in g]
    assert len(elites) == 1 and w.groups[elites[0]].main_code.language == "a"
    assert [event["kind"] for event in history.events] == ["foreign_elite"]


def test_beh_s_pozadim_zapise_udalosti_do_historie():
    w, events, _ = build(small(end_year=400, background="turbulent", seed=2))
    simulation = Simulation(w, events=events)
    simulation.run(400.0)
    recorded = [event for event in simulation.history.events if event.get("background")]
    assert recorded
    assert {event["kind"] for event in recorded} <= {
        "plague", "recovery", "resettlement", "trade", "prestige", "foreign_elite"}


def test_vypujcka_je_inovace_se_slovem_souseda_jineho_jazyka():
    import numpy as np

    from cee.v2.changes.base import InnovationContext
    from cee.v2.changes.lexicon import LexicalBorrowing
    from cee.v2.scenarios import ProtoLanguage, Region, region_world

    regions = (Region("p", (0.0, 0.0), language="a", villages=1, neighbours=("q",)),
               Region("q", (30.0, 0.0), language="b", villages=1, neighbours=("p",)))
    w = region_world(regions, languages=(ProtoLanguage("a"), ProtoLanguage("b")), semantics=True)
    change = LexicalBorrowing()
    home, donor = w.groups["p-v0"], "q-v0"
    context = InnovationContext(w, home, home.main_code, 1, 25.0)
    sites = change.sites(context)
    assert sites and change.total_rate(context) > 0
    # Základní slovo se půjčuje méně než vzácné (přenositelnost × 1 − frekvence).
    rates = dict(zip(sites, change.rates(context, sites)))
    by_frequency = sorted(sites, key=lambda site: (w.concept_frequency(site.split(":", 1)[1]), site))
    assert rates[by_frequency[-1]] < rates[by_frequency[0]]
    site = by_frequency[0]
    variant = change.propose(context, site, np.random.default_rng(1), 0)
    source = w.variants[w.dominant(donor, site)[0]]
    assert variant is not None and variant.origin.change == "lexical_borrowing"
    assert variant.origin.parent == source.id
    assert variant.payload["morpheme"] == source.payload["morpheme"]
    assert w.morphemes[variant.payload["morpheme"]].language == "b"

    alone = region_world((Region("p", (0.0, 0.0), language="a", villages=1),), languages=(ProtoLanguage("a"),),
                         semantics=True)
    group = alone.groups["p-v0"]
    assert change.total_rate(InnovationContext(alone, group, group.main_code, 1, 25.0)) == 0
