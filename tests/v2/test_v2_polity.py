"""Státy, jazyková politika a lingua franca (M6f, ``cee.v2.polity``)."""

import pytest

from cee.v2.parameters import Parameters
from cee.v2.polity import (
    Annexation,
    BorderPolicy,
    Collapse,
    LanguagePolicy,
    LinguaFranca,
    Preserve,
    Revival,
    Schools,
    Secession,
    Standard,
    State,
    groups_in,
    language_census,
    seat_of,
)
from cee.v2.scenarios import ProtoLanguage, Region, kingdom, region_world
from cee.v2.simulation import Simulation

LANGUAGES = (ProtoLanguage("a"), ProtoLanguage("b"))


def pair(terrain="plain", identity="shared", distance=60.0, villages=3):
    regions = (
        Region("capital", (0.0, 0.0), density=2.0, neighbours=("x",), language="a", villages=villages),
        Region("x", (distance, 0.0), neighbours=("capital",), language="b", villages=villages,
               terrain=terrain, identity=identity),
    )
    return region_world(regions, seed=1, languages=LANGUAGES)


def home_share(world, region, language):
    return language_census(world)[region]["home"].get(language, 0.0)


def test_stat_zvedne_prestiz_hlavniho_mesta_a_spoji_vesnice_se_sidlem():
    world = pair()
    before = {group_id: world.groups[group_id].prestige for group_id in world.group_ids()}
    simulation = Simulation(world, events=[State(0.0, "k", ("capital", "x"), "capital", centralization="strong")])
    simulation.run(25.0)
    seat = seat_of(world, "capital")
    assert world.states["k"].seat == seat and world.states["k"].language == "a"
    for group_id in groups_in(world, ["capital"]):
        assert world.groups[group_id].prestige == pytest.approx(before[group_id] * world.params.capital_prestige)
    for group_id in groups_in(world, ["x"]):
        assert (group_id, seat) in world.links
    assert simulation.history.of_kind("state")


def test_neplatne_zadani_statu_odmitne_srozumitelne():
    world = pair()
    with pytest.raises(ValueError, match="možnosti"):
        State(0.0, "k", ("capital", "x"), "capital", policy="brutal").apply(world, Simulation(world).history, 0)
    with pytest.raises(ValueError, match="Hlavní město"):
        State(0.0, "k", ("x",), "capital").apply(world, Simulation(world).history, 0)
    with pytest.raises(ValueError, match="není region"):
        State(0.0, "k", ("capital", "nikde"), "capital").apply(world, Simulation(world).history, 0)
    with pytest.raises(ValueError, match="neexistuje"):
        LanguagePolicy(0.0, "nikdo", "enforced").apply(world, Simulation(world).history, 0)


def test_region_odmitne_neznamy_teren_a_jazyk():
    with pytest.raises(ValueError, match="terénu"):
        region_world((Region("r", (0.0, 0.0), terrain="bažina"),))
    with pytest.raises(ValueError, match="protojazyk"):
        region_world((Region("r", (0.0, 0.0), language="z"),), languages=LANGUAGES)
    with pytest.raises(ValueError, match="languages"):
        region_world((Region("r", (0.0, 0.0), language="a"),))


def border(world):
    return max(
        link.strength for (first, second), link in world.links.items()
        if first.startswith("capital") and second.startswith("x")
    )


def test_teren_oslabi_vazbu_pres_hranici_a_identita_nastavi_loajalitu():
    plain, mountains = pair(), pair(terrain="mountains", identity="strong")
    assert border(mountains) == pytest.approx(border(plain) * Parameters().terrain_access["mountains"])
    strong = Parameters().identity_loyalty["strong"]
    assert all(mountains.groups[g].loyalty == strong for g in groups_in(mountains, ["x"]))


def test_tolerantni_stat_necha_stabilni_dvojjazycnost():
    world = pair()
    simulation = Simulation(world, events=[State(0.0, "k", ("capital", "x"), "capital", policy="tolerant")])
    simulation.run(400.0)
    census = language_census(world)["x"]
    assert census["home"] == {"b": 1.0}
    assert census["public"]["a"] > 0.0


def test_vynucovani_prosadi_jazyk_statu_na_blizke_rovine():
    world = pair()
    simulation = Simulation(world, events=[State(0.0, "k", ("capital", "x"), "capital", policy="enforced")])
    simulation.run(300.0)
    assert home_share(world, "x", "b") == 0.0
    assert language_census(world)["x"]["public"] == {}
    kinds = {event["kind"] for event in simulation.history.events}
    assert {"nativization", "language_shift"} <= kinds


def test_hory_se_silnou_identitou_si_jazyk_udrzi():
    world = pair(terrain="mountains", identity="strong")
    Simulation(world, events=[State(0.0, "k", ("capital", "x"), "capital", policy="promoted")]).run(500.0)
    assert home_share(world, "x", "b") == 1.0


def test_odlisna_identita_prechod_zpomali():
    shared, distinct = pair(), pair(identity="distinct")
    for world in (shared, distinct):
        Simulation(world, events=[State(0.0, "k", ("capital", "x"), "capital", policy="promoted")]).run(500.0)
    assert home_share(shared, "x", "b") < home_share(distinct, "x", "b") < 1.0


def test_uvolneni_politiky_prechod_zastavi():
    world = pair(identity="distinct")
    simulation = Simulation(world, events=[
        State(0.0, "k", ("capital", "x"), "capital", policy="enforced"),
        LanguagePolicy(50.0, "k", "tolerant"),
    ])
    simulation.run(75.0)
    paused = home_share(world, "x", "b")
    simulation.run(400.0)
    assert 0.0 < paused < 1.0
    assert home_share(world, "x", "b") == pytest.approx(paused, abs=0.02)


def test_pripojeni_regionu_rozsiri_stat():
    regions = (
        Region("capital", (0.0, 0.0), density=2.0, neighbours=("x",), language="a", villages=3),
        Region("x", (60.0, 0.0), neighbours=("capital", "y"), language="b", villages=3),
        Region("y", (120.0, 0.0), neighbours=("x",), language="b", villages=3),
    )
    world = region_world(regions, seed=1, languages=LANGUAGES)
    simulation = Simulation(world, events=[
        State(0.0, "k", ("capital", "x"), "capital"), Annexation(50.0, "k", ("y",)),
    ])
    simulation.run(75.0)
    assert world.states["k"].regions == ("capital", "x", "y")
    assert language_census(world)["y"]["state"] == "k"
    assert language_census(world)["y"]["public"]["a"] > 0.0


def test_lingua_franca_zustane_mimo_domov_nebo_zdomacni():
    stable, native = pair(), pair()
    Simulation(stable, events=[LinguaFranca(0.0, "capital", ("x",), spread="common")]).run(400.0)
    Simulation(native, events=[LinguaFranca(0.0, "capital", ("x",), spread="common", nativize=True)]).run(400.0)
    census = language_census(stable)["x"]
    assert census["home"] == {"b": 1.0}
    assert census["public"]["a"] == pytest.approx(Parameters().lingua_franca_levels["common"], abs=0.02)
    assert home_share(native, "x", "b") < 1.0
    public = [g for g in stable.group_ids() if stable.groups[g].domain == "public"]
    assert public and all(stable.groups[g].main_code.l2_share == 1.0 for g in public)


def test_hory_snizi_rozsireni_lingua_franca():
    plain, mountains = pair(), pair(terrain="mountains")
    for world in (plain, mountains):
        Simulation(world, events=[LinguaFranca(0.0, "capital", ("x",), spread="universal")]).run(25.0)
    assert language_census(mountains)["x"]["public"]["a"] < language_census(plain)["x"]["public"]["a"]


def test_kralovstvi_je_deterministicke():
    digests = []
    for _ in range(2):
        world, events = kingdom(1, modern=200.0)
        simulation = Simulation(world, events=events)
        simulation.run(300.0)
        digests.append(simulation.history.digest())
    assert digests[0] == digests[1]


def test_spisovny_jazyk_statu_ctou_vsichni_a_zvedne_prestiz_jeho_jazyka():
    world = pair()
    history = Simulation(world).history
    State(0.0, "k", ("capital", "x"), "capital").apply(world, history, 0)
    before = {g: world.groups[g].prestige for g in world.group_ids()}
    Standard(0.0, "k", literacy="towns").apply(world, history, 0)
    written = world.standards["k"]
    assert world.groups[written].written
    for group_id in groups_in(world, ["capital", "x"]):
        group = world.groups[group_id]
        assert group.standard == written and group.literacy > 0.0
        own = group.main_code.language == "a"
        expected = before[group_id] * (world.params.standard_prestige if own else 1.0)
        assert group.prestige == pytest.approx(expected)
    with pytest.raises(ValueError, match="už spisovný jazyk má"):
        Standard(0.0, "k").apply(world, history, 0)


def test_skola_uci_jen_jazyk_normy_a_vlastni_norma_zustane():
    world = pair()
    history = Simulation(world).history
    with pytest.raises(ValueError, match="nemá spisovný jazyk"):
        Schools(0.0, "x").apply(world, history, 0)
    State(0.0, "k", ("capital", "x"), "capital", policy="tolerant").apply(world, history, 0)
    Standard(0.0, "x").apply(world, history, 0)
    Standard(0.0, "k").apply(world, history, 0)
    Schools(0.0, "k").apply(world, history, 0)
    assert world.groups[world.standards["k"]].openness > 0.0  # tisk: norma sleduje řeč sídla
    for group_id in groups_in(world, ["x"]):
        assert world.groups[group_id].standard == world.standards["x"]
        assert world.groups[group_id].schooling == 0.0
    for group_id in groups_in(world, ["capital"]):
        assert world.groups[group_id].schooling > 0.0
    public = [g for g in world.group_ids() if world.groups[g].domain == "public"]
    assert public and all(world.groups[g].schooling > 0.0 for g in public)


def test_skola_ve_vlastnim_jazyce_prechod_brzdi():
    plain, protected = pair(identity="distinct"), pair(identity="distinct")
    state = State(0.0, "k", ("capital", "x"), "capital", policy="enforced")
    Simulation(plain, events=[state]).run(100.0)
    Simulation(protected, events=[state, Standard(0.0, "x"), Schools(0.0, "x")]).run(100.0)
    assert home_share(plain, "x", "b") < home_share(protected, "x", "b")


def test_diglosni_skola_vytvori_vysokou_varietu():
    world = pair()
    history = Simulation(world).history
    State(0.0, "k", ("capital", "x"), "capital", policy="tolerant").apply(world, history, 0)
    Standard(0.0, "k").apply(world, history, 0)
    Schools(0.0, "k", diglossic=True).apply(world, history, 0)
    assert any(g.endswith(">H") for g in world.group_ids())
    assert world.groups[world.standards["k"]].openness == 0.0


def chain():
    regions = (
        Region("w", (0.0, 0.0), neighbours=("m",), language="a", villages=3),
        Region("m", (40.0, 0.0), neighbours=("w", "e"), language="a", villages=3),
        Region("e", (80.0, 0.0), neighbours=("m",), language="a", villages=3),
    )
    return region_world(regions, seed=1, languages=(ProtoLanguage("a"),))


def crossing(world, here, there):
    return [link for (first, second), link in sorted(world.links.items())
            if first.startswith(here + "-") and second.startswith(there + "-")]


def test_hranice_vznikne_mezi_staty_a_pripojeni_ji_zrusi():
    world = chain()
    base = {key: link.strength for key, link in world.links.items()}
    history = Simulation(world).history
    State(0.0, "west", ("w",), "w", centralization="none").apply(world, history, 0)
    State(0.0, "east", ("m", "e"), "e", centralization="none", border="closed").apply(world, history, 0)
    levels = world.params.border_levels
    for link in crossing(world, "w", "m"):
        assert link.strength == pytest.approx(base[(link.source, link.target)] * min(levels["normal"], levels["closed"]))
    for link in crossing(world, "m", "e"):
        assert link.strength == pytest.approx(base[(link.source, link.target)])
    BorderPolicy(0.0, "east", "open").apply(world, history, 0)
    for link in crossing(world, "w", "m"):
        assert link.strength == pytest.approx(base[(link.source, link.target)] * levels["normal"])
    Annexation(0.0, "west", ("m", "e")).apply(world, history, 0)
    assert "east" not in world.states  # přišel o hlavní město
    for link in crossing(world, "w", "m"):
        assert link.strength == pytest.approx(base[(link.source, link.target)])


def test_region_mimo_staty_ma_hranici_se_statem():
    world = chain()
    base = {key: link.strength for key, link in world.links.items()}
    State(0.0, "west", ("w",), "w").apply(world, Simulation(world).history, 0)
    for link in crossing(world, "w", "m"):
        assert link.strength == pytest.approx(base[(link.source, link.target)] * world.params.border_levels["normal"])


def test_stat_odmitne_cizi_region_a_odtrzeni_hlavniho_mesta():
    world = chain()
    history = Simulation(world).history
    State(0.0, "k", ("w", "m"), "w").apply(world, history, 0)
    with pytest.raises(ValueError, match="už patří"):
        State(0.0, "j", ("m", "e"), "e").apply(world, history, 0)
    with pytest.raises(ValueError, match="nemůže odtrhnout"):
        Secession(0.0, "j", ("w",), "w").apply(world, history, 0)


def test_rozpad_statu_vrati_prestiz_a_zastavi_prechod():
    kept, collapsed = pair(), pair()
    capital = groups_in(kept, ["capital"])
    base = {g: kept.groups[g].prestige for g in capital}
    state = State(0.0, "k", ("capital", "x"), "capital", policy="promoted")
    Simulation(kept, events=[state]).run(600.0)
    simulation = Simulation(collapsed, events=[state, Collapse(300.0, "k")])
    simulation.run(325.0)
    for group_id in capital:
        assert collapsed.groups[group_id].prestige == pytest.approx(base[group_id])
    seat = seat_of(collapsed, "capital")
    native = [g for g in groups_in(collapsed, ["x"]) if collapsed.groups[g].main_code.language == "b"]
    assert native and not any((g, seat) in collapsed.links for g in native)
    after = home_share(collapsed, "x", "b")
    simulation.run(600.0)
    assert home_share(collapsed, "x", "b") == pytest.approx(after, abs=0.02)
    assert home_share(kept, "x", "b") < after


def test_odtrzeni_vytvori_novy_stat_a_jeho_jazyk_ziska_prestiz():
    world = pair()
    simulation = Simulation(world, events=[
        State(0.0, "k", ("capital", "x"), "capital", policy="promoted"),
        Secession(100.0, "nezavisly", ("x",), "x"),
    ])
    simulation.run(125.0)
    assert world.states["k"].regions == ("capital",)
    assert world.states["nezavisly"].language == "b"
    native = [g for g in groups_in(world, ["x"]) if world.groups[g].main_code.language == "b"]
    assert all(world.groups[g].prestige == pytest.approx(0.5 * world.params.capital_prestige) for g in native)
    assert simulation.history.of_kind("secession")


def test_autor_muze_jazyk_zakonzervovat_a_konzervaci_zrusit():
    world = pair()
    simulation = Simulation(world, events=[
        State(0.0, "k", ("capital", "x"), "capital", policy="enforced"),
        Preserve(0.0, ("x",)),
        Preserve(300.0, ("x",), preserved=False),
    ])
    simulation.run(275.0)
    assert home_share(world, "x", "b") == 1.0
    simulation.run(600.0)
    assert home_share(world, "x", "b") < 1.0


def test_region_muze_byt_zakonzervovany_od_zacatku():
    regions = (
        Region("capital", (0.0, 0.0), density=2.0, neighbours=("x",), language="a", villages=3),
        Region("x", (60.0, 0.0), neighbours=("capital",), language="b", villages=3, preserve=True),
    )
    world = region_world(regions, seed=1, languages=LANGUAGES)
    Simulation(world, events=[State(0.0, "k", ("capital", "x"), "capital", policy="enforced")]).run(300.0)
    assert home_share(world, "x", "b") == 1.0


def enforced(*extra, identity="distinct"):
    world = pair(identity=identity)
    simulation = Simulation(world, events=[State(0.0, "k", ("capital", "x"), "capital", policy="enforced"), *extra])
    return world, simulation


def test_hnuti_s_normou_a_skolou_obrati_prechod():
    plain, base = enforced()
    revived, simulation = enforced(Revival(50.0, ("x",), strength="national"), Standard(50.0, "x"), Schools(50.0, "x"))
    base.run(300.0)
    simulation.run(50.0)
    start = home_share(revived, "x", "b")
    simulation.run(300.0)
    assert home_share(plain, "x", "b") == 0.0
    assert home_share(revived, "x", "b") > 0.5 and start > 0.5


def test_odtrzeni_s_obrozenim_vrati_jazyk():
    world, simulation = enforced(Secession(50.0, "nezavisly", ("x",), "x"), Revival(50.0, ("x",), strength="national"))
    simulation.run(50.0)
    start = home_share(world, "x", "b")
    simulation.run(400.0)
    assert home_share(world, "x", "b") > start
    assert simulation.history.of_kind("revival")


def test_vymrely_jazyk_lze_obrodit_jen_z_pisma():
    later = (Secession(300.0, "nezavisly", ("x",), "x"), Revival(300.0, ("x",), strength="national"))
    written, simulation = enforced(Standard(0.0, "x"), *later)
    silent, quiet = enforced(*later)
    for world, run in ((written, simulation), (silent, quiet)):
        run.run(275.0)
        assert home_share(world, "x", "b") == 0.0
        run.run(300.0)
    assert not [g for g in silent.group_ids() if g.endswith(":revived")]
    created = [g for g in written.group_ids() if g.endswith(":revived")]
    assert created and all(written.groups[g].main_code.language == "b" for g in created)
    simulation.run(500.0)
    assert home_share(written, "x", "b") > 0.0


def test_obrozeni_odmitne_neznamou_silu():
    world = pair()
    with pytest.raises(ValueError, match="síla obrození"):
        Revival(0.0, ("x",), strength="bouřlivé").apply(world, Simulation(world).history, 0)
