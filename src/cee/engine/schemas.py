import random
from typing import Optional
from dataclasses import dataclass
from cee.core.models import Inventory
from cee.engine.rules import Rule

class Schema:
    """Základní třída pro šablony zvukových změn."""
    def __init__(self, name: str):
        self.name = name

    def generate_rule(self, inventory: Inventory, year: int, rng=None) -> Optional[Rule]:
        """
        Pokusí se vytvořit konkrétní pravidlo z této šablony pro daný inventář.
        Pokud to není možné (např. chybí cílové hlásky), vrátí None.

        :param rng: seedovaný random.Random pro schémata s více variantami.
                    None = deterministicky první varianta.
        """
        raise NotImplementedError()


class LenitionSchema(Schema):
    """Změkčování souhlásek, např. ptk -> bdg mezi samohláskami."""
    def __init__(self):
        super().__init__("lenition")
        
    def generate_rule(self, inventory: Inventory, year: int, rng=None) -> Optional[Rule]:
        # Pro zjednodušení V1 vytvoříme fixní pravidlo, později by zde probíhala 
        # analýza inventáře (zda v něm je vůbec co lenitovat).
        return Rule(
            name=f"Lenice (gen. v {year})",
            target={"cons": "+", "cont": "-", "voi": "-"},  # Neznělé okluzivy
            action={"voi": "+"},                           # Znělost
            env_before={"syl": "+"},                       # Mezi samohláskami
            env_after={"syl": "+"},
            year=year
        )

class FortitionSchema(Schema):
    """Zpevňování souhlásek, např. na začátku slov."""
    def __init__(self):
        super().__init__("fortition")
        
    def generate_rule(self, inventory: Inventory, year: int, rng=None) -> Optional[Rule]:
        # Kromě [cont] je nutné shodit i [strid]: panphon má /v/ a /z/ jako
        # [+strid], zatímco /b/ a /d/ jsou [-strid]. Bez toho vznikne matice,
        # kterou mapper nedokáže přeložit a tiše ji nahradí nesmyslem.
        return Rule(
            name=f"Fortice (gen. v {year})",
            target={"cons": "+", "voi": "+", "cont": "+"},  # Znělé frikativy
            action={"cont": "-", "strid": "-"},            # Stanou se okluzivami
            env_before={"_boundary": "+"},                 # Na začátku slova
            year=year
        )

class SyncopeSchema(Schema):
    """Ztráta nepřízvučných samohlásek uvnitř slova (zkracování slov)."""
    def __init__(self):
        super().__init__("syncope")
        
    def generate_rule(self, inventory: Inventory, year: int, rng=None) -> Optional[Rule]:
        # Samohláska mezi dvěma souhláskami (kontext C_C).
        #
        # POZOR na rysy: segment nemůže být zároveň [syl: +] a [cons: +] —
        # vokál je [syl: +, cons: -], konsonant [syl: -, cons: +]. Dřívější
        # verze zde měla env {"syl": "+", "cons": "+"}, což je nesplnitelná
        # podmínka, takže schéma nikdy nevygenerovalo funkční pravidlo.
        #
        # Zjednodušení: nemáme model přízvuku, takže cílíme na každý vokál
        # v C_C, nikoli jen na nepřízvučný. Okrajové pozice jsou vyloučené
        # samy — env_before/env_after vyžadují skutečný sousední segment.
        return Rule(
            name=f"Synkopa (gen. v {year})",
            target={"syl": "+"},
            action={"delete": "+"},
            env_before={"cons": "+"},
            env_after={"cons": "+"},
            year=year
        )

class CodaLossSchema(Schema):
    """Ztráta koncových souhlásek."""
    def __init__(self):
        super().__init__("coda_loss")
        
    def generate_rule(self, inventory: Inventory, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Ztráta kody (gen. v {year})",
            target={"cons": "+"},
            action={"delete": "+"},
            env_after={"_boundary": "+"},
            year=year
        )

class VowelShiftSchema(Schema):
    """
    Posun samohlásek — zvýšení (zavření) středových vokálů.

    Přední a zadní řada se musí generovat zvlášť. Panphon totiž kóduje
    zadní vokály nesymetricky: /o/ je [lab: -], ale /u/ je [lab: +], zatímco
    /e/ a /i/ se liší jen v [hi]. Jedna společná akce {"hi": "+"} proto
    přední řadu posune správně (e -> i), ale u zadní vyrobí nekonzistentní
    matici, kterou mapper nedokáže přeložit na /u/.
    """
    def __init__(self):
        super().__init__("vowel_shift")

    def generate_rule(self, inventory: Inventory, year: int, rng=None) -> Optional[Rule]:
        front = True if rng is None else rng.random() < 0.5

        if front:
            return Rule(
                name=f"Zvýšení předních středových vokálů e -> i (gen. v {year})",
                target={"syl": "+", "hi": "-", "lo": "-", "back": "-"},
                action={"hi": "+"},
                year=year
            )
        return Rule(
            name=f"Zvýšení zadních středových vokálů o -> u (gen. v {year})",
            target={"syl": "+", "hi": "-", "lo": "-", "back": "+"},
            action={"hi": "+", "lab": "+"},
            year=year
        )


SCHEMA_REGISTRY = {
    "lenition": LenitionSchema(),
    "fortition": FortitionSchema(),
    "syncope": SyncopeSchema(),
    "coda_loss": CodaLossSchema(),
    "vowel_shift": VowelShiftSchema(),
}
