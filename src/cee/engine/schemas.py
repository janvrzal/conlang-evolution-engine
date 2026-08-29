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

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        """
        Popíše tvar změny. Implementují potomci.

        Inventář dostávají i sem, protože vkládací schémata (epenteze,
        diftongizace) musí vybrat konkrétní hlásku, která v jazyce existuje.
        """
        raise NotImplementedError()

    def generate_rule(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        """
        Vytvoří pravidlo, pokud pro něj je v inventáři opora.

        Vrací None, když je cílová třída nebo některé z prostředí prázdné —
        takové pravidlo by se stejně nikdy nespustilo a jen by promarnilo
        místo v chronologii.
        """
        rule = self.build(inventory, year, rng)
        if rule is None:
            return None

        if not inventory.has_all(rule.target, rule.env_before, rule.env_after):
            return None

        return rule


class LenitionSchema(Schema):
    """Změkčování souhlásek, např. ptk -> bdg mezi samohláskami."""

    def __init__(self):
        super().__init__("lenition")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
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

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
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

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        # Samohláska mezi dvěma souhláskami (kontext C_C). Okrajové pozice
        # vypadnou samy — env vyžaduje skutečného souseda.
        target, popis = self._VARIANTS[0] if rng is None else rng.choice(self._VARIANTS)
        return Rule(
            name=f"Synkopa {popis} vokálů (gen. v {year})",
            target=dict(target),
            action={"delete": "+"},
            env_before={"cons": "+"},
            env_after={"cons": "+"},
            prosody="unstressed",
            year=year,
        )


class CodaLossSchema(Schema):
    """Ztráta koncových souhlásek."""

    def __init__(self):
        super().__init__("coda_loss")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
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

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
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


class EpenthesisSchema(Schema):
    """
    Vkládání vokálu do souhláskového shluku (CC -> CVC).

    Protiváha erozi: bez schémat, která slovo prodlužují, se lexikon nutně
    scvrkává do shluků souhlásek, protože synkopa a ztráta kody umí jen ubírat.
    """

    def __init__(self):
        super().__init__("epenthesis")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        # Vkládá se hláska, kterou jazyk skutečně má — epentetický vokál
        # cizí celému inventáři by byl nepravděpodobný.
        vokal = inventory.pick({"syl": "+", "hi": "+"}, rng) or inventory.pick({"syl": "+"}, rng)
        if not vokal:
            return None

        features = inventory.features_of(vokal)
        if not features:
            return None

        return Rule(
            name=f"Epenteze /{vokal}/ v souhláskovém shluku (gen. v {year})",
            target={"cons": "+"},
            action={},
            env_after={"cons": "+"},
            insert="after",
            insert_features=features,
            insert_label=vokal,
            year=year,
        )


class DiphthongizationSchema(Schema):
    """
    Rozpad dlouhého/středového vokálu na dvojhlásku (V -> Vj, Vw).

    Druhá protiváha erozi, tentokrát ve vokalismu.
    """

    def __init__(self):
        super().__init__("diphthongization")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        # Za středový vokál se přidá vysoký — tak vznikají dvojhlásky typu ai, au.
        klouzavy = inventory.pick({"syl": "+", "hi": "+"}, rng)
        if not klouzavy:
            return None

        features = inventory.features_of(klouzavy)
        if not features:
            return None

        return Rule(
            name=f"Diftongizace středových vokálů na /{klouzavy}/ (gen. v {year})",
            target={"syl": "+", "hi": "-", "lo": "-"},
            action={},
            env_after={"cons": "+"},
            insert="after",
            insert_features=features,
            insert_label=klouzavy,
            year=year,
        )


class UnconditionalFricatizationSchema(Schema):
    """Nepodmíněná frikativizace jedné řady okluziv (typ Grimmova zákona)."""

    # Jediná akce nemůže beze zbytku převést všechny řady okluziv: /p/ a /t/
    # potřebují navíc [+strid] (/f/, /s/), velární /k/ ne (/x/). Volíme proto
    # jeden konkrétní, ale v celém lexikonu nepodmíněný historický zákon.
    _VARIANTS = (
        ("p", "f", {"cont": "+", "strid": "+"}),
        ("t", "s", {"cont": "+", "strid": "+"}),
        ("k", "x", {"cont": "+"}),
    )

    def __init__(self):
        super().__init__("unconditional_fricatization")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        variants = [variant for variant in self._VARIANTS if variant[0] in inventory]
        if not variants:
            return None
        source, target, action = variants[0] if rng is None else rng.choice(variants)
        source_features = inventory.features_of(source)
        assert source_features is not None  # platí díky filtru `source in inventory`
        return Rule(
            name=f"Plošná frikativizace /{source}/ → /{target}/ (gen. v {year})",
            # Kompletní matice zdroje brání tomu, aby /p/ → /f/ omylem změnilo
            # také /k/ na neexistující nebo nechtěnou frikativu.
            target=source_features,
            action=action,
            year=year,
        )

class UnconditionalDevoicingSchema(Schema):
    """Plošná ztráta znělosti u okluziv."""

    def __init__(self):
        super().__init__("unconditional_devoicing")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Plošná ztráta znělosti (gen. v {year})",
            target={"cons": "+", "son": "-", "cont": "-", "voi": "+"},
            action={"voi": "-"},
            year=year,
        )

class UnconditionalVowelLoweringSchema(Schema):
    """Plošné snížení vysokých samohlásek (i, u) na středové (e, o)."""

    def __init__(self):
        super().__init__("unconditional_vowel_lowering")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Plošné snížení vysokých vokálů (gen. v {year})",
            target={"syl": "+", "hi": "+"},
            # Panphon rozlišuje /u/ a /o/ i rysovou hodnotou [lab]. Bez
            # tohoto přepnutí vznikla neplatná matice, kterou mapper vykreslil
            # jako tónovou značku místo samohlásky.
            action={"hi": "-", "lo": "-", "lab": "-"},
            year=year,
        )


class FinalDevoicingSchema(Schema):
    """Finální ztráta znělosti u obstruentů."""
    def __init__(self):
        super().__init__("final_devoicing")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Finální odznělení (gen. v {year})",
            target={"cons": "+", "son": "-"},
            action={"voi": "-"}, env_after={"_boundary": "+"}, year=year,
        )


class UmlautSchema(Schema):
    """Přední vokál táhne předcházející samohlásku dopředu (umlaut)."""
    def __init__(self):
        super().__init__("umlaut")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Umlaut před vysokým předním vokálem (gen. v {year})",
            target={"syl": "+", "back": "+"}, action={"back": "-", "lab": "-"},
            env_after={"_lookahead_vowel": "+", "syl": "+", "hi": "+", "back": "-"}, year=year,
        )


class NasalizationSchema(Schema):
    """Nazalizace vokálu před nosovkou."""
    def __init__(self):
        super().__init__("nasalization")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Nazalizace před nosovkou (gen. v {year})",
            target={"syl": "+"}, action={"nas": "+"},
            env_after={"cons": "+", "nas": "+"}, year=year,
        )


class MonophthongizationSchema(Schema):
    """Ztráta druhé části jednoduché dvojhlásky Vj/Vw."""
    def __init__(self):
        super().__init__("monophthongization")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Monoftongizace (gen. v {year})",
            target={"syl": "+", "hi": "+"}, action={"delete": "+"},
            env_before={"cons": "+"}, prosody="unstressed", year=year,
        )


class ApocopeSchema(Schema):
    """Samostatná ztráta nepřízvučné koncové samohlásky."""
    def __init__(self):
        super().__init__("apocope")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Apokopa nepřízvučného vokálu (gen. v {year})",
            target={"syl": "+"}, action={"delete": "+"}, prosody="unstressed",
            env_after={"_boundary": "+"}, year=year,
        )


class AssimilationSchema(Schema):
    """Regresivní asimilace znělosti před další obstruentou."""
    def __init__(self):
        super().__init__("assimilation")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Asimilace znělosti před sonantou (gen. v {year})",
            target={"cons": "+", "son": "-"}, action={"voi": "$after:voi"},
            env_after={"syl": "+"}, year=year,
        )


class PalatalizationSchema(Schema):
    """Fronting okluzivy před /i/; vybírá jen dvojici existující v inventáři."""
    def __init__(self):
        super().__init__("palatalization")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        source, target = next(((a, b) for a, b in (("t", "s"), ("k", "t"), ("ɡ", "d")) if a in inventory and b in inventory), (None, None))
        if not source or not target:
            return None
        source_features = inventory.features_of(source)
        target_features = inventory.features_of(target)
        assert source_features and target_features
        action = {feature: value for feature, value in target_features.items() if source_features.get(feature) != value}
        return Rule(
            name=f"Palatalizace /{source}/ před /i/ (gen. v {year})",
            target=source_features, action=action,
            env_after={"_lookahead_vowel": "+", "syl": "+", "hi": "+", "back": "-"}, year=year,
        )


class IntervocalicSpirantizationSchema(Schema):
    """Intervokalická spirantizace okluziv."""
    def __init__(self):
        super().__init__("intervocalic_spirantization")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Intervokalická spirantizace (gen. v {year})",
            target={"cons": "+", "son": "-", "cont": "-"}, action={"cont": "+"},
            env_before={"syl": "+"}, env_after={"syl": "+"}, year=year,
        )


class ProthesisSchema(Schema):
    """Protetický vokál před počátečním shlukem/okluzivou."""
    def __init__(self):
        super().__init__("prothesis")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        vowel = inventory.pick({"syl": "+"}, rng)
        features = inventory.features_of(vowel) if vowel else None
        if not features:
            return None
        return Rule(
            name=f"Protéze /{vowel}/ (gen. v {year})", target={"cons": "+"}, action={},
            env_before={"_boundary": "+"}, insert="before", insert_features=features, insert_label=vowel, year=year,
        )


class ParagogeSchema(Schema):
    """Paragoge: vokál po koncové souhlásce."""
    def __init__(self):
        super().__init__("paragoge")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        vowel = inventory.pick({"syl": "+"}, rng)
        features = inventory.features_of(vowel) if vowel else None
        if not features:
            return None
        return Rule(
            name=f"Paragoge /{vowel}/ (gen. v {year})", target={"cons": "+"}, action={},
            env_after={"_boundary": "+"}, insert="after", insert_features=features, insert_label=vowel, year=year,
        )


class GeminationSchema(Schema):
    """Geminace intervokalické souhlásky."""
    def __init__(self):
        super().__init__("gemination")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Intervokalická geminace (gen. v {year})", target={"cons": "+"}, action={},
            env_before={"syl": "+"}, env_after={"syl": "+"}, operation="geminate", year=year,
        )


class MetathesisSchema(Schema):
    """Metateze sousedních souhlásek; vhodná pro pozdní, vzácné změny."""
    def __init__(self):
        super().__init__("metathesis")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Metateze souhláskového shluku (gen. v {year})", target={"cons": "+"}, action={},
            env_after={"cons": "+"}, operation="swap_next", year=year,
        )


class CompensatoryLengtheningSchema(Schema):
    """Prodloužení vokálu před ztratitelnou koncovou souhláskou."""
    def __init__(self):
        super().__init__("compensatory_lengthening")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Kompenzační dloužení (gen. v {year})", target={"syl": "+"}, action={},
            env_after={"cons": "+"}, operation="lengthen", year=year,
        )


class StressShiftSchema(Schema):
    """Přesun přízvuku na penultimu jako samostatná diachronní změna."""
    def __init__(self):
        super().__init__("stress_shift")

    def build(self, inventory: InventoryView, year: int, rng=None) -> Optional[Rule]:
        return Rule(
            name=f"Přesun přízvuku na penultimu (gen. v {year})", target={"syl": "+"}, action={},
            operation="stress_penult", year=year,
        )


SCHEMA_REGISTRY = {
    "lenition": LenitionSchema(),
    "fortition": FortitionSchema(),
    "syncope": SyncopeSchema(),
    "coda_loss": CodaLossSchema(),
    "vowel_shift": VowelShiftSchema(),
    "epenthesis": EpenthesisSchema(),
    "diphthongization": DiphthongizationSchema(),
    "unconditional_fricatization": UnconditionalFricatizationSchema(),
    "unconditional_devoicing": UnconditionalDevoicingSchema(),
    "unconditional_vowel_lowering": UnconditionalVowelLoweringSchema(),
    "final_devoicing": FinalDevoicingSchema(),
    "umlaut": UmlautSchema(),
    "nasalization": NasalizationSchema(),
    "monophthongization": MonophthongizationSchema(),
    "apocope": ApocopeSchema(),
    "assimilation": AssimilationSchema(),
    "palatalization": PalatalizationSchema(),
    "intervocalic_spirantization": IntervocalicSpirantizationSchema(),
    "prothesis": ProthesisSchema(),
    "paragoge": ParagogeSchema(),
    "gemination": GeminationSchema(),
    "metathesis": MetathesisSchema(),
    "compensatory_lengthening": CompensatoryLengtheningSchema(),
    "stress_shift": StressShiftSchema(),
}
