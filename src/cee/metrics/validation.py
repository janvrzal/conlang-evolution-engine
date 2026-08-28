import csv
import lingpy
from typing import Dict
from cee.core.models import Lexicon
from cee.engine.phonology import FeatureMapper

class ValidationMetric:
    @staticmethod
    def evaluate(generated_lexicon: Lexicon, ground_truth_csv: str, mapper: FeatureMapper) -> Dict[str, float]:
        """
        Porovná vygenerovaný slovník proti referenčnímu Ground Truth slovníku.
        Vrací průměrnou fonetickou editační vzdálenost.
        """
        
        # Načtení ground truth cílů (ID -> IPA)
        ground_truth = {}
        with open(ground_truth_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ground_truth[row['id']] = row['ipa_target']
                
        total_distance = 0.0
        comparisons = 0
        exact_matches = 0
        
        for word in generated_lexicon.words:
            if word.concept_id in ground_truth:
                generated_ipa = mapper.render_word(word)
                target_ipa = ground_truth[word.concept_id]
                
                # LingPy normalizovaná editační vzdálenost (0.0 = perfektní shoda)
                dist = lingpy.edit_dist(generated_ipa, target_ipa, normalized=True)
                total_distance += dist
                comparisons += 1
                
                if generated_ipa == target_ipa:
                    exact_matches += 1
                    
        if comparisons == 0:
            return {"avg_edit_distance": 1.0, "exact_match_ratio": 0.0, "comparisons": 0}
            
        return {
            "avg_edit_distance": total_distance / comparisons,
            "exact_match_ratio": exact_matches / comparisons,
            "comparisons": comparisons
        }
