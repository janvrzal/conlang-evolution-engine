"""API změn světa (``cee.v2.edits``): operace, deník změn a jeho přehrání (krok A8)."""

from __future__ import annotations

import ast
import copy
import hashlib
import pickle
from pathlib import Path

import pytest

from cee.v2 import edits
from cee.v2.edits import OPERATIONS, Edit, Edits, journal_lines, load_journal
from cee.v2.events import ReplayEdits, replay_events
from cee.v2.history import History
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation, SimulationConfig
from cee.v2.world import gravity_links
from tests.v2.edit_worlds import SCENARIOS, fingerprint

#: Otisky světů s událostmi z doby před zavedením API (běh s Rustem i s ``CEE_NATIVE=0``):
#: dokazují, že přesun změn do ``edits`` nezměnil žádné chování.
BEFORE_API = {
    "trade-elite": ("a49145a8e0c174a2d121d540bde1d22e360e4908a00af1e73150c3c786e32ff7",
                    "e49850fb80e526341a8c92620188bd005a35669fc5fe07610568afd4e60504a2"),
    "church-school": ("e220b264c60c509fd0dba2062cde5beb97fe0be2f2a652cead403cd598e0a4f3",
                      "3ee9c781b9dd703922ae64b310617d14cbb2e4ac50ab05ea536af29f0169a908"),
    "shift-trade": ("bb660be97a226f69336ae21bb642e5a9f46db92df3eafabbdf568c002fbb669e",
                    "c43466fac96d7cc118f78672a81261d40c6bfb26351b06b4450d474efcc0135d"),
    "conquest-shift": ("390307a8b8036b28c05698145c86994be873691ce4f68abb5546a253e77f076c",
                       "f952e54efebfacecf78ba7b976b0035a8dd301d10747f6382071e63a5cf633cd"),
    "society": ("3026e8aa4568b59018af04c73a2c48a6c7d584c4aaedfbbdacfdbf4a558d72d3",
                "70a3672889948d6a795d5cb93251b9a8f51ba80e5df3ed3afc3b299aabb4b47c"),
    "refinement": ("4d99d97160bd66cd6bca3e62893c5d637be63ed8bdc0682a4f9e71fbf0e0d317",
                   "bde60ff02cfbdcf2b712d9f672c64c255647ed2e57fec6e5087116f4e357ddfc"),
    "polity": ("ae9810d529f715093f0599e7727d88cfdcc7c7fd3c9b3daf6dc0d391426f9afc",
               "4432100c3324e9a79825edc5aae76ca8c62e0c4643bd9e14a439775d289ad04f"),
}

#: Druhy záznamů v historii, které zapisují samy události (ne dynamika světa).
EVENT_KINDS = frozenset({
    "border", "contact", "bilingualism", "codification", "printing", "schooling", "religious_change",
    "refinement", "migration", "conquest", "war", "epidemic", "state_collapse", "state", "language_policy",
    "annexation", "lingua_franca", "secession", "collapse", "border_policy", "preserve", "identity",
    "immigration", "revival_movement", "standard", "schools", "plague", "recovery", "resettlement", "trade",
    "prestige", "foreign_elite", "elite_assimilation",
})


def _digest_without_events(history: History) -> str:
    sha = hashlib.sha256()
    for event, line in zip(history.events, history.lines()):
        if event["kind"] not in EVENT_KINDS:
            sha.update(line.encode("utf-8"))
            sha.update(b"\n")
    return sha.hexdigest()


@pytest.fixture(scope="module")
def runs():
    """Každý svět jednou s událostmi a jednou s přehráním deníku do nového světa."""
    found = {}
    for name, build in SCENARIOS.items():
        world, events, years = build()
        simulation = Simulation(world, events=events)
        simulation.run(years)
        fresh, _, _ = build()
        # Deník prošel řádky JSON, takže přehrání používá jen čísla a řetězce.
        journal = load_journal(journal_lines(world))
        replayed = Simulation(fresh, events=replay_events(journal, start_year=fresh.start_year,
                                                          dt=simulation.config.dt))
        replayed.run(years)
        found[name] = (simulation, replayed, journal)
    return found


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_svet_s_udalostmi_je_po_zavedeni_api_bitove_stejny(runs, name):
    simulation = runs[name][0]
    assert (simulation.history.digest(), fingerprint(simulation.world)) == BEFORE_API[name]


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_prehrani_deniku_da_stejny_svet_a_stejny_denik(runs, name):
    simulation, replayed, journal = runs[name]
    assert journal
    # Přehrání nemá žádné události, jen operace z deníku v týchž ticích.
    assert not [event for event in replayed.history.events if event["kind"] in EVENT_KINDS]
    assert _digest_without_events(replayed.history) == _digest_without_events(simulation.history)
    assert fingerprint(replayed.world) == fingerprint(simulation.world)
    assert replayed.world.edit_log == simulation.world.edit_log == journal


def test_deniky_svetu_pokryvaji_vsechny_operace(runs):
    used = {edit.op for _, _, journal in runs.values() for edit in journal}
    assert used == set(OPERATIONS)


def test_denik_je_jen_cisla_a_retezce_v_poradi_ticku(runs):
    for _, _, journal in runs.values():
        assert [edit.tick for edit in journal] == sorted(edit.tick for edit in journal)
        for edit in journal:
            assert edit.op in OPERATIONS and edit.tick >= 0
            for value in edit.args.values():
                assert value is None or isinstance(value, (str, int, float, bool, list))
                if isinstance(value, list):
                    assert all(isinstance(item, (str, int, float)) for item in value)
        assert load_journal([edit.line() for edit in journal]) == journal


def test_checkpoint_a_pickle_nesou_denik_a_pokracovani_je_stejne():
    world, events, years = SCENARIOS["shift-trade"]()
    straight = Simulation(world, SimulationConfig(checkpoint_every=100.0), events=events)
    straight.run(years)
    point = straight.checkpoints[12]  # rok 300, před posledními dvěma přesuny jazyka
    assert 0 < len(point.state[0].edit_log) < len(world.edit_log)

    resumed = Simulation.resume(point, events)
    resumed.run(years)
    assert resumed.world.edit_log == world.edit_log
    assert fingerprint(resumed.world) == fingerprint(world)
    assert resumed.history.digest() == straight.history.digest()

    restored = pickle.loads(pickle.dumps(point.state))
    assert restored[0].edit_log == point.state[0].edit_log
    assert copy.deepcopy(world).edit_log == world.edit_log
    # Kopie má vlastní deník: zápis do ní originál nezmění.
    clone = copy.deepcopy(world)
    Edits(clone, 99).set_group(clone.group_ids()[0], "prestige", 123.0)
    assert len(clone.edit_log) == len(world.edit_log) + 1


# --- jednotlivé operace -----------------------------------------------------------


def _world():
    world = village_grid(3, seed=1)
    Simulation(world)
    return world


def test_operace_se_zapise_s_tikem_a_cisly():
    world = _world()
    edit = Edits(world, 7)
    edit.connect("v00-00", "v00-02", 0.4, "strong")
    assert world.edit_log == [Edit(7, "connect", {"first": "v00-00", "second": "v00-02", "strength": 0.4,
                                                  "kind": "strong"})]
    assert world.links[("v00-02", "v00-00")].strength == 0.4


def test_operace_beze_zmeny_se_nezapise():
    world = _world()
    edit = Edits(world, 1)
    assert not edit.drop_link("v00-02", "v00-02")
    assert not edit.set_trade("v00-01", "v00-00", None)
    assert not edit.set_base_prestige("v00-00", None)
    assert not edit.set_group("v00-00", "population", world.groups["v00-00"].population)
    assert edit.set_group("v00-00", "population", 321)
    assert [item.op for item in world.edit_log] == ["set_group"]


def test_obchodni_podil_se_uklada_pod_abecedne_serazenou_dvojici():
    world = _world()
    edit = Edits(world, 0)
    edit.set_trade("v00-01", "v00-00", 0.2)
    assert world.trade == {("v00-00", "v00-01"): 0.2}
    assert world.edit_log[0].args["first"] == "v00-00"
    assert edit.set_trade("v00-00", "v00-01", None) and not world.trade


def test_argumenty_jsou_jen_skalary_a_pole_skupiny_se_kontroluji():
    world = _world()
    edit = Edits(world, 0)
    with pytest.raises(TypeError, match="číslo, řetězec"):
        edit.do("set_group", group="v00-00", field="prestige", value=object())
    with pytest.raises(KeyError, match="nemění"):
        edit.set_group("v00-00", "taboo", 1)
    with pytest.raises(TypeError):
        edit.set_group("v00-00", "population", 1.5)
    with pytest.raises(TypeError):
        edit.set_group("v00-00", "domain", "doma")
    with pytest.raises(ValueError, match="neexistuje"):
        edit.set_link("v00-00", "nikdo", 0.5)
    assert not world.edit_log


def test_numpy_cisla_se_zapisou_jako_cisla_pythonu():
    import numpy as np

    world = _world()
    Edits(world, 0).set_group("v00-00", "prestige", np.float64(0.75))
    value = world.edit_log[0].args["value"]
    assert type(value) is float and value == 0.75
    Edits(world, 0).set_group("v00-00", "population", np.int64(77))
    assert type(world.edit_log[1].args["value"]) is int and world.groups["v00-00"].population == 77


def test_pridani_skupiny_odvodi_kod_z_darce_a_zmrazeni_necha_dominantni_variantu():
    world = _world()
    donor = world.groups["v00-00"]
    edit = Edits(world, 3)
    edit.add_territory("t", "settlement", "world", (1.0, 2.0))
    edit.add_group("t", "t", 40, "v00-00", generation_years=donor.generation_years, prestige=1.5, elite=True)
    edit.set_code("t", acquisition="L2", l1_source="v00-00", l2_share=0.5)
    new = world.groups["t"]
    assert new.elite and new.prestige == 1.5 and new.population == 40
    assert new.main_code is not donor.main_code
    assert (new.main_code.acquisition, new.main_code.l1_source, new.main_code.l2_share) == ("L2", "v00-00", 0.5)
    assert world.territories["t"].position == (1.0, 2.0) and "t" in world.territories["world"].children
    # Nestálá proměnná se zafixuje na dominantní variantu, stálá zůstane.
    variable = next(iter(world.variables))
    mixed = new.main_code.repertoire.get(variable).with_innovation(
        next(item for item in world.variants if item != new.main_code.repertoire.get(variable).variants[0]), 0.3
    )
    new.main_code.repertoire.set(variable, mixed)
    dominant = mixed.dominant()[0]
    edit.fix_code("t")
    assert new.main_code.repertoire.get(variable).variants == (dominant,)
    assert [item.op for item in world.edit_log] == ["add_territory", "add_group", "set_code", "fix_code"]


def test_gravitacni_vazby_se_zapisou_po_jedne_a_dajou_totez_co_gravity_links():
    plain, journalled = _world(), _world()
    gravity_links(plain, max_distance=15.0)
    count = Edits(journalled, 0).connect_gravity(journalled.group_ids(), max_distance=15.0)
    assert count == len(journalled.edit_log) > 0
    assert {item.op for item in journalled.edit_log} == {"connect"}
    assert list(journalled.links.items()) == list(plain.links.items())


def test_prehrani_v_jinem_ticku_se_odmitne():
    world = _world()
    Edits(world, 4).set_group("v00-00", "population", 11)
    other = _world()
    with pytest.raises(ValueError, match="ticku"):
        ReplayEdits(0.0, tuple(world.edit_log)).apply(other, History(), 5)
    ReplayEdits(0.0, tuple(world.edit_log)).apply(other, History(), 4)
    assert other.groups["v00-00"].population == 11 and other.edit_log == world.edit_log


# --- události mění svět jen přes API -------------------------------------------------

_MODULES = ("events.py", "polity.py", "background.py")
_MUTATORS = {"add_group", "remove_group", "add_territory", "connect", "materialize", "pop", "setdefault",
             "update", "clear", "append", "extend", "remove", "insert", "popitem", "sort"}


_WORLD_DICTS = {"links", "trade", "states", "standards", "border_factors", "base_prestige", "prestige_mirror",
                "groups", "territories"}


def _rooted_in_world(node: ast.AST) -> bool:
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return isinstance(node, ast.Name) and node.id == "world"


def test_udalosti_staty_a_pozadi_nesahaji_na_svet_mimo_edits():
    """Žádný zápis do atributů a položek ani volání mutátorů světa mimo ``Edits``."""
    offences = []
    for module in _MODULES:
        path = Path(edits.__file__).parent / module
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            elif isinstance(node, ast.Delete):
                targets = node.targets
            for target in targets:
                for found in ast.walk(target):
                    if not isinstance(found, (ast.Attribute, ast.Subscript)) or isinstance(found.ctx, ast.Load):
                        continue
                    # Zápis do atributu je vždy změna objektu; zápis do položky jen u slovníků světa.
                    held = found.value if isinstance(found, ast.Subscript) else None
                    if held is None or _rooted_in_world(held) or (
                        isinstance(held, ast.Attribute) and held.attr in _WORLD_DICTS
                    ):
                        offences.append(f"{module}:{node.lineno} zápis {ast.unparse(found)}")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _MUTATORS and _rooted_in_world(node.func.value)):
                offences.append(f"{module}:{node.lineno} volání {ast.unparse(node.func)}")
    assert not offences, "\n".join(offences)
