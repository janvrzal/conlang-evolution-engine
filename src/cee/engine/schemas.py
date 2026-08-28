import random
from typing import Optional
from dataclasses import dataclass
from cee.core.models import Inventory
from cee.engine.rules import Rule

class Schema:
    """Základní třída pro šablony zvukových změn."""
    def __init__(self, name: str):
        self.name = name

    def generate_rule(self, inventory: Inventory, year: int) -> Optional[Rule]:
        """
        Pokusí se vytvořit konkrétní pravidlo z této šablony pro daný inventář.
        Pokud to není možné (např. chybí cílové hlásky), vrátí None.
        """
        raise NotImplementedError()


class LenitionSchema(Schema):
    """Změkčování souhlásek, např. ptk -> bdg mezi samohláskami."""
    def __init__(self):
        super().__init__("lenition")
        
    def generate_rule(self, inventory: Inventory, year: int) -> Optional[Rule]:
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
        
    def generate_rule(self, inventory: Inventory, year: int) -> Optional[Rule]:
        return Rule(
            name=f"Fortice (gen. v {year})",
            target={"cons": "+", "voi": "+", "cont": "+"},  # Znělé frikativy
            action={"cont": "-"},                          # Stanou se okluzivami
            env_before={"_boundary": "+"},                 # Na začátku slova
            year=year
        )

class SyncopeSchema(Schema):
    """Ztráta nepřízvučných samohlásek (zkracování slov)."""
    def __init__(self):
        super().__init__("syncope")
        
    def generate_rule(self, inventory: Inventory, year: int) -> Optional[Rule]:
        return Rule(
            name=f"Synkopa (gen. v {year})",
            target={"syl": "+"},     # Všechny samohlásky (mělo by být nepřízvučné, ale zjednodušujeme)
            action={"delete": "+"},
            env_before={"syl": "+", "cons": "+"}, # V kontextu VC_CV (velmi hrubé zjednodušení)
            env_after={"cons": "+", "syl": "+"},
            year=year
        )

class CodaLossSchema(Schema):
    """Ztráta koncových souhlásek."""
    def __init__(self):
        super().__init__("coda_loss")
        
    def generate_rule(self, inventory: Inventory, year: int) -> Optional[Rule]:
        return Rule(
            name=f"Ztráta kody (gen. v {year})",
            target={"cons": "+"},
            action={"delete": "+"},
            env_after={"_boundary": "+"},
            year=year
        )

SCHEMA_REGISTRY = {
    "lenition": LenitionSchema(),
    "fortition": FortitionSchema(),
    "syncope": SyncopeSchema(),
    "coda_loss": CodaLossSchema()
}
