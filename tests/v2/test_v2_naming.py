"""Podklady pro jména jazyků a nářečí (``cee.v2.naming``)."""

from cee.v2 import export, naming
from cee.v2.scenarios import ProtoLanguage, Region, region_world
from cee.v2.simulation import Simulation
from cee.v2.spec import build, check

VOWELS = set("aeiouəɛ")


def is_vowel(ipa):
    return ipa in VOWELS


def test_slabiky_a_zkracena_slozenina():
    assert naming.syllables(list("bapijek"), is_vowel) == [["b", "a"], ["p", "i"], ["j", "e", "k"]]
    assert naming.syllables(list("aum"), is_vowel) == [["a"], ["u", "m"]]
    # první část na slabiku, celek nejvýš o dvě slabiky delší
    assert "".join(naming.compound([list("lipopi"), list("bodipe")], is_vowel)) == "libodi"
    assert "".join(naming.compound([list("jato")], is_vowel)) == "jato"
    assert naming.compound([], is_vowel) == []


def test_smer_od_stredu_jazyka():
    assert naming.direction((0.0, 0.0), 50.0) == "center"
    assert naming.direction((10.0, 0.0), 50.0) == "center"
    assert naming.direction((40.0, 0.0), 50.0) == "east"
    assert naming.direction((0.0, 40.0), 50.0) == "south"  # osa y k jihu
    assert naming.direction((-30.0, -30.0), 50.0) == "northwest"


def world_with_two_regions():
    regions = (
        Region("west", (0.0, 0.0), neighbours=("east",), language="a", villages=3),
        Region("east", (80.0, 0.0), neighbours=("west",), language="a", villages=3, terrain="mountains"),
    )
    return region_world(regions, seed=3, languages=(ProtoLanguage("a", endonym=("person", "language")),))


def test_export_nese_vlastni_jmeno_puvod_a_fakta_o_narecich():
    world = world_with_two_regions()
    simulation = Simulation(world)
    simulation.run(300.0)
    data = export.export(simulation)
    living = [item for item in data["lineages"] if item["groups"]]
    assert living and all(item["endonym"] for item in living)
    assert all(item["origin_region"] in ("west", "east") for item in data["lineages"])
    facts = data["dialect_facts"]
    assert sum(len(item["groups"]) for item in facts) == 6
    assert {item["direction"] for item in facts} <= {"center", *naming.DIRECTIONS}
    mountain = [item for item in facts if item["regions"] == ["east"]]
    assert all(item["terrain"] == "mountains" for item in mountain)
    frame = export.frame(simulation)
    assert set(frame["endonyms"]) == {item["id"] for item in living}


def test_vlastni_jmeno_je_slozenina_slov_jazyka():
    world = world_with_two_regions()
    simulation = Simulation(world)
    simulation.run(25.0)
    lexicon = export.lexicon(simulation.world, "west-v0")
    name = naming.endonym(simulation.world, ["west-v0"])
    assert name and name.startswith(lexicon["person"]["form"][:1])
    assert len(name) <= len(lexicon["person"]["form"]) + len(lexicon["language"]["form"])


def test_popis_sveta_overi_pojmy_vlastniho_jmena():
    spec = {
        "end_year": 50, "semantics": False,
        "languages": [{"id": "a", "endonym": ["person", "neexistuje"]}],
        "regions": [{"id": "c", "position": [0, 0], "villages": 2}],
    }
    issues = {issue.path: issue.message for issue in check(spec)}
    assert "neznámý pojem" in issues["languages.0.endonym.1"]
    spec["languages"][0]["endonym"] = ["person", "language"]
    world, _, _ = build(spec)
    assert world.endonyms == {"a": ("person", "language")}
