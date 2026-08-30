import copy
from typing import Dict, Iterable, Optional, cast

from cee.core.models import State, Word


class MorphologyEvaluator:
    """
    Vykonává morfologické operace, např. skládání slov (compounding)
    a případně analogii (zarovnávání nepravidelností).
    """

    def compound(
        self, state: State, word1_id: str, word2_id: str, new_concept_id: str
    ) -> Optional[Word]:
        """
        Vytvoří nové slovo spojením dvou existujících slov z lexikonu státu.
        Respektuje typologický parametr 'compound_head' (initial vs final).
        word1: hlava (head)
        word2: modifikátor (modifier)

        Např: head='město', modifier='zlatý'.
        Pokud head='final', výsledek bude [zlatý][město].
        Pokud head='initial', výsledek bude [město][zlatý].
        """
        w1 = state.lexicon.get_word(word1_id)
        w2 = state.lexicon.get_word(word2_id)

        if not w1 or not w2:
            return None
        existing = state.lexicon.get_word(new_concept_id)
        if existing:
            return existing

        head_order = state.compound_head

        if head_order == "initial":
            new_segments = copy.deepcopy(w1.segments) + copy.deepcopy(w2.segments)
        else:  # final
            new_segments = copy.deepcopy(w2.segments) + copy.deepcopy(w1.segments)

        new_word = Word(
            concept_id=new_concept_id,
            segments=new_segments,
            origin_year=state.year,
            frequency=min(w1.frequency, w2.frequency) * 0.6,
            morpheme_boundaries={len(w1.segments) if head_order == "initial" else len(w2.segments)},
            parent_word_id=w1.id,
            origin_type="compound",
            origin_rule="compounding",
        )

        # Přidáme do lexikonu
        state.lexicon.words.append(new_word)
        return new_word

    def derive(
        self,
        state: State,
        root_id: str,
        affix_id: str,
        new_concept_id: str,
        *,
        prefix: Optional[bool] = None,
    ) -> Optional[Word]:
        """Lexikalizuje afix z existujícího slova a zaznamená hranici morfémů."""
        root = state.lexicon.get_word(root_id)
        affix = state.lexicon.get_word(affix_id)
        if not root or not affix:
            return None
        if state.lexicon.get_word(new_concept_id):
            return state.lexicon.get_word(new_concept_id)

        use_prefix = state.affixation_strategy == "prefix" if prefix is None else prefix
        left, right = (affix, root) if use_prefix else (root, affix)
        word = Word(
            concept_id=new_concept_id,
            segments=copy.deepcopy(left.segments) + copy.deepcopy(right.segments),
            origin_year=state.year,
            frequency=root.frequency * 0.5,
            morpheme_boundaries={len(left.segments)},
            parent_word_id=root.id,
            origin_type="derived",
            origin_rule="affixation",
        )
        state.lexicon.words.append(word)
        return word

    def level_analogies(self, state: State, threshold: float = 0.75) -> int:
        """Vyrovná nejisté afixální alternace podle nejčastějšího paradigmatu.

        Není to generativní morfologie celé přirozené řeči: jde o konzervativní
        krok, který kopíruje afix z nejfrekventovanějšího členěného slova do
        méně frekventních členů stejné orientace. Tím opravuje část
        nepravidelností vytvořených předchozí fonologií, aniž by mazal kořen.
        """
        changed = 0
        paradigms: Dict[str, list[Word]] = {}
        for word in state.lexicon.words:
            if word.active and word.paradigm and word.morpheme_boundaries:
                paradigms.setdefault(word.paradigm, []).append(word)

        for members in paradigms.values():
            if len(members) < 2:
                continue
            model = max(members, key=lambda word: word.frequency)
            boundary = min(model.morpheme_boundaries)
            model_affix = (
                model.segments[:boundary]
                if state.affixation_strategy == "prefix"
                else model.segments[boundary:]
            )
            for word in members:
                if word is model or word.frequency >= threshold:
                    continue
                split = min(word.morpheme_boundaries)
                root = (
                    word.segments[split:]
                    if state.affixation_strategy == "prefix"
                    else word.segments[:split]
                )
                word.segments = (
                    copy.deepcopy(model_affix) + root
                    if state.affixation_strategy == "prefix"
                    else root + copy.deepcopy(model_affix)
                )
                word.morpheme_boundaries = {
                    len(model_affix) if state.affixation_strategy == "prefix" else len(root)
                }
                word.ensure_stress()
                changed += 1
        return changed

    def inflect(
        self,
        state: State,
        stem_id: str,
        paradigm_id: str,
        forms: Iterable[Dict[str, object]],
    ) -> list[Word]:
        """Vytvoří časované tvary paradigmatu z lexikalizovaných afixů.

        Konfigurace drží explicitní identifikátory afixů místo nečitelných
        řetězcových koncovek, takže i afix může mít vlastní dějiny a projít
        zvukovou změnou před gramatikalizací.
        """
        stem = state.lexicon.get_word(stem_id)
        if stem is None:
            return []
        created: list[Word] = []
        for form in forms:
            form_id = str(form.get("id", ""))
            affix_id = str(form.get("affix", ""))
            if not form_id or not affix_id or state.lexicon.get_word(form_id):
                continue
            affix = state.lexicon.get_word(affix_id)
            if affix is None:
                continue
            prefix = bool(form.get("prefix", state.affixation_strategy == "prefix"))
            left, right = (affix, stem) if prefix else (stem, affix)
            word = Word(
                concept_id=form_id,
                segments=copy.deepcopy(left.segments) + copy.deepcopy(right.segments),
                origin_year=state.year,
                frequency=stem.frequency * 0.45,
                morpheme_boundaries={len(left.segments)},
                parent_word_id=stem.id,
                origin_type="inflected",
                origin_rule=f"paradigm:{paradigm_id}",
                paradigm=paradigm_id,
                grammatical_features={
                    str(k): str(v)
                    for k, v in cast(dict[str, str], form.get("features", {})).items()
                },
            )
            state.lexicon.words.append(word)
            created.append(word)
        return created

    def grammaticalize(self, state: State, word_id: str) -> bool:
        """Označí samostatné slovo jako gramatický morfém pro budoucí derivaci."""
        word = state.lexicon.get_word(word_id)
        if word is None:
            return False
        word.is_grammatical = True
        word.origin_rule = word.origin_rule or "grammaticalization"
        word.frequency = min(1.0, word.frequency + 0.15)
        return True

    def reanalyze_boundaries(self, state: State, paradigm_id: Optional[str] = None) -> int:
        """Posune nestabilní hranici o jeden segment k produktivnímu afixu."""
        words = [
            word
            for word in state.lexicon.words
            if word.morpheme_boundaries and (paradigm_id is None or word.paradigm == paradigm_id)
        ]
        if not words:
            return 0
        changed = 0
        for word in words:
            boundary = min(word.morpheme_boundaries)
            if state.affixation_strategy == "prefix" and boundary > 1:
                word.morpheme_boundaries = {boundary - 1}
                changed += 1
            elif state.affixation_strategy != "prefix" and boundary < len(word.segments) - 1:
                word.morpheme_boundaries = {boundary + 1}
                changed += 1
        return changed
