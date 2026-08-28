"""
Vývoj jedné linie a jeho záznam.

Bez historie nelze odpovědět na otázku, kvůli které projekt vzniká: čím slovo
prošlo, kdy, a co to způsobilo (CEE_master.md, Etapa 1 — trasovatelnost slova).
"""
import pytest

from cee.core.models import Lexicon
from cee.engine.history import BorrowingEvent, RuleApplication, SimulationHistory
from cee.engine.parser import YamlParser
from cee.pipeline import LineageConfig, evolve_lineage, lineage_payload

PRESET_PATH = "src/cee/data/presets/fantasy_preset.yaml"
SLOVA = [("vlk", "lupu"), ("voda", "laku"), ("strom", "petra"),
         ("oheň", "foku"), ("kámen", "sekuru")]


@pytest.fixture(scope="module")
def preset():
    return YamlParser.parse_preset(PRESET_PATH)


def _lexikon(mapper):
    return Lexicon(words=[mapper.parse_word(cid, ipa) for cid, ipa in SLOVA])


def _bez(mapper, preset, **kwargs):
    config = LineageConfig(years=1000, epochs=5, preset=preset, seed=3, **kwargs)
    return evolve_lineage(_lexikon(mapper), mapper, config)


def test_jazyk_se_skutecne_vyvine(mapper, preset):
    state, history = _bez(mapper, preset, biome="hory")

    prvni, posledni = history.snapshots[0], history.snapshots[-1]
    assert prvni.year == 0 and prvni.label == "Protojazyk"
    assert posledni.year == 1000 and posledni.label == "Současnost"
    assert prvni.words != posledni.words, "Jazyk se za tisíc let vůbec nezměnil."


def test_snapshoty_pokryvaji_epochy(mapper, preset):
    _state, history = _bez(mapper, preset, biome="prales")
    roky = [s.year for s in history.snapshots]

    assert roky == sorted(roky)
    assert roky[0] == 0 and roky[-1] == 1000
    assert len(roky) == len(set(roky)), "Epochy se nesmí opakovat."


def test_zadne_pravidlo_nepadne_naprazdno(mapper, preset):
    """
    Generátor prochází přes `accepts` síto, které pravidlo bez dopadu zahodí.
    Prázdný krok v chronologii je šum, ne historie.
    """
    for biome in (None, "hory", "prales"):
        _state, history = _bez(mapper, preset, biome=biome)
        prazdne = [a for a in history.rule_applications() if a.hit_count == 0]
        assert not prazdne, f"Biom {biome}: {[a.rule_name for a in prazdne]} nezasáhly nic."


def test_zaznam_nese_dopad_na_slova(mapper, preset):
    _state, history = _bez(mapper, preset, biome="hory")

    for app in history.rule_applications():
        assert app.changes
        for change in app.changes:
            assert change.before != change.after
            assert change.concept_id in dict(SLOVA)


def test_derivace_slova_navazuje(mapper, preset):
    """Každý krok derivace musí začínat tam, kde předchozí skončil."""
    state, history = _bez(mapper, preset, biome="hory")

    for concept, _ipa in SLOVA:
        steps = history.trace(state.node_id, concept)
        if len(steps) < 2:
            continue
        for predchozi, dalsi in zip(steps, steps[1:]):
            assert predchozi.year <= dalsi.year
        assert steps[0].note == "výchozí tvar"
        assert steps[0].form == dict(SLOVA)[concept]

        vysledny = next(w for w in state.lexicon.words if w.concept_id == concept)
        assert steps[-1].form == mapper.render_word(vysledny)


def test_bez_presetu_varuje(mapper):
    with pytest.warns(UserWarning, match="Bez presetu"):
        _state, history = evolve_lineage(
            _lexikon(mapper), mapper, LineageConfig(years=500, epochs=2)
        )
    assert history.rule_applications() == []


def test_stejny_seed_stejny_vyvoj(mapper, preset):
    def forma():
        state, _h = _bez(mapper, preset, biome="hory")
        return sorted((w.concept_id, mapper.render_word(w)) for w in state.lexicon.words)

    assert forma() == forma()


def test_payload_pro_ui(mapper, preset):
    state, history = _bez(mapper, preset, biome="hory")
    payload = lineage_payload(state, history, mapper)

    assert payload["status"] == "success"
    assert payload["node_id"] == "proto"
    assert len(payload["epochs"]) == len(history.snapshots)
    assert set(payload["traces"]) == {c for c, _ in SLOVA}
    assert all(e["kind"] == "sound_change" for e in payload["events"])


def test_historie_filtruje_podle_uzlu():
    history = SimulationHistory()
    history.record(RuleApplication(year=100, node_id="a", rule_name="r1", target={}, action={}))
    history.record(RuleApplication(year=200, node_id="b", rule_name="r2", target={}, action={}))
    history.record(BorrowingEvent(year=300, source_id="a", target_id="b", concepts=["vlk"]))

    assert [a.rule_name for a in history.rule_applications("a")] == ["r1"]
    assert [b.year for b in history.borrowings("b")] == [300]
    assert history.borrowings("a") == []


def test_vypujcka_je_v_derivaci():
    history = SimulationHistory()
    history.record(BorrowingEvent(year=400, source_id="north", target_id="south",
                                  concepts=["vlk"]))
    steps = history.trace("south", "vlk")

    assert len(steps) == 1
    assert "přejato z 'north'" in steps[0].note
