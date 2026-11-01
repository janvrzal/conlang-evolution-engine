"""Sestaví obrazovku Protojazyk: skutečný protoslovník z enginu + šablona."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import record  # noqa: E402
from fonts import charis  # noqa: E402
from cee.v2 import export  # noqa: E402
from cee.v2.spec import build  # noqa: E402

CS = {
    "i": "já", "you": "ty", "we": "my", "this": "tento", "that": "tamten", "who": "kdo", "what": "co", "not": "ne",
    "all": "všechen", "many": "mnoho", "one": "jeden", "two": "dva", "big": "velký", "long": "dlouhý", "small": "malý",
    "woman": "žena", "man": "muž", "person": "člověk", "fish": "ryba", "bird": "pták", "dog": "pes", "louse": "veš",
    "tree": "strom", "seed": "semeno", "leaf": "list", "root": "kořen", "bark": "kůra", "skin": "kůže", "flesh": "maso",
    "blood": "krev", "bone": "kost", "grease": "tuk", "egg": "vejce", "horn": "roh", "tail": "ocas", "feather": "pero",
    "hair": "vlasy", "head": "hlava", "ear": "ucho", "eye": "oko", "nose": "nos", "mouth": "ústa", "tooth": "zub",
    "tongue": "jazyk (v ústech)", "fingernail": "nehet", "foot": "chodidlo", "leg": "noha", "knee": "koleno", "hand": "ruka",
    "belly": "břicho", "neck": "krk", "breasts": "prsa", "heart": "srdce", "liver": "játra", "drink": "pít", "eat": "jíst",
    "bite": "kousat", "see": "vidět", "hear": "slyšet", "know": "vědět", "sleep": "spát", "die": "umřít", "kill": "zabít",
    "swim": "plavat", "fly": "letět", "walk": "jít", "come": "přijít", "lie": "ležet", "sit": "sedět", "stand": "stát",
    "give": "dát", "say": "říct", "sun": "slunce", "moon": "měsíc", "star": "hvězda", "water": "voda", "rain": "déšť",
    "stone": "kámen", "sand": "písek", "earth": "země", "cloud": "mrak", "smoke": "kouř", "fire": "oheň", "ash": "popel",
    "burn": "hořet", "path": "stezka", "mountain": "hora", "red": "červený", "green": "zelený", "yellow": "žlutý",
    "white": "bílý", "black": "černý", "night": "noc", "hot": "horký", "cold": "studený", "full": "plný", "new": "nový",
    "good": "dobrý", "round": "kulatý", "dry": "suchý", "name": "jméno", "father": "otec", "mother": "matka",
    "child": "dítě", "family": "rod", "house": "dům", "village": "ves", "town": "město", "road": "cesta", "river": "řeka",
    "sea": "moře", "forest": "les", "field": "pole", "wind": "vítr", "thunder": "hrom", "day": "den", "year": "rok",
    "morning": "ráno", "food": "jídlo", "grain": "obilí", "salt": "sůl", "animal": "zvíře", "horse": "kůň", "boat": "loď",
    "trade": "obchod", "king": "král", "law": "zákon", "war": "válka", "peace": "mír", "god": "bůh", "spirit": "duch",
    "ritual": "obřad", "write": "psát", "read": "číst", "speak": "mluvit", "language": "řeč", "friend": "přítel",
    "enemy": "nepřítel", "work": "práce", "make": "dělat", "carry": "nést", "open": "otevřít", "close": "zavřít",
    "near": "blízko", "far": "daleko", "old": "starý", "young": "mladý", "fast": "rychlý", "slow": "pomalý",
}


def main() -> None:
    world, _, _ = build(record.spec())
    from cee.v2.simulation import Simulation
    simulation = Simulation(world)
    for _ in simulation.iterate(25.0):
        pass
    lexicon = export.lexicon(simulation.world, "vardun-v0")
    from cee.v2.scenarios import DEFAULT_CONCEPTS
    concepts = [[c, CS[c], lexicon.get(c, {}).get("form")] for c in DEFAULT_CONCEPTS]
    missing = [c for c, _, f in concepts if not f]
    geo = [[name, x, y, t] for name, x, y, t in [(n if n != "Sorrow" else "Soran", x, y, t) for n, x, y, t in record.REGIONS]]
    font = charis()
    page = ((HERE / "proto.template.html").read_text()
            .replace("__CONCEPTS__", json.dumps(concepts, ensure_ascii=False))
            .replace("__GEO__", json.dumps(geo, ensure_ascii=False))
            .replace("__CHARIS_REGULAR__", font))
    (HERE / "protojazyk.html").write_text(page)
    print(len(page) // 1024, "kB; chybí", missing, "; ukázka", concepts[:6], file=sys.stderr)


if __name__ == "__main__":
    main()
