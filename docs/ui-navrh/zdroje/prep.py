"""Zhustí run.json na data pro stránku a sestaví HTML ze šablony."""

import json
import sys
from pathlib import Path

from fonts import charis

HERE = Path(__file__).parent

GLOSS = {
    "water": "voda", "fire": "oheň", "stone": "kámen", "sun": "slunce", "moon": "měsíc", "night": "noc",
    "day": "den", "mother": "matka", "father": "otec", "child": "dítě", "dog": "pes", "fish": "ryba",
    "bird": "pták", "tree": "strom", "eye": "oko", "ear": "ucho", "hand": "ruka", "heart": "srdce",
    "blood": "krev", "bone": "kost", "eat": "jíst", "drink": "pít", "die": "umřít", "come": "přijít",
    "big": "velký", "small": "malý", "black": "černý", "white": "bílý", "cold": "studený", "far": "daleko",
    "road": "cesta", "boat": "loď", "field": "pole", "house": "dům", "name": "jméno", "king": "král",
}
NAMES = {"sorrow": "Soran"}
ORIGIN = {"inherited": 0, "derivation": 1, "compound": 2, "coinage": 3}


def main() -> None:
    run = json.loads((HERE / "run.json").read_text())
    regions = {r["id"]: r for r in run["spec"]["regions"]}
    strings: list[str] = []
    index: dict[str, int] = {}

    def s(value: str) -> int:
        if value not in index:
            index[value] = len(strings)
            strings.append(value)
        return index[value]

    places = []
    for group in run["groups"]:
        if group["written"]:
            continue
        territory = next(t for t in run["territories"] if t["id"] == group["territory"])
        places.append({"id": group["id"], "region": territory["parent"],
                       "x": group["position"][0], "y": group["position"][1]})
    places.sort(key=lambda p: p["id"])
    order = [p["id"] for p in places]
    origins: dict[str, int] = {}
    forms = {}
    for concept in GLOSS:
        rows = []
        for gid in order:
            history = run["forms"][gid][concept]
            out, last = [], object()
            for entry in history:
                value = (entry[1], entry[3] if len(entry) > 3 else None) if entry[1] is not None else None
                if value == last:
                    continue
                last = value
                if value is None:
                    out.append([int(entry[0]), -1, 0])
                else:
                    origin = value[1] or "inherited"
                    origins.setdefault(origin, len(origins))
                    out.append([int(entry[0]), s(value[0]), origins[origin]])
            rows.append(out)
        forms[concept] = rows
    data = {
        "start": 0, "end": int(run["year"]), "step": 50,
        "regions": [{"id": rid, "name": NAMES.get(rid, r["name"]), "x": r["position"][0], "y": r["position"][1],
                     "terrain": r["terrain"], "identity": r["identity"]} for rid, r in regions.items()],
        "places": places,
        "gloss": GLOSS,
        "strings": strings,
        "origins": list(origins),
        "forms": forms,
        "states": [{"id": st["id"], "name": "Vardunské království", "regions": st["regions"],
                    "capital": st["capital"], "from": 700} for st in run["states"]],
        "events": [
            {"year": 700, "title": "Vardunské království", "text": "Deset západních krajů pod jedním trůnem. Hranice je zavřená."},
            {"year": 1100, "title": "Psaná norma", "text": "Písaři ve Vardunu ustálí, jak se píše. Číst umí jen vrstva u dvora."},
            {"year": 1600, "title": "Tisk a školy", "text": "Škola v každé vsi království. Norma se dostává k dětem."},
        ],
        "dialects": [[o["year"], len(o["dialects"])] for o in run["observed"]],
    }
    template = (HERE / "page.template.html").read_text()
    fonts = {name: charis(name) for name in ("Regular", "Italic")}
    page = (template.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
            .replace("__CHARIS_REGULAR__", fonts["Regular"]).replace("__CHARIS_ITALIC__", fonts["Italic"]))
    (HERE / "slovo-v-krajine.html").write_text(page)
    print(len(page) // 1024, "kB;", len(strings), "tvarů;", origins, file=sys.stderr)


if __name__ == "__main__":
    main()
