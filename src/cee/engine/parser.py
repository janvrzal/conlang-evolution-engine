import warnings
from typing import Any, Dict, List

import yaml

from cee.engine.rules import Rule
from cee.engine.schemas import SCHEMA_REGISTRY
from cee.engine.topology import ContactEdge, EvolutionGraph, VerticalEdge


class YamlParser:
    @staticmethod
    def parse_rules(filepath: str) -> List[Rule]:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        rules = []
        for r_dict in data.get("rules", []):
            rule = Rule(
                name=r_dict["name"],
                target=r_dict["target"],
                action=r_dict["action"],
                env_before=r_dict.get("env_before"),
                env_after=r_dict.get("env_after"),
                prosody=r_dict.get("prosody"),
                syllable_part=r_dict.get("syllable_part"),
                operation=r_dict.get("operation"),
                chain_steps=r_dict.get("chain_steps"),
                chain_type=r_dict.get("chain_type"),
                harmony_direction=r_dict.get("harmony_direction"),
                harmony_domain=r_dict.get("harmony_domain"),
                harmony_features=r_dict.get("harmony_features"),
                harmony_inventory=r_dict.get("harmony_inventory"),
                tone_rotation=r_dict.get("tone_rotation"),
                tone_sandhi_map=r_dict.get("tone_sandhi_map"),
                year=r_dict.get("year"),
            )
            rules.append(rule)
        return rules

    @staticmethod
    def parse_topology(file_path: str) -> EvolutionGraph:
        """Načte YAML konfiguraci evoluční sítě."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        graph = EvolutionGraph()

        # Parsování node_configs (např. map, biome)
        for n_data in data.get("nodes", []):
            graph.node_configs[n_data["id"]] = n_data

        # Parsování vertical edges (a jejich vnořených pravidel)
        for v_edge in data.get("vertical_edges", []):
            rules = []
            for r_data in v_edge.get("rules", []):
                rule = Rule(
                    name=r_data["name"],
                    target=r_data["target"],
                    action=r_data["action"],
                    env_before=r_data.get("env_before"),
                    env_after=r_data.get("env_after"),
                    prosody=r_data.get("prosody"),
                    syllable_part=r_data.get("syllable_part"),
                    operation=r_data.get("operation"),
                    chain_steps=r_data.get("chain_steps"),
                    chain_type=r_data.get("chain_type"),
                    harmony_direction=r_data.get("harmony_direction"),
                    harmony_domain=r_data.get("harmony_domain"),
                    harmony_features=r_data.get("harmony_features"),
                    harmony_inventory=r_data.get("harmony_inventory"),
                    tone_rotation=r_data.get("tone_rotation"),
                    tone_sandhi_map=r_data.get("tone_sandhi_map"),
                    year=r_data.get("year"),
                )
                rules.append(rule)
            graph.vertical_edges.append(
                VerticalEdge(parent_id=v_edge["parent"], child_id=v_edge["child"], rules=rules)
            )

        # Parsování contact edges
        for c_edge in data.get("contact_edges", []):
            graph.contact_edges.append(
                ContactEdge(
                    year=c_edge["year"],
                    source_id=c_edge["source"],
                    target_id=c_edge["target"],
                    volume=c_edge.get("volume", 10),
                    mutual=bool(c_edge.get("mutual", False)),
                    domain=c_edge.get("domain", c_edge.get("contact_type", "neighborhood")),
                    prestige=float(c_edge.get("prestige", 1.0)),
                    calque_rate=float(c_edge.get("calque_rate", 0.0)),
                    adapt=bool(c_edge.get("adapt", False)),
                )
            )

        return graph

    @staticmethod
    def parse_preset(file_path: str) -> Dict[str, Any]:
        """Načte YAML konfiguraci presetu (šablony a biomové modifikátory)."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        preset = {
            "name": data.get("name", "Unknown Preset"),
            "description": data.get("description", ""),
            "macro": data.get("macro", {}),
            "schemas": data.get("schemas", {}),
            "biomes": data.get("biomes", {}),
        }

        # Bez schémat generátor tiše nevyrobí jediné pravidlo — typicky když se
        # jako preset omylem předá soubor s topologií.
        if not preset["schemas"]:
            warnings.warn(
                f"Preset '{file_path}' nedeklaruje žádná schémata ('schemas'). "
                f"Generátor zvukových změn nevygeneruje žádná pravidla.",
                stacklevel=2,
            )

        unknown = [s for s in preset["schemas"] if s not in SCHEMA_REGISTRY]
        if unknown:
            warnings.warn(
                f"Preset '{file_path}' odkazuje na neznámá schémata {unknown}; "
                f"budou ignorována. Známá schémata: {sorted(SCHEMA_REGISTRY)}.",
                stacklevel=2,
            )

        return preset
