import yaml
from typing import List, Dict, Any
from cee.engine.rules import Rule
from cee.engine.topology import EvolutionGraph, VerticalEdge, ContactEdge

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

    @staticmethod
    def parse_topology(file_path: str) -> EvolutionGraph:
        """Načte YAML konfiguraci evoluční sítě."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            
        graph = EvolutionGraph()
        
        # Parsování node_configs (např. map, biome)
        for n_data in data.get('nodes', []):
            graph.node_configs[n_data['id']] = n_data
            
        # Parsování vertical edges (a jejich vnořených pravidel)
        for v_edge in data.get('vertical_edges', []):
            rules = []
            for r_data in v_edge.get('rules', []):
                rule = Rule(
                    name=r_data['name'],
                    target=r_data['target'],
                    action=r_data['action'],
                    env_before=r_data.get('env_before'),
                    env_after=r_data.get('env_after'),
                    year=r_data.get('year')
                )
                rules.append(rule)
            graph.vertical_edges.append(VerticalEdge(
                parent_id=v_edge['parent'],
                child_id=v_edge['child'],
                rules=rules
            ))
            
        # Parsování contact edges
        for c_edge in data.get('contact_edges', []):
            graph.contact_edges.append(ContactEdge(
                year=c_edge['year'],
                source_id=c_edge['source'],
                target_id=c_edge['target'],
                volume=c_edge.get('volume', 10)
            ))
            
        return graph

    @staticmethod
    def parse_preset(file_path: str) -> Dict[str, Any]:
        """Načte YAML konfiguraci presetu (šablony a biomové modifikátory)."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            
        return {
            'name': data.get('name', 'Unknown Preset'),
            'description': data.get('description', ''),
            'schemas': data.get('schemas', {}),
            'biomes': data.get('biomes', {})
        }
