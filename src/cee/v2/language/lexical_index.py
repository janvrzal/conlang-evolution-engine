"""Průběžná mapa homofonů a skóre lexikální jasnosti."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cee.v2.language.segments import Form

if TYPE_CHECKING:
    from cee.v2.world import Code, World

Pair = tuple[str, str]


class LexicalClarityIndex:
    """Příspěvky dominantních kořenů a memo dotázaných kandidátů.

    Neuchovává odkazy na svět; změna identity deníku vyvolá úplnou obnovu.
    """

    def __init__(self) -> None:
        self.token: int | None = None
        self.cursor = 0
        self.dominant_cursor = 0
        self.version = -1
        self.lexicon_version = -1
        self.dominant: dict[str, str] = {}
        self.root_concepts: dict[str, set[str]] = {}
        self.root_forms: dict[str, Form] = {}
        self.owners: dict[Form, set[Pair]] = {}
        self.scores: dict[Pair, float] = {}
        self.score_forms: dict[Pair, Form] = {}
        self.by_form: dict[Form, set[Pair]] = {}
        self.by_root: dict[str, set[Pair]] = {}
        self.graph_signature: object = None

    def _forget(self, key: Pair) -> None:
        form = self.score_forms.pop(key)
        del self.scores[key]
        self.by_form[form].remove(key)
        if not self.by_form[form]:
            del self.by_form[form]
        self.by_root[key[0]].remove(key)
        if not self.by_root[key[0]]:
            del self.by_root[key[0]]

    def _clear_scores(self) -> None:
        self.scores.clear()
        self.score_forms.clear()
        self.by_form.clear()
        self.by_root.clear()

    def _add(self, concept: str, root: str, form: Form) -> None:
        self.dominant[concept] = root
        self.root_concepts.setdefault(root, set()).add(concept)
        self.root_forms[root] = form
        self.owners.setdefault(form, set()).add((root, concept))

    def _remove(self, concept: str) -> Form:
        root = self.dominant.pop(concept)
        form = self.root_forms[root]
        self.owners[form].remove((root, concept))
        if not self.owners[form]:
            del self.owners[form]
        self.root_concepts[root].remove(concept)
        if not self.root_concepts[root]:
            del self.root_concepts[root]
            del self.root_forms[root]
        return form

    @staticmethod
    def _graph_signature(world: World) -> object:
        graph = world.semantics
        return None if graph is None else (id(graph), id(graph.relations))

    def sync(self, world: World, code: Code) -> None:
        state, forms = code.phonology, code.forms
        # Stejně jako původní cache je změna grafu vidět až při změně verze.
        if self.version == state.version:
            return
        signature = self._graph_signature(world)
        journal = state.dominant_log
        if (self.token != forms.token or self.cursor > len(forms.log)
                or self.dominant_cursor > len(journal)):
            self.dominant.clear()
            self.root_concepts.clear()
            self.root_forms.clear()
            self.owners.clear()
            self._clear_scores()
            for concept, root in state.dominant.items():
                self._add(concept, root, world.form_of(code, root))
        else:
            if self.graph_signature != signature:
                self._clear_scores()
            changed = set(forms.log[self.cursor:])
            dirty_forms: set[Form] = set()
            # Běžné přepisy tvarů nemění dominantní kořeny. Kontrola celé
            # mapy je záloha při změně slovní zásoby či neznámém zásahu.
            modified = {concept for concept, _, _ in journal[self.dominant_cursor:]}
            if (self.lexicon_version != state.lexicon_version
                    or (not changed and not modified)):
                modified.update(concept for concept in self.dominant.keys() | state.dominant.keys()
                                if self.dominant.get(concept) != state.dominant.get(concept))
            modified = {concept for concept in modified
                        if self.dominant.get(concept) != state.dominant.get(concept)}
            for concept in modified:
                if concept in self.dominant:
                    dirty_forms.add(self._remove(concept))
            for root in changed & self.root_concepts.keys():
                old = self.root_forms[root]
                new = world.form_of(code, root)
                if old != new:
                    concepts = self.root_concepts[root].copy()
                    for concept in concepts:
                        self._remove(concept)
                    for concept in concepts:
                        self._add(concept, root, new)
                    dirty_forms.update((old, new))
            for concept in modified:
                new_root = state.dominant.get(concept)
                if new_root is not None:
                    form = world.form_of(code, new_root)
                    self._add(concept, new_root, form)
                    dirty_forms.add(form)
            dirty: set[Pair] = set()
            for form in dirty_forms:
                dirty.update(self.by_form.get(form, ()))
            for root in changed:
                dirty.update(self.by_root.get(root, ()))
            for key in dirty:
                self._forget(key)
        self.token, self.cursor, self.version = forms.token, len(forms.log), state.version
        self.lexicon_version = state.lexicon_version
        self.dominant_cursor = len(journal)
        self.graph_signature = signature

    def score(self, world: World, code: Code, morpheme: str, concept: str) -> float:
        key = (morpheme, concept)
        found = self.scores.get(key)
        if found is not None:
            return found
        form = world.form_of(code, morpheme)
        eroded = len(form) <= 2 and len(form) < len(world.morphemes[morpheme].form)
        value = -0.5 if eroded else 0.0
        for root, other in self.owners.get(form, ()):
            if root != morpheme and other != concept and not (
                world.semantics is not None and world.semantics.related(concept, other)
            ):
                value -= 0.4
                break
        self.scores[key] = value
        self.score_forms[key] = form
        self.by_form.setdefault(form, set()).add(key)
        self.by_root.setdefault(morpheme, set()).add(key)
        return value
