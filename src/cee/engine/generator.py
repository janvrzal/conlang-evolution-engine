import random
from typing import Dict, Any, List
from cee.core.models import State
from cee.engine.rules import Rule
from cee.engine.schemas import SCHEMA_REGISTRY

class SoundChangeGenerator:
    """
    Markovův generátor zvukových změn na základě šablon, vah a biomů.
    """
    def __init__(self, preset: Dict[str, Any], seed: int = 42):
        self.preset = preset
        self.random = random.Random(seed)
        
    def generate_rules_for_edge(self, state: State, start_year: int, end_year: int, num_rules: int = 2) -> List[Rule]:
        """
        Vygeneruje seznam pravidel pro hranu mezi start_year a end_year.
        Používá biom uložený ve state.
        """
        biome = state.map.get('biome', 'default') if hasattr(state, 'map') and state.map else None
        
        # Sestavení vah pro daný biom
        schemas = self.preset.get('schemas', {})
        biome_config = self.preset.get('biomes', {}).get(biome, {})
        modifiers = biome_config.get('modifiers', {})
        
        choices = []
        weights = []
        
        for schema_id, schema_cfg in schemas.items():
            if schema_id not in SCHEMA_REGISTRY:
                continue
                
            base_weight = schema_cfg.get('base_weight', 0)
            modifier = modifiers.get(schema_id, 1.0)
            final_weight = base_weight * modifier
            
            if final_weight > 0:
                choices.append(SCHEMA_REGISTRY[schema_id])
                weights.append(final_weight)
                
        rules = []
        if not choices:
            return rules
            
        # Generujeme pravidla rozložená v čase
        time_step = max(1, (end_year - start_year) // (num_rules + 1))
        
        for i in range(num_rules):
            year = start_year + time_step * (i + 1)
            
            # Weighted random choice
            selected_schema = self.random.choices(choices, weights=weights, k=1)[0]
            
            # Grounding: pokusíme se vytvořit pravidlo
            rule = selected_schema.generate_rule(state.inventory, year, rng=self.random)
            if rule:
                rules.append(rule)
                
        return rules
