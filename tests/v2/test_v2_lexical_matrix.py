"""Hromadné sestavení matice lexikální jasnosti zachovává staré buňky."""

from types import SimpleNamespace

import numpy as np

import cee.v2.pressures.lexical as lexical
from cee.v2.language.lexical_index import LexicalClarityIndex
from cee.v2.pressures.base import PressureBatch


class _FakeScorer:
    def __init__(self, group: str, calls: dict[str, list[tuple[str, str]]]):
        self.group = group
        self.calls = calls

    def __call__(self, morpheme: str, concept: str) -> float:
        return len(morpheme) / 10 + len(concept) / 100 + int(self.group[-1])

    def scores_many(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.calls[self.group].extend(pairs)
        return [self(morpheme, concept) for morpheme, concept in pairs]


def test_lexical_clarity_scatter_matches_cell_reference(monkeypatch) -> None:
    world = SimpleNamespace(
        table=object(),
        variants={
            "a": SimpleNamespace(payload={"morpheme": "root-a"}),
            "b": SimpleNamespace(payload={"morpheme": "b"}),
            "c": SimpleNamespace(payload={"morpheme": "root-a"}),
            "plain": SimpleNamespace(payload={"appeal": 0.2}),
        },
    )
    freqs = np.zeros((2, 3, 4))
    heard = np.zeros_like(freqs)
    freqs[0, 0, 0] = 0.2
    heard[0, 1, 0] = 0.3  # Dosažení pouze přes slyšení.
    freqs[0, 0, 1] = 0.4
    freqs[0, 2, 3] = 0.5  # Ne-morfémový slot zůstane nulový.
    heard[1, 1, 0] = 0.6
    freqs[1, 2, 1] = 0.7
    freqs[1, 0, 2] = 0.8
    heard[1, 1, 2] = 0.9
    batch = PressureBatch(
        world=world,  # type: ignore[arg-type]
        variable_ids=("lexical:river", "lexical:stone"),
        group_ids=("group-0", "group-1", "group-2"),
        freqs=freqs,
        slots=(("a", "b", None, "plain"), ("c", "a", "b", None)),
        tick=0,
        heard=heard,
    )

    calls: dict[str, list[tuple[str, str]]] = {group_id: [] for group_id in batch.group_ids}
    created: list[str] = []

    def clarity_map(_batch: PressureBatch, group_id: str) -> _FakeScorer:
        created.append(group_id)
        return _FakeScorer(group_id, calls)

    monkeypatch.setattr(lexical, "_clarity_map", clarity_map)
    actual = lexical.LexicalClarity().scores(batch)

    expected = np.zeros_like(freqs)
    reached = (freqs > 0) | (heard > 0)
    reference_calls: dict[str, list[tuple[str, str]]] = {group_id: [] for group_id in batch.group_ids}
    for row, variable_id in enumerate(batch.variable_ids):
        concept = variable_id.split(":", 1)[1]
        for slot, variant in enumerate(batch.slots[row]):
            if variant is None:
                continue
            morpheme = world.variants[variant].payload.get("morpheme")
            if not isinstance(morpheme, str):
                continue
            for column, group_id in enumerate(batch.group_ids):
                if reached[row, column, slot]:
                    reference_calls[group_id].append((morpheme, concept))
                    expected[row, column, slot] = _FakeScorer(group_id, reference_calls)(morpheme, concept)

    np.testing.assert_array_equal(actual, expected)
    assert calls == reference_calls  # Zachovává pořadí i opakované dvojice.
    assert created == ["group-0", "group-1", "group-2"]
    assert actual[0, 1, 0] != 0  # heard-only buňka.
    assert actual[0, 2, 3] == 0  # non-morpheme.
    assert actual[0, 0, 2] == 0  # None slot.


def test_index_scores_many_zachova_poradi_a_duplicitni_dvojice(monkeypatch) -> None:
    index = LexicalClarityIndex()
    calls: list[tuple[str, str]] = []

    def score(_world, _code, morpheme: str, concept: str) -> float:
        calls.append((morpheme, concept))
        return float(len(calls))

    monkeypatch.setattr(index, "score", score)
    pairs = [("root", "river"), ("root", "river"), ("other", "stone")]
    assert index.scores_many(None, None, pairs) == [1.0, 2.0, 3.0]  # type: ignore[arg-type]
    assert calls == pairs
