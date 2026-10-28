"""Kontakt jazyků enginu v2 (milník M5): filtry, adaptace, komunity."""

from cee.v2 import contact, morphology
from cee.v2.events import LanguageShift
from cee.v2.history import History
from cee.v2.scenarios import SYNTAX_GRAMMAR, Language, Place, contact_world, language_shift
from cee.v2.simulation import Simulation

NO_CASE = {name: construction for name, construction in SYNTAX_GRAMMAR.items() if name != "OBJ"}


def _pair(seed=1):
    return contact_world([
        Language("a", (Place("a0", (0.0, 0.0)),)),
        Language("b", (Place("b0", (100.0, 0.0)),), grammar=NO_CASE,
                 consonants=("t", "k", "s", "n", "m", "l", "ʃ", "f", "x", "v", "r", "j")),
    ], seed=seed)


def test_jazyky_maji_vlastni_slova_a_bunky():
    world = _pair()
    Simulation(world)
    a, b = world.groups["a0"].main_code, world.groups["b0"].main_code
    assert a.language == "a" and b.language == "b"
    assert {world.morphemes[unit].language for unit in a.phonology.vocabulary} == {"a"}
    assert not any(world.morphemes[unit].cell == "OBJ" for unit in b.phonology.vocabulary)
    assert any(world.morphemes[unit].cell == "OBJ" for unit in a.phonology.vocabulary)
    # Lexikální proměnné se liší od začátku, takže jsou živé (mohou se mísit).
    assert "lexical:water" in world.live


def test_filtr_vypujcek_a_interference_podle_thomasona_a_kaufmana():
    world = _pair()
    frequent = max(world.concept_frequencies, key=world.concept_frequencies.get)
    rare = min(world.concept_frequencies, key=world.concept_frequencies.get)
    assert contact.borrowing_factor(world, f"lexical:{rare}") > contact.borrowing_factor(world, f"lexical:{frequent}")
    assert contact.borrowing_factor(world, "construction:NEG") < contact.borrowing_factor(world, f"lexical:{rare}")
    assert contact.interference_factor(world, "construction:NEG") > contact.interference_factor(world, f"lexical:{rare}")


def test_vypujcka_se_adaptuje_a_sklonuje_podle_prijemce():
    world = _pair()
    Simulation(world)
    b = world.groups["b0"].main_code
    loan = world.groups["a0"].main_code.phonology.dominant["dog"]
    contact.adopt(world, "b0", loan)
    assert set(world.form_of(b, loan)) <= set(contact.inventory(world, b))
    units = morphology.units_of(world, b, loan)
    cells = {world.morphemes[unit].cell for unit in units[1:]}
    assert "OBJ" not in cells  # příjemce pád předmětu nemá
    stats = morphology.class_stats(world, b)
    for unit in units[1:]:
        cell = world.morphemes[unit].cell
        assert world.unit_of(b, unit).exponent == stats.productive("noun", cell)


def test_adaptace_nahradi_cizi_hlasku_nejblizsi_vlastni():
    world = _pair()
    Simulation(world)
    b = world.groups["b0"].main_code
    table = world.table
    native = set(contact.inventory(world, b))
    foreign = [segment for segment in (table.id_of("w"), table.id_of("h"), table.id_of("p")) if segment not in native]
    assert foreign
    adapted = contact.adapt(world, b, tuple(foreign) + (table.id_of("a"),))
    assert set(adapted) <= native
    assert not table.is_vowel(adapted[0]) and table.is_vowel(adapted[-1])


def test_pristehovalci_drzi_podil_l2_mluvcich():
    world = contact_world([Language("proto", (Place("city", (0.0, 0.0), immigration=0.4),))])
    world.groups["city"].main_code.l2_share = 0.0
    for tick in range(10):
        contact.community_step(world, 25.0, tick, tick * 25.0, History())
    assert abs(world.groups["city"].main_code.l2_share - 0.4) < 1e-9


def test_prechod_zalozi_skupinu_s_interferenci_a_stary_kod_vymre():
    world, events = language_shift(seed=1, start=100.0)
    simulation = Simulation(world, events=events)
    simulation.run(100.0)
    learners = world.groups["x2>y"]
    assert learners.main_code.language == "y" and learners.main_code.l1_source == "x2"
    assert learners.community == world.groups["x2"].community == "x2"
    assert ("x2>y", "y0") in world.links and ("x2>y", "x2") in world.links
    simulation.run(600.0)
    assert "x2" not in world.groups and "x0" not in world.groups
    shifts = simulation.history.of_kind("language_shift")
    assert {event["group"] for event in shifts} == {"x0", "x1", "x2"}
    stopped = {event["group"]: event["year"] for event in simulation.history.of_kind("transmission_stopped")}
    # Děti přestanou starý jazyk učit dřív, než vymře.
    assert all(stopped[event["group"]] <= event["year"] for event in shifts)
    assert world.groups["x2>y"].main_code.l1_source is None


def test_prechod_zachova_jazyk_skupiny_bez_vazeb():
    world, _ = language_shift(seed=1, start=100.0)
    simulation = Simulation(world, events=[LanguageShift(100.0, "x0", "y0")])
    simulation.run(300.0)
    # Bez vazby na rodilé mluvčí se skupina učí jen od sebe a od zdroje.
    assert {link.target for link in world.neighbors("x0>y")} <= {"x0", "x1", "x1>y"}


def test_determinismus_s_kontaktem():
    def run():
        world, events = language_shift(seed=2, start=200.0)
        simulation = Simulation(world, events=events)
        simulation.run(600.0)
        return simulation.history.digest()

    assert run() == run()
