from cee.engine.decisions import ChangeDecisionEngine
from cee.pipeline import load_lexicon_from_records
from cee.semantics.concepts import ConcepticonIndex


def test_concepticon_doplni_role_a_domenu_bez_rucnich_tagu(mapper):
    index = ConcepticonIndex.from_tsv("tests/fixtures/concepticon_sample.tsv")
    lexicon = load_lexicon_from_records(
        [{"id": "hand", "ipa": "pata"}, {"id": "see", "ipa": "pata"}],
        mapper,
        concepticon_index=index,
    )
    hand, see = lexicon.words
    assert hand.grammatical_features["semantic.domains"] == "The body"
    assert hand.grammatical_features["semantic.roles"] == "reference"
    assert see.grammatical_features["semantic.roles"] == "event"

    decision = ChangeDecisionEngine().assess_homophones([hand, see])[0]
    assert decision.pressure == 0.0
    assert decision.evidence_level == "semantic-metadata"


def test_concepticon_hleda_podle_id_i_glosu():
    index = ConcepticonIndex.from_tsv("tests/fixtures/concepticon_sample.tsv")
    assert index.lookup("1277").gloss == "HAND"
    assert index.lookup("hand").concepticon_id == "1277"
    assert "sha256=" in index.provenance
