"""Z běhů enginu v Rustu (run_world.py) připraví kompaktní data pro návrh aplikace.

    python prep.py BĚH_A BĚH_B VÝSTUP.json

BĚH_* jsou adresáře s world.json, tick0.json, frames.json a export.json.
Všechno, co stránka ukazuje, pochází z těchto souborů; nic se nedopočítává
mimo engine kromě popisků (české glosy, jména změn) a souhrnů po stoletích.
"""

import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SEG = json.load(open(ROOT / "src/cee/data/v2_segments.json"))["ipa"]
GRAMMAR = json.load(open(ROOT / "src/cee/data/v2_grammar.json"))

GLOSS_EXTRA = {"finish": "dokončit", "go": "jít", "have": "mít", "step": "krok", "thing": "věc", "want": "chtít"}

FAMILY = {
    "vowel_shift": "posun samohlásky", "hiatus_elision": "zánik v hiátu", "vowel_reduction": "redukce samohlásky",
    "voicing": "znělost", "spirantization": "spirantizace", "palatalization": "palatalizace", "epenthesis": "vkladná hláska",
    "syncope": "synkopa", "vowel_nasalization": "nosovost samohlásky", "secondary_palatalization": "změkčení",
    "cluster_simplification": "zjednodušení skupiny", "coda_loss": "zánik koncové souhlásky", "glide_formation": "vznik polosamohlásky",
    "delabialization": "ztráta retnosti", "debuccalization": "debukalizace", "voicing_assimilation": "spodoba znělosti",
    "labialization": "labializace", "monophthongization": "monoftongizace", "final_devoicing": "neznělost na konci",
    "tonogenesis_onset": "vznik tónu (začátek)", "intervocalic_loss": "zánik mezi samohláskami", "labial_shift": "posun ke rtům",
    "apocope": "apokopa", "diphthongization": "diftongizace", "depalatalization": "depalatalizace",
    "tonogenesis_coda": "vznik tónu (konec)", "vowel_denazalization": "ztráta nosovosti", "nasal_assimilation": "spodoba nosovek",
    "fortition": "zesílení", "tone_merger": "splynutí tónů", "tone_loss": "ztráta tónu",
}

INNOVATION_GROUP = {
    "semantic_shift": "význam", "bleaching": "význam",
    "lexical_coinage": "nová slova", "derivation": "nová slova", "compounding": "nová slova", "conversion": "nová slova",
    "back_formation": "nová slova", "lexical_borrowing": "výpůjčky",
    "extension": "analogie", "leveling": "analogie", "contamination": "analogie", "rebracketing": "analogie",
    "periphrasis": "mluvnice", "category_loss": "mluvnice", "cliticization": "mluvnice", "order_fixation": "mluvnice",
    "order_relaxation": "mluvnice", "negation_reinforcement": "mluvnice", "negation_renewal": "mluvnice",
    "stress_shift": "přízvuk", "stress_strength": "přízvuk",
}

# Události, které stránka ukazuje jednotlivě (ostatní jen jako souhrn po stoletích).
SINGLE = {
    "state", "annexation", "secession", "collapse", "language_policy", "border_policy", "lingua_franca", "standard",
    "schools", "revival", "revival_movement", "preserve", "identity", "immigration", "codification", "printing",
    "plague", "recovery", "resettlement", "trade", "prestige", "foreign_elite", "elite_assimilation", "migration",
    "conquest", "bilingualism", "nativization", "transmission_stopped", "transmission_resumed", "language_shift",
    "language_emerged", "language_split", "language_ended", "stress_rule_changed", "stress_strength_changed",
    "grammaticalized", "exapted", "refinement", "war", "epidemic", "state_collapse",
}


def seg(i: str) -> str:
    return SEG[int(i)] if i.isdigit() and int(i) < len(SEG) else i


def bundle(text: str) -> str:
    if text.startswith("{"):
        return text[1:-1].replace(",", " ")
    if text in ("V", "C"):
        return text
    return "[" + text.replace(",", " ").replace("-", "−") + "]" if text else ""


def change_label(variable: str) -> dict:
    """Čitelný popis zvukové změny z klíče procesu."""
    p = variable.split("|") + [""] * 12
    family, target, op, feats, rep, left, right, stress = p[0].removeprefix("process:"), p[1], p[2], p[3], p[4], p[5], p[6], p[7]
    src = bundle(target)
    if op == "replace":
        res = seg(rep)
    elif op == "change":
        res = bundle(feats)
    elif op == "delete":
        res = "∅"
    elif op.startswith("insert"):
        src, res = "∅", seg(rep) if rep else bundle(feats)
    else:
        res = op
    ctx = ""
    if left or right:
        ctx = f" / {bundle(left)}_{'#' if right == '#' else bundle(right)}"
    if stress:
        ctx += " (nepřízvučné)" if stress == "unstressed" else " (přízvučné)"
    if op == "insert_before" and left:
        ctx = f" / _{bundle(left)}{'#' if right == '#' else ''}"
    return {"family": FAMILY.get(family, family.replace("_", " ")), "rule": f"{src} → {res}{ctx}"}


def load(run: Path) -> dict:
    return {name: json.load(open(run / f"{name}.json")) for name in ("world", "tick0", "frames", "export")}


def compact(run: dict, concepts: list[str], with_lex: bool) -> dict:
    world, tick0, frames, export = run["world"], run["tick0"], run["frames"], run["export"]
    groups: dict[str, int] = {}
    ginfo: list[list] = []

    def gi(gid: str, territory: str | None = None, domain: str | None = None) -> int:
        if gid not in groups:
            groups[gid] = len(ginfo)
            ginfo.append([gid, territory, domain])
        elif territory and not ginfo[groups[gid]][1]:
            ginfo[groups[gid]][1], ginfo[groups[gid]][2] = territory, domain
        return groups[gid]

    lineage_ids: dict[str, int] = {}

    def li(lid: str | None) -> int | None:
        if lid is None:
            return None
        if lid not in lineage_ids:
            lineage_ids[lid] = len(lineage_ids)
        return lineage_ids[lid]

    forms: dict[str, int] = {"": 0}

    def fi(form: str) -> int:
        if form not in forms:
            forms[form] = len(forms)
        return forms[form]

    for g in tick0["groups"] + export["groups"]:
        gi(g["id"], g["territory"], g["domain"][0])
    out_frames = []
    for f in frames:
        for gid, st in f["group_state"].items():
            gi(gid, st[0], st[1][0])
        fr = {
            "y": int(f["year"]),
            "langs": {str(li(l)): [gi(g) for g in gs] for l, gs in f["languages"].items()},
            "dial": [[gi(g) for g in d] for d in f["dialects"]],
            "states": f["states"],
            "census": f["census"],
            "endo": {str(li(l)): n for l, n in f["endonyms"].items()},
            "facts": [{"g": [gi(g) for g in d["groups"]], "l": li(d["lineage"]), "regions": d["regions"],
                       "direction": d["direction"], "terrain": d["terrain"], "sole": d["sole"]} for d in f["dialect_facts"]],
            "g": {str(gi(g["id"])): [g["population"], round(g["l2_share"], 3), li(g["observed_language"])] for g in f["groups"]},
            "s": {str(gi(k)): [v[2], v[3], v[4], v[5], v[6], v[7], v[9], v[10]] for k, v in f["group_state"].items()},
            "borders": [[b["regions"][0], b["regions"][1], b["factor"]] for b in f["borders"]],
            "gram": {str(gi(k)): {fn: v[:3] for fn, v in gr.items()} for k, gr in f["grammar"].items()},
        }
        if with_lex or f is frames[-1]:
            lex, org = {}, {}
            for gid, words in f["lexicon"].items():
                k = str(gi(gid))
                lex[k] = [fi(words[c][0]) if c in words else 0 for c in concepts]
                extra = {str(i): [words[c][1], words[c][2]] for i, c in enumerate(concepts)
                         if c in words and (words[c][1] != "inherited" or words[c][3])}
                if extra:
                    org[k] = extra
            fr["lex"], fr["org"] = lex, org
        out_frames.append(fr)

    # Linie: z exportu (i vymřelé), jméno z exportu nebo poslední známé ze snímků.
    last_endo: dict[str, str] = {}
    for f in frames:
        for l, n in f["endonyms"].items():
            if n:
                last_endo[l] = n
    lineages = []
    for l in export["lineages"]:
        lineages.append({"i": li(l["id"]), "parent": li(l["parent"]), "start": l["start_year"], "end": l["end_year"],
                         "endonym": l["endonym"] or last_endo.get(l["id"]), "origin": l["origin_region"],
                         "groups0": [gi(g) for g in l["groups_at_start"]]})

    # Linie skupiny v roce: nejbližší snímek v roce události nebo po něm.
    years = [int(f["year"]) for f in frames]
    lin_of = [{g: li(l) for l, gs in f["languages"].items() for g in gs} for f in frames]

    def lineage_at(group: str, year: float) -> int | None:
        for k, y in enumerate(years):
            if y >= year and group in lin_of[k]:
                return lin_of[k][group]
        return lin_of[-1].get(group)

    sound = collections.defaultdict(dict)
    analogy = collections.defaultdict(lambda: collections.Counter())
    analogy_examples = collections.defaultdict(list)
    century = collections.defaultdict(collections.Counter)
    singles = []
    for ev in export["events"]:
        kind, year = ev["kind"], ev["year"]
        c = int(year // 100) * 100
        if kind == "phonologized":
            lin = lineage_at(ev["group"], year)
            item = sound[lin].setdefault(ev["variable"], {"first": year, "groups": set()})
            item["groups"].add(ev["group"])
            century[c]["zvuky"] += 1
        elif kind == "analogy":
            lin = lineage_at(ev["group"], year)
            analogy[lin][ev["operation"]] += 1
            if len(analogy_examples[lin]) < 400:
                analogy_examples[lin].append([year, ev["concept"], ev["cell"], ev["operation"]])
            century[c]["analogie"] += 1
        elif kind == "innovation":
            century[c][INNOVATION_GROUP.get(ev.get("change"), "zvuky")] += 1
        elif kind in SINGLE:
            item = {k: v for k, v in ev.items() if k not in ("tick", "readers", "pupils", "linked")}
            for key in ("lineage", "parent"):
                if key in item:
                    item[key] = li(item[key])
            for key in ("groups", "bilingual", "speakers", "revived", "fallen"):
                if key in item and isinstance(item[key], list):
                    item[key] = len(item[key])
            singles.append(item)
    sound_out = {}
    for lin, items in sound.items():
        ranked = sorted(items.items(), key=lambda kv: (-len(kv[1]["groups"]), kv[1]["first"]))[:60]
        sound_out[str(lin)] = [dict(change_label(v), first=int(d["first"]), groups=len(d["groups"])) for v, d in ranked]
    analogy_out = {str(l): {"ops": dict(c), "examples": sorted({tuple(x[1:3]): x for x in analogy_examples[l]}.values())[:24]}
                   for l, c in analogy.items()}
    return {
        "groups": ginfo, "forms": list(forms), "frames": out_frames, "lineages": lineages,
        "sound": sound_out, "analogy": analogy_out, "century": {str(k): dict(v) for k, v in sorted(century.items())},
        "events": singles, "states": export["states"], "standards": export["standards"],
    }


def main() -> None:
    a, b, out = load(Path(sys.argv[1])), load(Path(sys.argv[2])), Path(sys.argv[3])
    world, tick0 = a["world"], a["tick0"]
    concepts = sorted(tick0["lexicon"][tick0["groups"][0]["id"]])
    proto_src = Path(__file__).resolve().parents[1].parent / "prototypy" / "protojazyk.html"
    logic = re.findall(r"<script[^>]*>(.*?)</script>", proto_src.read_text(encoding="utf-8"), re.S)[-1]
    gloss = {c: cs for c, cs, _ in json.loads(re.search(r"const CONCEPTS = (\[.*?\]);", logic, re.S).group(1))}
    gloss.update(GLOSS_EXTRA)
    proto = {}
    for lang in world["languages"]:
        first = next(r["id"] for r in world["regions"] if r.get("language", world["languages"][0]["id"]) == lang["id"])
        group = f"{first}-v0"
        proto[lang["id"]] = {"lex": [tick0["lexicon"][group][c]["form"] for c in concepts],
                             "grammar": {k: v["kind"] for k, v in tick0["grammar"][group].items()}}
    data = {
        "world": world, "concepts": concepts, "gloss": {c: gloss.get(c, c) for c in concepts},
        "proto": proto, "grammar_catalog": GRAMMAR,
        "villages": [t for t in a["export"]["territories"] if t["level"] == "settlement"],
        "a": compact(a, concepts, True), "b": compact(b, concepts, True),
    }
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(out, f"{out.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
