"""
Šablony zvukových změn (CEE_master.md 4.4, vrstva 1).

Schéma není konkrétní pravidlo, ale parametrizovaná třída změny. Zda z něj
pravidlo vůbec vznikne, rozhoduje **aktuální inventář**: podle 4.3 se pravidlo
mířící na prázdnou přirozenou třídu nemá vygenerovat. Tuhle kontrolu dělá
`Schema.generate_rule` na jednom místě, potomci jen popisují tvar změny.

Pozor na rysové matice — viz AGENT.md 3.1b. Akce musí vyrobit kombinaci rysů,
která odpovídá reálné hlásce, jinak ji mapper tiše nahradí nejbližším odhadem.
"""
from typing import Optional

from cee.engine.inventory import InventoryView
from cee.engine.rules import Rule


class Schema:
    """Základní třída pro šablony zvukových změn."""

    def __init__(self, name: str):
        self.name = name

    def build(self, year: int, rng=None) -> Optional[Rule]:
        """Popíše tvar změny bez ohledu na inventář. Implementují potomci."""
        raise NotImplementedError()

    def generate_rule(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        """
        Vytvoří pravidlo, pokud pro něj je v inventáři opora.

        Vrací None, když je cílová třída nebo některé z prostředí prázdné —
        takové pravidlo by se stejně nikdy nespustilo a jen by promarnilo
        místo v chronologii.
        """
        rule = self.build(year, rng)
        if rule is None:
            return None

        if not inventory.has_all(rule.target, rule.env_before, rule.env_after):
            return None

        return rule


class LenitionSchema(Schema):
    """Změkčování souhlásek, např. ptk -> bdg mezi samohláskami."""

    def __init__(self):
        super().__init__("lenition")

    def build(self, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Lenice (gen. v {year})",
            target={"cons": "+", "son": "-", "cont": "-", "voi": "-"},  # neznělé okluzivy
            action={"voi": "+"},
            env_before={"syl": "+"},  # mezi samohláskami
            env_after={"syl": "+"},
            year=year,
        )


class FortitionSchema(Schema):
    """Zpevňování znělých frikativ na okluzivy na začátku slova."""

    def __init__(self):
        super().__init__("fortition")

    def build(self, year: int, rng=None) -> Optional[Rule]:
        # [son: -] je nutné: bez něj terč pohltí i likvidy /l/ a /r/, které
        # jsou taky [cons +, voi +, cont +], a fortice z nich udělá nesmysl.
        # [strid: -] v akci proto, že panphon má /v/ a /z/ jako [+strid],
        # kdežto /b/ a /d/ jako [-strid].
        return Rule(
            name=f"Fortice (gen. v {year})",
            target={"cons": "+", "son": "-", "voi": "+", "cont": "+"},
            action={"cont": "-", "strid": "-"},
            env_before={"_boundary": "+"},
            year=year,
        )


class SyncopeSchema(Schema):
    """Ztráta nepřízvučných samohlásek uvnitř slova (zkracování slov)."""

    def __init__(self):
        super().__init__("syncope")

    # Synkopa nezasahuje všechny vokály naráz. Bez modelu přízvuku aspoň
    # rozlišíme kvalitu: nejdřív mizí krátké vysoké vokály, teprve pak ostatní.
    # Bez tohohle rozlišení jedno pravidlo vygumovalo skoro celý vokalismus
    # a jazyk se dál neměl jak vyvíjet.
    _VARIANTS = (
        ({"syl": "+", "hi": "+"}, "vysokých"),
        ({"syl": "+", "hi": "-", "lo": "-"}, "středových"),
        ({"syl": "+", "back": "-"}, "předních"),
        ({"syl": "+", "back": "+"}, "zadních"),
    )

    def build(self, year: int, rng=None) -> Optional[Rule]:
        # Samohláska mezi dvěma souhláskami (kontext C_C). Okrajové pozice
        # vypadnou samy — env vyžaduje skutečného souseda.
        target, popis = self._VARIANTS[0] if rng is None else rng.choice(self._VARIANTS)
        return Rule(
            name=f"Synkopa {popis} vokálů (gen. v {year})",
            target=dict(target),
            action={"delete": "+"},
            env_before={"cons": "+"},
            env_after={"cons": "+"},
            year=year,
        )


class CodaLossSchema(Schema):
    """Ztráta koncových souhlásek."""

    def __init__(self):
        super().__init__("coda_loss")

    def build(self, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Ztráta kody (gen. v {year})",
            target={"cons": "+"},
            action={"delete": "+"},
            env_after={"_boundary": "+"},
            year=year,
        )


class VowelShiftSchema(Schema):
    """
    Posun samohlásek — zvýšení (zavření) středových vokálů.

    Přední a zadní řada se generují zvlášť. Panphon kóduje zadní vokály
    nesymetricky: /o/ je [lab: -], ale /u/ je [lab: +], zatímco /e/ a /i/ se
    liší jen v [hi]. Jedna společná akce {"hi": "+"} by u zadní řady vyrobila
    matici, kterou mapper nepřeloží na /u/.
    """

    def __init__(self):
        super().__init__("vowel_shift")

    def build(self, year: int, rng=None) -> Optional[Rule]:
        front = True if rng is None else rng.random() < 0.5

        if front:
            return Rule(
                name=f"Zvýšení předních středových vokálů e -> i (gen. v {year})",
                target={"syl": "+", "hi": "-", "lo": "-", "back": "-"},
                action={"hi": "+"},
                year=year,
            )
        return Rule(
            name=f"Zvýšení zadních středových vokálů o -> u (gen. v {year})",
            target={"syl": "+", "hi": "-", "lo": "-", "back": "+"},
            action={"hi": "+", "lab": "+"},
            year=year,
        )


SCHEMA_REGISTRY = {
    "lenition": LenitionSchema(),
    "fortition": FortitionSchema(),
    "syncope": SyncopeSchema(),
    "coda_loss": CodaLossSchema(),
    "vowel_shift": VowelShiftSchema(),
}
