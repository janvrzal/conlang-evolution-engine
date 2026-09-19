import json

import pytest

from cee.core.models import Inventory, Lexicon, State, Word
from cee.metrics.empirical_validation import RetentionCorpus, aggregate_reports, build_report, write_report


def _state():
    inherited = Word("water", [])
    loan = Word("wolf", [], source_id="trader")
    shifted = Word("sun", [], polysemy={"day", "light"})
    return State("branch", Inventory(), Lexicon([inherited, loan, shifted]), year=500)


def test_retention_corpus_rejects_range_and_duplicates(tmp_path):
    path = tmp_path / "corpus.csv"
    path.write_text(
        "concepticon_id,gloss,source,value,method_note\n"
        "1,WATER,Swadesh,0.9,fixture\n"
        "1,WATER,Swadesh,0.8,fixture\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicitní"):
        RetentionCorpus.from_csv(path)


def test_report_separates_contact_replacement_and_semantic_events(tmp_path):
    source = tmp_path / "proto.csv"
    source.write_text("id,ipa\nwater,wata\n", encoding="utf-8")
    corpus_path = tmp_path / "corpus.csv"
    corpus_path.write_text(
        "concepticon_id,gloss,source,value,method_note\n"
        ",water,fixture,0.9,fixture\n", encoding="utf-8"
    )
    corpus = RetentionCorpus.from_csv(corpus_path)
    events = [
        {"kind": "semantic_change_started", "change_id": "s1", "year": 100,
         "language_id": "branch", "evidence_type": "contact-calque", "change_kind": "extension"},
        {"kind": "semantic_change_progress", "change_id": "s1", "year": 180,
         "language_id": "branch", "phase": "completed"},
    ]
    report = build_report({"branch": _state()}, ["water", "wolf", "sun", "stone"], seed=7,
                          simulator_version="test", inputs={"proto": source}, events=events, corpus=corpus)

    lexical = report["branches"]["branch"]["lexical_retention"]
    assert lexical == {"inherited": 2, "contact_replacement": 1, "replacement": 0, "lost": 1, "ratio": 0.5}
    assert report["events"]["semantic_origins"] == {"contact": 1}
    assert report["events"]["coexistence"][0]["years"] == 80
    assert report["retention_corpus"]["coverage"]["fallback_heuristic"] == 3

    paths = write_report(report, tmp_path / "out")
    assert all(path.is_file() for path in paths)
    assert json.loads(paths[0].read_text(encoding="utf-8"))["inputs"]["seed"] == 7


def test_report_rejects_nonidentical_concept_instrument(tmp_path):
    source = tmp_path / "proto.csv"
    source.write_text("id,ipa\na,a\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicity"):
        build_report({"branch": _state()}, ["water", "water"], seed=1, simulator_version="test", inputs={"proto": source})


def test_aggregate_reports_requires_the_same_concept_instrument(tmp_path):
    source = tmp_path / "proto.csv"
    source.write_text("id,ipa\na,a\nb,b\n", encoding="utf-8")
    first = build_report({"branch": _state()}, ["water"], seed=1, simulator_version="test", inputs={"proto": source})
    second = build_report({"branch": _state()}, ["water"], seed=2, simulator_version="test", inputs={"proto": source})
    aggregate = aggregate_reports([first, second])
    assert aggregate["seeds"] == [1, 2]
    assert aggregate["branches"]["branch"]["runs"] == 2

    mismatched = build_report({"branch": _state()}, ["wolf"], seed=3, simulator_version="test", inputs={"proto": source})
    with pytest.raises(ValueError, match="identický"):
        aggregate_reports([first, mismatched])
