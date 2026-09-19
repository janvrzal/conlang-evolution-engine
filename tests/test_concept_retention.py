from cee.pipeline import load_lexicon_from_records
from cee.semantics.concepts import ConcepticonIndex
from cee.semantics.retention import ConceptRetentionModel
from cee.semantics.retention import build_concepticon_retention_prior


def test_empirical_retention_table_annotates_concepticon_id_and_gloss(mapper):
    index = ConcepticonIndex.from_tsv("tests/fixtures/concepticon_sample.tsv")
    model = ConceptRetentionModel.from_table("tests/fixtures/retention_sample.csv")
    lexicon = load_lexicon_from_records(
        [{"id": "hand", "ipa": "pata"}, {"id": "see", "ipa": "mita"}],
        mapper,
        concepticon_index=index,
        retention_model=model,
    )

    assert [word.grammatical_features["semantic.stability"] for word in lexicon.words] == [
        "0.910000", "0.720000"
    ]
    assert all("retention-corpus:" in word.grammatical_features["semantic.stability_provenance"] for word in lexicon.words)


def test_concepticon_stability_lists_build_a_reproducible_global_prior(tmp_path):
    path = build_concepticon_retention_prior(
        {
            "swadesh": "tests/fixtures/concepticon_stability_a.tsv",
            "peust": "tests/fixtures/concepticon_stability_b.tsv",
        },
        tmp_path / "prior.csv",
    )
    model = ConceptRetentionModel.from_table(path)

    assert model.by_id["1277"] == 0.95
    assert model.by_gloss["SEE"] == 0.5
    assert path.with_suffix(".json").is_file()
