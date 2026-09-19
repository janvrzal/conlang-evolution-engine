"""
Staví kombinovaný sémantický graf z CLICS4 (kolexifikace) a DatSemShift
(orientované posuny) — CEE_master.md, sekce 4.7.

Klíčová věc, kterou obě datové sady musí sdílet, je **identita konceptu**.
CLICS4 exportuje graf s uzly klíčovanými anglickým glosem konceptu ve
velkých písmenech (např. "WORLD", "FAN (OBJECT)") — jeho GML soubor
neobsahuje žádné číselné Concepticon ID. DatSemShift naopak číselné
`Concepticon_ID` má. Bez sjednocení na společný klíč (`Concepticon_Gloss`,
což je přesně ten gloss, který CLICS4 používá) by obě sady sice sdílely
jeden `networkx.DiGraph`, ale nikdy by se jejich uzly nepotkaly — graf by byl
"kombinovaný" jen podle jména souboru.
"""

import csv
import io
import json
import os
import ssl
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict

import networkx as nx

CLICS4_URL = "https://raw.githubusercontent.com/clics/clics4/main/cldf/clics4-graph.gml.zip"


def download_clics4_graph(out_path: str) -> None:
    """Stáhne CLICS4 graf, pokud ještě neexistuje."""
    if os.path.exists(out_path):
        return

    print("Stahuji CLICS4 data...")
    ssl._create_default_https_context = ssl._create_unverified_context  # type: ignore[assignment]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    try:
        with urllib.request.urlopen(CLICS4_URL) as resp:
            data = resp.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if name.endswith(".gml"):
                    with open(out_path, "wb") as f:
                        f.write(z.read(name))
                    break
        print(f"CLICS4 graf uložen do {out_path}")
    except Exception as e:
        print(f"Chyba při stahování CLICS4: {e}")


def normalize_gloss(gloss: str) -> str:
    """
    Sjednotí zápis glosu mezi zdroji. CLICS4 uzly jsou už velkými písmeny
    (`WORLD`), DatSemShift `Concepticon_Gloss` stejně — ale ne spoléhat na
    to, že to tak zůstane i v budoucí verzi dat.
    """
    return gloss.strip().upper()


def _add_or_merge_edge(
    G: nx.DiGraph, source: str, target: str, weight: int, edge_type: str
) -> None:
    """
    Přidá hranu, nebo když už existuje, sečte váhu.

    DatSemShift hrana (`shift`) při souběhu s CLICS kolexifikací (`colexification`)
    typ přepíše na `shift` — orientovaný, doložený posun je specifičtější
    informace než symetrická kolexifikace, viz 4.7 (CLICS *neorientovaně*,
    DatSemShift *orientovaně*).
    """
    if source == target:
        return  # smyčka na sebe sama nenese žádnou informaci o posunu

    if G.has_edge(source, target):
        G[source][target]["weight"] += weight
        if edge_type == "shift":
            G[source][target]["type"] = "shift"
    else:
        G.add_edge(source, target, weight=weight, type=edge_type)


def _load_clics4(G: nx.DiGraph, clics4_path: str) -> None:
    print(f"Načítám CLICS4 ze {clics4_path}...")
    with open(clics4_path, encoding="utf-8") as f:
        G_clics = nx.parse_gml(f.read())

    for node, data in G_clics.nodes(data=True):
        # CLICS4 GML nemá číselné concepticon_id — uzel je klíčovaný přímo
        # anglickým glosem (nx.parse_gml ho vzal z GML pole `label`).
        gloss = normalize_gloss(str(node))
        if not G.has_node(gloss):
            G.add_node(gloss, name=gloss)

    for u, v, data in G_clics.edges(data=True):
        gu = normalize_gloss(str(u))
        gv = normalize_gloss(str(v))

        # Váha CLICS hrany je počet jazyků, ve kterých je kolexifikace
        # doložená (4.7) — `language_count` na hraně, ne `weight` (to pole
        # v GML vůbec neexistuje) a ne string `families` dělený dvěma, jak
        # to dřív dělal odhad tady — ten dá u typické (1-rodinné) hrany 0.
        weight = int(data.get("language_count") or 1)

        # Kolexifikace je symetrická, takže hrana jde oběma směry.
        _add_or_merge_edge(G, gu, gv, weight, "colexification")
        _add_or_merge_edge(G, gv, gu, weight, "colexification")

    print(f"CLICS4 načteno. Uzly: {G.number_of_nodes()}, Hrany: {G.number_of_edges()}")


def _concept_shift_weight(entry: Dict[str, Any]) -> int:
    """
    Váha DatSemShift hrany: součet doložení posunu i odvození, počítáno po
    rodinách (aby jedna přehnaně zdokumentovaná rodina hranu neutopila).
    """
    weight = int(entry.get("PolysemyByFamily", 1) or 0) + int(
        entry.get("DerivationByFamily", 0) or 0
    )
    return weight or 1


def _load_datsemshift(G: nx.DiGraph, datsemshift_path: str) -> None:
    print(f"Načítám DatSemShift ze {datsemshift_path}...")

    # ID -> klíč ve sdíleném grafu. Concepticon_Gloss (ne _ID!) je to, co se
    # potká s uzly z CLICS4. Bez shody zůstává koncept ve svém vlastním
    # lokálním ID — nepřipojí se k CLICS, ale v grafu zůstává použitelný.
    local_to_key: Dict[str, str] = {}

    with open(datsemshift_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            local_id = row["ID"]
            gloss = row.get("Concepticon_Gloss", "").strip()
            name = row.get("Name", "").strip()

            if gloss:
                key = normalize_gloss(gloss)
                local_to_key[local_id] = key
                if not G.has_node(key):
                    G.add_node(key, name=key)
                # Concepticon_ID se hodí jako metadata i bez shody s CLICS.
                G.nodes[key]["concepticon_id"] = row.get("Concepticon_ID", "").strip()
            else:
                local_to_key[local_id] = local_id
                if not G.has_node(local_id):
                    G.add_node(local_id, name=name or local_id)

    with open(datsemshift_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            source_key = local_to_key[row["ID"]]

            for field, edge_type in (
                ("Target_Concepts", "shift"),
                ("Linked_Concepts", "colexification"),
            ):
                try:
                    entries = json.loads(row.get(field, "[]") or "[]")
                except json.JSONDecodeError:
                    continue

                for entry in entries:
                    target_local_id = entry.get("ID")
                    if not target_local_id or target_local_id not in local_to_key:
                        continue

                    target_key = local_to_key[target_local_id]
                    weight = _concept_shift_weight(entry)

                    if edge_type == "shift":
                        _add_or_merge_edge(G, source_key, target_key, weight, "shift")
                    else:
                        # Linked_Concepts (kolexifikace v DatSemShiftu) je
                        # taky symetrická, stejně jako u CLICS.
                        _add_or_merge_edge(G, source_key, target_key, weight, "colexification")
                        _add_or_merge_edge(G, target_key, source_key, weight, "colexification")

    print("DatSemShift zpracován.")


def build_combined_semantic_graph(
    datsemshift_path: str, clics4_path: str, out_path: str
) -> nx.DiGraph:
    """
    Vybuduje kombinovaný `networkx.DiGraph` z DatSemShift (orientované posuny)
    a CLICS4 (kolexifikace) a uloží ho jako GraphML.

    Oba zdroje sdílejí uzly podle normalizovaného Concepticon glosu — to je
    jediný klíč, který CLICS4 export vůbec obsahuje.
    """
    G = nx.DiGraph()

    if os.path.exists(clics4_path):
        _load_clics4(G, clics4_path)
    else:
        print(f"CLICS4 soubor nenalezen: {clics4_path} — přeskakuji.")

    if os.path.exists(datsemshift_path):
        _load_datsemshift(G, datsemshift_path)
    else:
        print(f"DatSemShift soubor nenalezen: {datsemshift_path} — přeskakuji.")

    print("Finální graf byl úspěšně postaven.")
    print(f"  Uzly (Koncepty): {G.number_of_nodes()}")
    print(f"  Hrany (Posuny/Kolexifikace): {G.number_of_edges()}")

    if out_path:
        nx.write_graphml(G, out_path)
        print(f"Graf byl uložen do {out_path}")

    return G


def default_paths() -> Dict[str, str]:
    home = str(Path.home())
    return {
        "datsemshift_path": os.path.join(
            home, ".cee", "data", "datsemshift", "cldf", "parameters.csv"
        ),
        "clics4_path": os.path.join(home, ".cee", "data", "clics4", "clics4-graph.gml"),
        "concepticon_path": os.path.join(home, ".cee", "data", "concepticon", "concepticon.tsv"),
        "out_path": os.path.join(home, ".cee", "semantics", "graph.graphml"),
    }


if __name__ == "__main__":
    paths = default_paths()
    os.makedirs(os.path.dirname(paths["out_path"]), exist_ok=True)

    download_clics4_graph(paths["clics4_path"])
    build_combined_semantic_graph(**paths)
