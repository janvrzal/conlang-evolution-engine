import csv
import json
import os
import networkx as nx
from pathlib import Path

def build_graph_from_datsemshift(cldf_path: str, out_path: str):
    """
    Načte parameters.csv z DatSemShift CLDF a vybuduje NetworkX DiGraph.
    """
    print(f"Stavím graf ze zdroje: {cldf_path}")
    
    G = nx.DiGraph()
    
    # 1. Průchod: Získat mapování ID -> Concepticon_ID a vytvořit uzly
    id_to_concepticon = {}
    
    with open(cldf_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            local_id = row['ID']
            conc_id = row.get('Concepticon_ID', '').strip()
            name = row.get('Name', '').strip()
            
            if conc_id:
                id_to_concepticon[local_id] = conc_id
                # Přidáme uzel do grafu, pokud ještě není
                if not G.has_node(conc_id):
                    G.add_node(conc_id, name=name)
            else:
                id_to_concepticon[local_id] = local_id
                if not G.has_node(local_id):
                    G.add_node(local_id, name=name)
                    
    # 2. Průchod: Vytvořit hrany
    with open(cldf_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            source_local_id = row['ID']
            source_id = id_to_concepticon[source_local_id]
            
            # Sémantické posuny (orientované)
            target_json = row.get('Target_Concepts', '[]')
            if target_json:
                try:
                    targets = json.loads(target_json)
                    for t in targets:
                        target_local_id = t.get('ID')
                        if target_local_id and target_local_id in id_to_concepticon:
                            target_id = id_to_concepticon[target_local_id]
                            # Zjistíme počet jazykových rodin jako váhu
                            weight = int(t.get('PolysemyByFamily', 1)) + int(t.get('DerivationByFamily', 0))
                            if weight == 0: weight = 1
                            
                            # Přidáme orientovanou hranu
                            if G.has_edge(source_id, target_id):
                                G[source_id][target_id]['weight'] += weight
                            else:
                                G.add_edge(source_id, target_id, weight=weight, type='shift')
                except json.JSONDecodeError:
                    pass
                    
            # Kolexifikace (obousměrné) - používáno v Linked_Concepts
            linked_json = row.get('Linked_Concepts', '[]')
            if linked_json:
                try:
                    links = json.loads(linked_json)
                    for link in links:
                        link_local_id = link.get('ID')
                        if link_local_id and link_local_id in id_to_concepticon:
                            link_id = id_to_concepticon[link_local_id]
                            weight = int(link.get('PolysemyByFamily', 1)) + int(link.get('DerivationByFamily', 0))
                            if weight == 0: weight = 1
                            
                            # Obousměrná hrana (přidáme obě orientace)
                            for s, t in [(source_id, link_id), (link_id, source_id)]:
                                if G.has_edge(s, t):
                                    G[s][t]['weight'] += weight
                                else:
                                    G.add_edge(s, t, weight=weight, type='colexification')
                except json.JSONDecodeError:
                    pass
                    
    print(f"Graf byl úspěšně postaven.")
    print(f"  Uzly (Koncepty): {G.number_of_nodes()}")
    print(f"  Hrany (Posuny/Kolexifikace): {G.number_of_edges()}")
    
    # Uložíme jako graphml
    nx.write_graphml(G, out_path)
    print(f"Graf byl uložen do {out_path}")

if __name__ == "__main__":
    home = str(Path.home())
    cldf_path = os.path.join(home, ".cee", "data", "datsemshift", "cldf", "parameters.csv")
    out_dir = os.path.join(home, ".cee", "semantics")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "graph.graphml")
    
    if os.path.exists(cldf_path):
        build_graph_from_datsemshift(cldf_path, out_path)
    else:
        print(f"Chyba: Nebyl nalezen soubor datsemshift: {cldf_path}")
