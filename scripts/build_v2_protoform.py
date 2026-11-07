"""Data generátoru protojazyka (``src/cee/data/v2_protoform.json``, dok. 25).

Z ASJP (Wichmann a kol., verze v lexibank/asjp, CC BY 4.0) a WALS 12A (Maddieson 2013,
cldf-datasets/wals, CC BY 4.0) spočítá:

- četnost tříd hlásek ASJP ve slovech podle pozice (začátek, vnitřek, konec slova), a to
  *za podmínky, že jazyk třídu má* (podíl mezi souhláskami / samohláskami téže pozice
  v jazycích, kde se třída vyskytne), průměr po jazycích → rodinách → přes rodiny;
- podle slabičné stavby WALS 12A (jazyky ASJP spárované přes Glottocode): rozdělení počtu
  slabik (běhů samohlásek), podíl slov začínajících samohláskou, končících souhláskou
  a podíl slov se skupinou souhlásek na začátku a uvnitř;
- Zipfův zákon zkracování: Spearmanovo ρ mezi frekvencí pojmu (``v2_concept_frequencies``)
  a délkou slova v hláskách uvnitř jazyka; medián přes rodiny;
- inventáře hlásek z PHOIBLE (Moran a McCloy, eds., ``phoible/dev``, data CC BY 4.0): četnost
  hlásek (podíl jazyků, vážený po rodinách), Isingův model souvýskytu (pole a vazby) a velikosti
  inventářů pro kontrolu; jeden inventář na Glottocode, jen hlásky, které zná tabulka enginu;
- kontrolu dětských slov pro rodiče na WOLD (CC BY 4.0, 41 jazyků): podíl slov „matka“
  s nosovkou a slov „otec“ s retnou nebo zubnou ražnicí.

Zvuková symbolika se nepočítá: poměry rizik (RR) jsou převzaté z Blasi a kol. 2016
(PNAS 113: 10818, tab. S2 a S3), kteří pracovali se stejnými daty ASJP.

Data: ``~/.cee/data/asjp/cldf``, ``~/.cee/data/wals/cldf``, ``~/.cee/data/wold/wold-master/cldf``.
Spuštění: ``python scripts/build_v2_protoform.py`` (potřebuje numpy z extra ``data``) (zapíše JSON a vypíše přehled).
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path.home() / ".cee" / "data"
ASJP = DATA / "asjp" / "cldf"
WALS = DATA / "wals" / "cldf"
WOLD = DATA / "wold" / "wold-master" / "cldf"
PHOIBLE = DATA / "phoible"
OUT = ROOT / "src" / "cee" / "data" / "v2_protoform.json"
ASJP_COMMIT = "cf4bf0d13c95256b1b48f440d07c5c098500a770"
WALS_COMMIT = "81298aa26d01fdc11b769bcc7fa87ad9e43d7ccd"

VOWELS = set("ieE3auo")
CONSONANTS = set("pbfvmw84tdszcnrlSZCjT5ykgxNqGXh7L!")
MODIFIERS = set('*"~$')
STOPS = set("pbtdkgqGcCjT")

# Zvuková symbolika: Blasi a kol. 2016, tab. S2 (kladné) a S3 (záporné) — pojem, symbol
# ASJP, poměr rizik (výskyt symbolu ve slově pojmu / ve slovech ostatních pojmů).
BLASI = [
    ("ash", "u", 1.91), ("bite", "k", 1.69), ("bone", "k", 1.39), ("breasts", "u", 1.46),
    ("breasts", "m", 1.63), ("dog", "s", 1.76), ("ear", "k", 1.42), ("fish", "a", 1.17),
    ("full", "p", 2.11), ("full", "b", 1.91), ("hear", "N", 1.57), ("horn", "k", 1.53),
    ("horn", "r", 1.75), ("i", "5", 2.06), ("knee", "u", 1.84), ("knee", "o", 1.70),
    ("knee", "p", 1.81), ("knee", "k", 1.66), ("knee", "q", 2.30), ("leaf", "p", 1.94),
    ("leaf", "b", 1.48), ("leaf", "l", 1.75), ("name", "i", 1.25), ("nose", "u", 1.38),
    ("nose", "n", 1.47), ("one", "t", 1.49), ("one", "n", 1.29), ("red", "r", 2.24),
    ("round", "r", 2.48), ("sand", "s", 2.58), ("small", "i", 1.58), ("small", "C", 5.12),
    ("star", "z", 2.52), ("stone", "t", 1.32), ("tongue", "e", 1.54), ("tongue", "E", 1.73),
    ("tongue", "l", 2.77), ("we", "n", 1.54),
    ("bone", "y", 0.54), ("breasts", "a", 0.81), ("breasts", "h", 0.62), ("breasts", "r", 0.47),
    ("dog", "t", 0.58), ("drink", "a", 0.79), ("eye", "a", 0.80), ("i", "u", 0.44),
    ("i", "p", 0.18), ("i", "b", 0.24), ("i", "t", 0.44), ("i", "s", 0.27), ("i", "l", 0.19),
    ("i", "r", 0.35), ("name", "o", 0.67), ("name", "p", 0.40), ("nose", "a", 0.75),
    ("skin", "m", 0.53), ("skin", "n", 0.66), ("tongue", "u", 0.62), ("tongue", "k", 0.72),
    ("tooth", "b", 0.43), ("tooth", "m", 0.63), ("water", "t", 0.36), ("we", "p", 0.43),
    ("we", "l", 0.40), ("we", "s", 0.60), ("you", "u", 0.58), ("you", "o", 0.67),
    ("you", "p", 0.37), ("you", "t", 0.40), ("you", "d", 0.35), ("you", "q", 0.29),
    ("you", "s", 0.37), ("you", "r", 0.29), ("you", "l", 0.19),
]

# IPA (základní znak nebo dvojznak) → třída ASJP (Brown a kol. 2008, tab. 1–2).
IPA_TO_ASJP = {
    "p": "p", "b": "b", "f": "f", "ɸ": "f", "v": "v", "β": "v", "m": "m", "ɱ": "m",
    "w": "w", "ʋ": "w", "θ": "8", "ð": "8", "t": "t", "ʈ": "t", "d": "d", "ɖ": "d",
    "s": "s", "ʂ": "s", "z": "z", "ʐ": "z", "ts": "c", "dz": "c", "n": "n", "ɳ": "n",
    "r": "r", "ɾ": "r", "ɽ": "r", "ɹ": "r", "ɻ": "r", "ʀ": "r", "l": "l", "ɭ": "l",
    "ʃ": "S", "ɕ": "S", "ʒ": "Z", "ʑ": "Z", "tʃ": "C", "tɕ": "C", "dʒ": "j", "dʑ": "j",
    "c": "T", "ɟ": "T", "ɲ": "5", "j": "y", "k": "k", "ɡ": "g", "g": "g", "x": "x",
    "ɣ": "x", "ŋ": "N", "q": "q", "ɢ": "G", "χ": "X", "ʁ": "X", "ħ": "X", "ʕ": "X",
    "h": "h", "ɦ": "h", "ʔ": "7", "ɬ": "L", "ɮ": "L", "ʎ": "L", "ʟ": "L", "ɫ": "l",
    "ç": "S", "ʝ": "y", "ɰ": "w", "ʙ": "r",
    "i": "i", "ɪ": "i", "y": "i", "e": "e", "ø": "e", "ɛ": "E", "æ": "E", "œ": "E",
    "ə": "3", "ɨ": "3", "ʉ": "3", "ɜ": "3", "ɘ": "3", "ɵ": "3", "ɐ": "3", "a": "a",
    "ɑ": "a", "ɒ": "o", "u": "u", "ʊ": "u", "ɯ": "u", "o": "o", "ɔ": "o", "ɤ": "o",
    "ʌ": "o",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base(grapheme: str) -> str:
    """Základní symbol ASJP grafému (bez nosovosti, glotalizace a spřežek ``~``/``$``)."""
    core = "".join(c for c in grapheme if c not in MODIFIERS)
    if len(core) >= 2 and core[0] in "mnN" and core[1] in STOPS:
        return core[1]  # předností nosovka (nd~, mb~)
    return core[:1]


def words() -> dict[str, dict[str, list[list[str]]]]:
    """Doculect → pojem → slova (seznamy tříd ASJP)."""
    names = {r["ID"]: r["Name"].lstrip("*").lower() for r in csv.DictReader((ASJP / "parameters.csv").open())}
    found: dict[str, dict[str, list[list[str]]]] = defaultdict(lambda: defaultdict(list))
    for row in csv.DictReader((ASJP / "forms.csv").open(encoding="utf-8")):
        if row["Loan"] == "true":
            continue
        segments = [base(g) for g in row["Graphemes"].split() if g not in ("^", "$", "+")]
        segments = [s for s in segments if s in VOWELS or s in CONSONANTS]
        if segments:
            found[row["Language_ID"]][names[row["Parameter_ID"]]].append(segments)
    return found


def languages() -> dict[str, tuple[str, str]]:
    """Doculect → (Glottocode, rodina); jazyk bez rodiny je rodinou sám pro sebe."""
    out = {}
    for row in csv.DictReader((ASJP / "languages.csv").open(encoding="utf-8")):
        if row["long_extinct"] == "True":
            continue
        glottocode = row["Glottocode"] or row["ID"]
        out[row["ID"]] = (glottocode, row["Family"] or glottocode)
    return out


def nested_mean(values: dict[str, float], meta: dict[str, tuple[str, str]]) -> float | None:
    """Průměr doculect → jazyk (Glottocode) → rodina → přes rodiny."""
    by_language: dict[tuple[str, str], list[float]] = defaultdict(list)
    for doculect, value in values.items():
        by_language[meta[doculect]].append(value)
    by_family: dict[str, list[float]] = defaultdict(list)
    for (_, family), found in by_language.items():
        by_family[family].append(statistics.fmean(found))
    if not by_family:
        return None
    return statistics.fmean(statistics.fmean(v) for v in by_family.values())


def positions(word: list[str]):
    for at, segment in enumerate(word):
        if at == 0:
            yield "initial", segment
        elif at == len(word) - 1:
            yield "final", segment
        else:
            yield "medial", segment


def segment_weights(found, meta) -> dict:
    """Podíl třídy mezi souhláskami (samohláskami) pozice, v jazycích, které třídu mají."""
    shares: dict[tuple[str, str, str], dict[str, float]] = defaultdict(dict)
    for doculect, concepts in found.items():
        counts: dict[tuple[str, str], Counter] = defaultdict(Counter)
        present = set()
        for forms in concepts.values():
            for word in forms:
                present.update(word)
                for position, segment in positions(word):
                    kind = "vowels" if segment in VOWELS else "consonants"
                    counts[(kind, position)][segment] += 1
        for (kind, position), counter in counts.items():
            total = sum(counter.values())
            for segment in present:
                if (segment in VOWELS) == (kind == "vowels"):
                    shares[(kind, position, segment)][doculect] = counter[segment] / total
    out: dict = {"consonants": defaultdict(dict), "vowels": defaultdict(dict)}
    spread = []
    for (kind, position, segment), values in sorted(shares.items()):
        mean = nested_mean(values, meta)
        if mean is not None:
            out[kind][position][segment] = round(mean, 4)
        logs = [math.log(v / mean) for v in values.values() if v > 0 and mean]
        if len(logs) > 100 and position == "medial":
            spread.append(statistics.pstdev(logs))
    result = {k: dict(v) for k, v in out.items()}
    # Rozptyl mezi jazyky: medián směrodatné odchylky log podílu třídy (vnitřek slova).
    result["language_spread"] = round(statistics.median(spread), 3)
    return result


def spearman(xs: list[float], ys: list[float]) -> float | None:
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        rank = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            for k in range(i, j + 1):
                rank[order[k]] = (i + j) / 2
            i = j + 1
        return rank

    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    sx = sum((a - mx) ** 2 for a in rx) ** 0.5
    sy = sum((b - my) ** 2 for b in ry) ** 0.5
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sx * sy)


def nuclei(word: list[str]) -> int:
    count, previous = 0, False
    for segment in word:
        vowel = segment in VOWELS
        count += vowel and not previous
        previous = vowel
    return max(count, 1)


def abbreviation(found, meta) -> dict:
    freq = json.loads((ROOT / "src" / "cee" / "data" / "v2_concept_frequencies.json").read_text())
    known = {c: e["log_frequency"] for c, e in freq["concepts"].items()}
    rhos, slopes = {}, {}
    for doculect, concepts in found.items():
        pairs = [(known[c], statistics.fmean(len(w) for w in forms)) for c, forms in concepts.items() if c in known]
        if len(pairs) < 30:
            continue
        xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
        rho = spearman(xs, ys)
        if rho is None:
            continue
        rhos[doculect] = rho
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        slopes[doculect] = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    by_family: dict[str, list[float]] = defaultdict(list)
    for doculect, rho in rhos.items():
        by_family[meta[doculect][1]].append(rho)
    family_rho = [statistics.fmean(v) for v in by_family.values()]
    return {
        "spearman_mean": round(nested_mean(rhos, meta), 3),
        "spearman_family_quartiles": [round(q, 3) for q in statistics.quantiles(family_rho, n=4)],
        "negative_share_of_families": round(sum(r < 0 for r in family_rho) / len(family_rho), 3),
        "length_per_log10_frequency": round(nested_mean(slopes, meta), 3),
        "doculects": len(rhos),
        "families": len(family_rho),
    }


def syllable_types(found, meta) -> dict:
    codes = {r["ID"]: r["Name"] for r in csv.DictReader((WALS / "codes.csv").open()) if r["Parameter_ID"] == "12A"}
    glotto = {r["ID"]: r["Glottocode"] for r in csv.DictReader((WALS / "languages.csv").open(encoding="utf-8"))}
    kind_of: dict[str, str] = {}
    counts = Counter()
    for row in csv.DictReader((WALS / "values.csv").open(encoding="utf-8")):
        if row["Parameter_ID"] == "12A":
            name = codes[row["Code_ID"]]
            counts[name] += 1
            if glotto.get(row["Language_ID"]):
                kind_of[glotto[row["Language_ID"]]] = name
    stats: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for doculect, concepts in found.items():
        kind = kind_of.get(meta[doculect][0]) if doculect in meta else None
        if kind is None:
            continue
        all_words = [w for forms in concepts.values() for w in forms]
        if len(all_words) < 30:
            continue
        n = len(all_words)
        syllables = Counter(min(nuclei(w), 4) for w in all_words)
        for k in (1, 2, 3, 4):
            stats[kind][f"syllables_{k}"][doculect] = syllables[k] / n
        stats[kind]["vowel_initial"][doculect] = sum(w[0] in VOWELS for w in all_words) / n
        stats[kind]["consonant_final"][doculect] = sum(w[-1] in CONSONANTS for w in all_words) / n
        stats[kind]["initial_cluster"][doculect] = sum(
            len(w) > 1 and w[0] in CONSONANTS and w[1] in CONSONANTS for w in all_words) / n
        stats[kind]["medial_cluster"][doculect] = sum(
            any(a in CONSONANTS and b in CONSONANTS for a, b in zip(w[1:-1], w[2:-1])) for w in all_words) / n
        stats[kind]["final_cluster"][doculect] = sum(
            len(w) > 2 and w[-1] in CONSONANTS and w[-2] in CONSONANTS for w in all_words) / n
        stats[kind]["segments"][doculect] = statistics.fmean(len(w) for w in all_words)
    out = {}
    for kind, measures in stats.items():
        key = {"Simple": "simple", "Moderately complex": "moderate", "Complex": "complex"}[kind]
        out[key] = {m: round(nested_mean(v, meta), 3) for m, v in measures.items()}
        out[key]["wals_languages"] = counts[kind]
        out[key]["asjp_doculects"] = len(measures["segments"])
    return out


def parental_terms() -> dict:
    names = {r["ID"]: r["Name"] for r in csv.DictReader((WOLD / "parameters.csv").open())}
    first: dict[tuple[str, str], str] = {}
    for row in csv.DictReader((WOLD / "forms.csv").open(encoding="utf-8")):
        name = names.get(row["Parameter_ID"])
        if name in ("the mother", "the father"):
            first.setdefault((row["Language_ID"], name), row["Form"].lower())
    def share(name: str, letters: str) -> float:
        forms = [f for (_, n), f in first.items() if n == name]
        return round(sum(any(c in letters for c in f) for f in forms) / len(forms), 3)
    return {
        "languages": len({lang for lang, _ in first}),
        "mother_nasal": share("the mother", "mnɲŋñ"),
        "father_nasal": share("the father", "mnɲŋñ"),
        "father_labial_dental_stop": share("the father", "pbtdƀ"),
        "mother_labial_dental_stop": share("the mother", "pbtdƀ"),
    }


INVENTORY_SHARE = 0.02
REPLACE = {"ȵ": "ɲ", "ȶ": "c", "ȡ": "ɟ", "ȴ": "ʎ"}
CHECKS = [
    ("consonants", "ɡ", "b"), ("consonants", "d", "b"), ("consonants", "b", "ɡ"),
    ("consonants", "tʰ", "pʰ"), ("consonants", "kʰ", "pʰ"), ("consonants", "ʒ", "ʃ"),
    ("consonants", "t͡ʃ", "ʃ"), ("consonants", "ɲ", "ŋ"), ("consonants", "kʼ", "pʼ"),
    ("vowels", "ɔ", "ɛ"), ("vowels", "ɛ", "ɔ"), ("vowels", "uː", "iː"), ("vowels", "aː", "iː"),
    ("vowels", "ã", "ĩ"), ("vowels", "ũ", "ĩ"),
]


def engine_symbols() -> set[str]:
    return set(json.loads((ROOT / "src" / "cee" / "data" / "v2_segments.json").read_text())["symbols"])


def engine_phoneme(phoneme: str, known: set[str]) -> str | None:
    """Zápis hlásky PHOIBLE v tabulce enginu (NFD, oblouček u afrikát), jinak ``None``."""
    import unicodedata
    text = unicodedata.normalize("NFD", phoneme).replace("̠", "").replace("̞", "")
    text = REPLACE.get(text, text)
    if text in known:
        return text
    if len(text) >= 2 and text[0] in "tdpbkɡcɟq" and text[1] in "szʃʒɕʑçʝxɣχʁθðfvɸβpbɡ":
        tied = text[0] + "͡" + text[1:]
        if tied in known:
            return tied
    return None


ISING_L2 = 2.0
SWAP_SWEEPS = 20  # jako protoform::SWAP_SWEEPS


def initial_state(share, sizes, rng):
    """Počáteční inventáře dané velikosti: výběr bez vracení podle podílů (klíče u^(1/w))."""
    import numpy as np

    keys = rng.random((len(sizes), len(share))) ** (1.0 / share)
    order = np.argsort(-keys, axis=1)
    state = np.zeros_like(keys)
    for c, size in enumerate(sizes):
        state[c, order[c, :size]] = 1.0
    return state


def swap_step(state, field, coupling, rng):
    """Jedna výměna v každém řetězci: přítomná hláska i ven, chybějící j dovnitř (Metropolis)."""
    import numpy as np

    rows = np.arange(len(state))
    i = np.argmax(rng.random(state.shape) * state, axis=1)
    j = np.argmax(rng.random(state.shape) * (1.0 - state), axis=1)
    delta = field[j] - field[i] + (state * (coupling[j] - coupling[i])).sum(axis=1) - coupling[j, i]
    accept = rng.random(len(state)) < np.exp(np.minimum(delta, 0.0))
    state[rows[accept], i[accept]] = 0.0
    state[rows[accept], j[accept]] = 1.0
    return state


def ising(found: dict, kind: str, chosen: list[str], meta: dict) -> tuple[list[float], list[list[float]]]:
    """Log-lineární (Isingův) model přítomnosti hlásek: pole h a symetrické vazby J.

    Odhad pseudověrohodností (Besag 1975): pro každou hlásku logistická regrese její
    přítomnosti na přítomnosti ostatních (Newtonova metoda, L2 ``ISING_L2``), jazyky vážené
    1 / velikost rodiny; J = průměr (J_st + J_ts) / 2.
    """
    import numpy as np

    codes = sorted(found)
    x = np.array([[1.0 if s in found[g][kind] else 0.0 for s in chosen] for g in codes])
    family_size = Counter(meta[g][1] for g in codes)
    weight = np.array([1.0 / family_size[meta[g][1]] for g in codes])
    k = len(chosen)
    field = np.zeros(k)
    raw = np.zeros((k, k))
    for i in range(k):
        others = np.delete(x, i, axis=1)
        design = np.hstack([np.ones((len(codes), 1)), others])
        beta = np.zeros(design.shape[1])
        penalty = np.full(design.shape[1], ISING_L2)
        penalty[0] = 0.0
        for _ in range(30):
            p = 1.0 / (1.0 + np.exp(-(design @ beta)))
            gradient = design.T @ (weight * (x[:, i] - p)) - penalty * beta
            hessian = (design * (weight * p * (1 - p))[:, None]).T @ design + np.diag(penalty)
            step = np.linalg.solve(hessian, gradient)
            beta += step
            if np.abs(step).max() < 1e-6:
                break
        field[i] = beta[0]
        raw[i, np.arange(k) != i] = beta[1:]
    coupling = (raw + raw.T) / 2.0
    # Pole doladěná tak, aby vzorkování enginu (pevná velikost inventáře z PHOIBLE, výměny
    # hlásek podle Metropolise) dávalo podíly jazyků; pseudověrohodnost sama podíly silně
    # provázaného modelu nezachová.
    target = np.clip(np.array([weighted_share(found, kind, s, meta) for s in chosen]), 0.01, 0.99)
    sizes = np.array([sum(1 for s in found[g][kind] if s in set(chosen)) for g in codes])
    size_weight = weight / weight.sum()
    rng = np.random.default_rng(0)
    chains = 2000
    for _ in range(30):
        draw = np.clip(rng.choice(sizes, size=chains, p=size_weight), 1, k - 1)
        state = initial_state(target, draw, rng)
        for _ in range(SWAP_SWEEPS * int(draw.mean())):
            state = swap_step(state, field, coupling, rng)
        generated = np.clip(state.mean(axis=0), 0.005, 0.995)
        print(kind, "největší odchylka podílu", round(float(np.abs(generated - target).max()), 3), flush=True)
        field += 0.5 * (np.log(target / (1 - target)) - np.log(generated / (1 - generated)))
    return [round(float(h), 4) for h in field], [[round(float(v), 4) for v in row] for row in coupling]


def weighted_share(found: dict, kind: str, segment: str, meta: dict) -> float:
    return nested_mean({g: float(segment in inv[kind]) for g, inv in found.items()}, meta)


def inventories() -> dict:
    known = engine_symbols()
    families = {}
    for row in csv.DictReader((ASJP / "languages.csv").open(encoding="utf-8")):
        if row["Glottocode"]:
            families.setdefault(row["Glottocode"], row["Family"] or row["Glottocode"])
    found: dict[str, dict[str, set[str]]] = {}
    first: dict[str, str] = {}
    for row in csv.DictReader((PHOIBLE / "phoible.csv").open(encoding="utf-8")):
        glottocode = row["Glottocode"]
        if not glottocode or glottocode == "NA" or row["Marginal"] == "TRUE":
            continue
        if first.setdefault(glottocode, row["InventoryID"]) != row["InventoryID"]:
            continue
        kind = {"consonant": "consonants", "vowel": "vowels"}.get(row["SegmentClass"])
        symbol = engine_phoneme(row["Phoneme"], known) if kind else None
        if symbol:
            found.setdefault(glottocode, {"consonants": set(), "vowels": set()})[kind].add(symbol)
    # Zubná (◌̪) a apikální (◌̺) hláska bez prosté protějšky není kontrast, jen fonetický detail:
    # zapíše se prostě (t̪ → t), aby generované jazyky neměly diakritiku tam, kde nic nerozlišuje.
    for inv in found.values():
        for kind in ("consonants", "vowels"):
            for symbol in sorted(inv[kind]):
                plain = symbol.replace("\u032a", "").replace("\u033a", "")
                if plain != symbol and plain in known and plain not in inv[kind]:
                    inv[kind].discard(symbol)
                    inv[kind].add(plain)
    meta = {g: (g, families.get(g, g)) for g in found}
    out: dict = {"languages": len(found)}
    for kind in ("consonants", "vowels"):
        counts = Counter(s for inv in found.values() for s in inv[kind])
        share = {s: weighted_share(found, kind, s, meta) for s in counts}
        chosen = sorted((s for s, v in share.items() if v >= INVENTORY_SHARE), key=lambda s: -share[s])
        field, coupling = ising(found, kind, chosen, meta)
        out[kind] = [{"ipa": s, "share": round(share[s], 4)} for s in chosen]
        out[f"{kind}_field"] = field
        out[f"{kind}_coupling"] = coupling
    # Velikosti (souhlásky, samohlásky) z vybraných hlásek, vážené 1 / velikost rodiny.
    family_size = Counter(meta[g][1] for g in found)
    chosen_sets = {kind: {e["ipa"] for e in out[kind]} for kind in ("consonants", "vowels")}
    sizes: Counter = Counter()
    for g, inv in found.items():
        c = len(inv["consonants"] & chosen_sets["consonants"])
        v = len(inv["vowels"] & chosen_sets["vowels"])
        if c >= 6 and v >= 2:
            sizes[(c, v)] += 1.0 / family_size[meta[g][1]]
    out["sizes"] = [[c, v, round(w, 4)] for (c, v), w in sorted(sizes.items())]
    checks = []
    import unicodedata
    for kind, target, given in CHECKS:
        target, given = unicodedata.normalize("NFD", target), unicodedata.normalize("NFD", given)
        having = [inv for inv in found.values() if given in inv[kind]]
        if having:
            checks.append({"kind": kind, "segment": target, "given": given, "languages": len(having),
                           "share": round(sum(target in inv[kind] for inv in having) / len(having), 3)})
    out["checks"] = checks
    return out


def main() -> None:
    meta = languages()
    found = {d: c for d, c in words().items() if d in meta}
    result = {
        "description": "Data generátoru protojazyka (dok. 25): četnost tříd hlásek ASJP podle pozice ve "
        "slově (za podmínky, že jazyk třídu má), slabičné typy WALS 12A s měřením na slovech ASJP, Zipfův "
        "zákon zkracování, dětská slova pro rodiče a zvuková symbolika (Blasi a kol. 2016). "
        "Vytváří scripts/build_v2_protoform.py.",
        "sources": [
            {"name": "ASJP Database (lexibank/asjp, CLDF)", "citation": "Wichmann, Søren, Holman, Eric W. & Brown, "
             "Cecil H. (eds.) The ASJP Database. https://asjp.clld.org", "license": "CC BY 4.0",
             "license_url": "https://creativecommons.org/licenses/by/4.0/",
             "changes": "Odvozené souhrnné statistiky (podíly tříd hlásek podle pozice, délky slov, korelace), "
             "bez slovníků; výpůjčky a vymřelé jazyky vynechány.",
             "url": f"https://github.com/lexibank/asjp/tree/{ASJP_COMMIT}/cldf",
             "sha256": {f: sha256(ASJP / f) for f in ("forms.csv", "languages.csv", "parameters.csv")}},
            {"name": "WALS 12A Syllable Structure", "citation": "Maddieson, Ian 2013. Syllable Structure. In Dryer & "
             "Haspelmath (eds.), WALS Online (v2020.3).", "license": "CC BY 4.0",
             "license_url": "https://creativecommons.org/licenses/by/4.0/",
             "changes": "Jen zařazení jazyků do typů 12A a jejich počty, spárováno s ASJP přes Glottocode.",
             "url": f"https://github.com/cldf-datasets/wals/tree/{WALS_COMMIT}/cldf",
             "sha256": {f: sha256(WALS / f) for f in ("values.csv", "languages.csv", "codes.csv")}},
            {"name": "Blasi et al. 2016", "citation": "Blasi, Damián E., Wichmann, Søren, Hammarström, Harald, "
             "Stadler, Peter F. & Christiansen, Morten H. 2016. Sound–meaning association biases evidenced across "
             "thousands of languages. PNAS 113(39): 10818–10823, tab. S2–S3.", "license": "převzatá čísla (poměry rizik) s citací"},
            {"name": "Murdock 1959", "citation": "Murdock, George P. 1959. Cross-language parallels in parental kin "
             "terms. Anthropological Linguistics 1(9): 1–5; Jakobson, Roman 1962. Why 'mama' and 'papa'? Selected "
             "Writings I: 538–545.", "license": "převzatá čísla s citací"},
            {"name": "PHOIBLE (inventáře hlásek)", "citation": "Moran, Steven & McCloy, Daniel (eds.) PHOIBLE. "
             "https://phoible.org", "license": "CC BY 4.0 (data v phoible/dev)",
             "url": f"https://github.com/phoible/dev/tree/{(PHOIBLE / 'COMMIT').read_text().strip()}/data",
             "sha256": {"phoible.csv": sha256(PHOIBLE / "phoible.csv")},
             "license_url": "https://creativecommons.org/licenses/by/4.0/",
             "changes": "Neobsahuje inventáře jazyků, jen odvozené souhrnné statistiky: podíl jazyků s hláskou "
             "(jeden inventář na Glottocode, váženo po rodinách), parametry log-lineárního modelu souvýskytu "
             "hlásek (pole a vazby, odhad pseudověrohodností) a rozložení "
             "velikostí inventářů. Hlásky převedené do zápisu enginu (NFD, oblouček u afrikát, bez ̠ a ̞; "
             "zubná a apikální hláska bez prosté protějšky zapsaná prostě; "
             "ȵ ȶ ȡ ȴ → ɲ c ɟ ʎ), vynechané okrajové hlásky, tóny a hlásky, které tabulka enginu nezná."},
            {"name": "WOLD (kontrola dětských slov)", "citation": "Haspelmath, Martin & Tadmor, Uri (eds.) 2009. "
             "World Loanword Database.", "license": "CC BY 4.0"},
        ],
        "ipa_to_asjp": IPA_TO_ASJP,
        "segment_weights": segment_weights(found, meta),
        "syllable_types": syllable_types(found, meta),
        "abbreviation": abbreviation(found, meta),
        "parental_check": parental_terms(),
        "symbolism": [{"concept": c, "symbol": s, "risk_ratio": rr} for c, s, rr in BLASI],
        "inventory": inventories(),
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("syllable_types", "abbreviation", "parental_check")}, ensure_ascii=False, indent=1))
    inventory = result["inventory"]
    print("inventáře", inventory["languages"], "souhlásek", len(inventory["consonants"]), "samohlásek", len(inventory["vowels"]))
    print([e["ipa"] for e in inventory["consonants"]])
    print([e["ipa"] for e in inventory["vowels"]])
    print(inventory["checks"])
    print("spread", result["segment_weights"]["language_spread"])
    for kind, table in result["segment_weights"].items():
        if kind == "language_spread":
            continue
        for position, weights in table.items():
            top = sorted(weights.items(), key=lambda kv: -kv[1])[:14]
            print(kind, position, top)


if __name__ == "__main__":
    main()
