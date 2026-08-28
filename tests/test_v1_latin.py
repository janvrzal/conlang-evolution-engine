"""
Validace V1 — výstupní brána Etapy 1 (CEE_master.md, 5.2).

Aplikátor dostane latinský lexikon a publikovanou sadu zvukových zákonů;
měříme podíl odvozených forem shodných s doloženými.
"""
import csv
from pathlib import Path

from cee.core.models import Inventory, Lexicon, State
from cee.engine.fold import DerivationFold
from cee.engine.parser import YamlParser
from cee.metrics.validation import ValidationMetric

FIXTURES = Path(__file__).parent / "fixtures"
PROTO_CSV = FIXTURES / "latin_v1.csv"
RULES_YAML = FIXTURES / "latin_rules.yaml"


def _derivuj(mapper):
    lexicon = Lexicon()
    with open(PROTO_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lexicon.words.append(
                mapper.parse_word(concept_id=row["id"], ipa_string=row["ipa_proto"])
            )

    state = State(node_id="latin_v1", year=0, inventory=Inventory(), lexicon=lexicon)
    fold = DerivationFold(YamlParser.parse_rules(str(RULES_YAML)))
    fold.apply_to_lexicon(lexicon, mapper, state)
    return lexicon, state


def test_v1_latina_prochazi(mapper):
    lexicon, _state = _derivuj(mapper)
    metrics = ValidationMetric.evaluate(lexicon, str(PROTO_CSV), mapper)

    assert metrics["comparisons"] == 25
    assert metrics["exact_match_ratio"] == 1.0
    assert metrics["avg_edit_distance"] == 0.0


def test_fold_aktualizuje_inventar(mapper):
    """
    Fold je stavový (4.3): po derivaci musí inventář odpovídat tomu, co
    v jazyce zbylo. /t/ zmizí — všechna se lenovala nebo odpadla na konci.
    """
    _lexicon, state = _derivuj(mapper)

    assert state.inventory.segments, "Inventář zůstal prázdný — fold ho nikam neuložil."
    assert "t" not in state.inventory.segments
    assert {"b", "d", "ɡ"} <= state.inventory.segments


def test_validace_bez_prekryvu_nespadne(mapper, tmp_path):
    """Nulový překryv ID musí vrátit metriky, ne KeyError."""
    gt = tmp_path / "gt.csv"
    gt.write_text("id,ipa_target\nZZZ,xxx\n", encoding="utf-8")

    lexicon, _state = _derivuj(mapper)
    metrics = ValidationMetric.evaluate(lexicon, str(gt), mapper)

    assert metrics["comparisons"] == 0
    assert metrics["exact_match_ratio"] == 0.0
