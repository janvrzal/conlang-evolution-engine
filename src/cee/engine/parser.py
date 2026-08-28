import yaml
from typing import List
from cee.engine.rules import Rule

class YamlParser:
    @staticmethod
    def parse_rules(filepath: str) -> List[Rule]:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            
        rules = []
        for r_dict in data.get('rules', []):
            rule = Rule(
                name=r_dict['name'],
                target=r_dict['target'],
                action=r_dict['action'],
                env_before=r_dict.get('env_before'),
                env_after=r_dict.get('env_after')
            )
            rules.append(rule)
        return rules
