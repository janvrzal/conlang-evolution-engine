"""Generátor zvukových změn: priory, filtr věrohodnosti, stavovost."""

import pytest

from cee.core.models import Inventory, Lexicon, State
from cee.engine.decisions import ChangeDecisionEngine
from cee.engine.generator import SoundChangeGenerator, _reuses_schema_too_soon, _reverses
from cee.engine.inventory import InventoryView
from cee.engine.parser import YamlParser
from cee.engine.rules import Rule

PRESET = "src/cee/data/presets/fantasy_preset.yaml"


@pytest.fixture(scope="module")
def preset():
    return YamlParser.parse_preset(PRESET)


def _state(biome=None):
    return State(
        node_id="test",
        inventory=Inventory(),
        lexicon=Lexicon(),
        map={"biome": biome} if biome else {},
    )


def test_negeneruje_pravidla_bez_opory_v_inventari(mapper, preset):
    """
    Jazyk jen s /p t k a i u/ nemá znělé frikativy ani středové vokály,
    takže fortice ani vowel_shift nemají na čem pracovat.
    """
    inv = InventoryView(mapper, set("ptkaiu"))
    gen = SoundChangeGenerator(preset, seed=1)
    rules = gen.generate_rules_for_edge(_state(), 0, 400, num_rules=6, inventory=inv)

    assert rules, "Generátor nevyrobil nic, přestože lenice i synkopa mají oporu."

    # Každé vygenerované pravidlo musí mít oporu ve výchozím inventáři nebo
    # v tom, co mu připravila předchozí pravidla.
    stav = inv
    for rule in rules:
        assert stav.has_all(
            rule.target, rule.env_before, rule.env_after
        ), f"'{rule.name}' míří na třídu, která v inventáři {stav} není."
        stav = stav.apply(rule)

    zakazana = ("Fortice", "Zvýšení zadních")
    assert not [r for r in rules if r.name.startswith(zakazana)]


def test_bez_inventare_negeneruje_a_varuje(mapper, preset):
    gen = SoundChangeGenerator(preset, seed=1)
    with pytest.warns(UserWarning, match="nemá inventář"):
        assert gen.generate_rules_for_edge(_state(), 0, 400, inventory=None) == []


def test_kalibrace_nasobi_preset_ale_nezapne_vypnute_schema(preset):
    calibrated = SoundChangeGenerator(
        preset,
        schema_multipliers={"lenition": 2.5, "fortition": 0.0},
    )
    choices, weights = calibrated._weighted_schemas(None)
    result = {schema.name: weight for schema, weight in zip(choices, weights)}

    assert result["lenition"] == 250.0
    assert "fortition" not in result


def test_parser_presetu_zachova_makro_parametry(preset):
    assert preset["macro"]["deletion_rate"] == 0.4


def test_reverses_pozna_okamzite_zvraceni():
    lenice = Rule(name="lenice", target={"voi": "-", "cons": "+"}, action={"voi": "+"})
    zpet = Rule(name="ztráta znělosti", target={"voi": "+", "cons": "+"}, action={"voi": "-"})
    jina = Rule(name="synkopa", target={"syl": "+"}, action={"delete": "+"})

    assert _reverses(lenice, zpet) is True
    assert _reverses(lenice, jina) is False
    assert _reverses(lenice, lenice) is False
    assert _reverses(None, zpet) is False


def test_stejne_schema_se_neopakuje_v_kratkem_sledu():
    previous = Rule(
        name="Synkopa", target={"syl": "+"}, action={"delete": "+"}, year=200, schema_id="syncope"
    )
    soon = Rule(
        name="Další synkopa",
        target={"syl": "+"},
        action={"delete": "+"},
        year=500,
        schema_id="syncope",
    )
    later = Rule(
        name="Pozdní synkopa",
        target={"syl": "+"},
        action={"delete": "+"},
        year=700,
        schema_id="syncope",
    )

    assert _reuses_schema_too_soon([previous], soon) is True
    assert _reuses_schema_too_soon([previous], later) is False


def test_chronologie_neobsahuje_okamzite_zvraceni(mapper, preset):
    inv = InventoryView(mapper, set("aeiouptkbdɡfvszlrmn"))
    gen = SoundChangeGenerator(preset, seed=7)
    rules = gen.generate_rules_for_edge(_state(), 0, 1000, num_rules=10, inventory=inv)

    for predchozi, dalsi in zip(rules, rules[1:]):
        assert not _reverses(
            predchozi, dalsi
        ), f"'{predchozi.name}' je hned zrušeno pravidlem '{dalsi.name}'."


def test_pravidla_jsou_serazena_v_case(mapper, preset):
    inv = InventoryView(mapper, set("aeiouptkbdɡfvszlrmn"))
    gen = SoundChangeGenerator(preset, seed=3)
    roky = [
        r.year
        for r in gen.generate_rules_for_edge(_state(), 100, 900, num_rules=5, inventory=inv)
        if r.year is not None
    ]
    assert roky == sorted(roky)
    assert all(100 <= y <= 900 for y in roky)


def test_biom_meni_vysledek(mapper, preset):
    inv = InventoryView(mapper, set("aeiouptkbdɡfvszlrmn"))

    def bez(biome):
        gen = SoundChangeGenerator(preset, seed=42)
        return [
            r.name
            for r in gen.generate_rules_for_edge(_state(biome), 0, 600, num_rules=4, inventory=inv)
        ]

    assert bez("hory") != bez("prales")


def test_stejny_seed_stejny_vysledek(mapper, preset):
    inv = InventoryView(mapper, set("aeiouptkbdɡfvszlrmn"))

    def bez():
        gen = SoundChangeGenerator(preset, seed=11)
        return [
            r.name
            for r in gen.generate_rules_for_edge(_state("hory"), 0, 600, num_rules=4, inventory=inv)
        ]

    assert bez() == bez()


def test_lexikalni_tlak_prebije_vahu_schema(mapper):
    """Prior nesmí vybrat slabší inovaci jen proto, že je velmi vysoký."""
    words = [mapper.parse_word(f"intervocalic-{index}", "apa") for index in range(9)]
    words.append(mapper.parse_word("final", "ab"))
    state = State(node_id="test", inventory=Inventory(), lexicon=Lexicon(words=words))
    inventory = InventoryView.from_lexicon(state.lexicon, mapper)
    preset = {
        "schemas": {
            "final_devoicing": {"base_weight": 10_000},
            "lenition": {"base_weight": 1},
        }
    }
    generator = SoundChangeGenerator(preset, seed=7)

    candidate = generator.generate_pressure_driven(
        state,
        200,
        inventory,
        score=lambda rule: ChangeDecisionEngine.assess_sound_change(state, rule).pressure,
    )

    assert candidate is not None
    assert candidate.schema_id == "lenition"
