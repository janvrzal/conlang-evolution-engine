"""
Lexikální retence — metrika (A) z CEE_master.md 5.1.

Měří **náhradu**: zda význam ve slotu drží původní kořen, nebo ho obsadil nový.
Je to jiná osa než fonetická vzdálenost z `validation.py`, která měří **erozi**.
Obě je nutné počítat odděleně: `*kʷetwores` -> *čtyři* je fonologicky brutální,
ale lexikálně nulová změna.

Retence **není tvrdý cíl**. Swadeshova konstanta není konstanta — Bergsland
a Vogt to ukázali už v roce 1962 na islandštině proti kontinentální
skandinávštině. Slouží jako volné pásmo (řádově 75–95 % za tisíciletí).
"""
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from cee.core.models import Lexicon

# Volné pásmo očekávané retence za tisíciletí (5.1 A).
PLAUSIBLE_BAND_PER_MILLENNIUM = (0.75, 0.95)


@dataclass
class RetentionResult:
    """Rozpad diagnostického seznamu na zachované, vypůjčené a ztracené sloty."""

    retained: List[str]
    borrowed: List[str]
    lost: List[str]

    @property
    def total(self) -> int:
        return len(self.retained) + len(self.borrowed) + len(self.lost)

    @property
    def ratio(self) -> float:
        """Podíl slotů, které drží původní (nevypůjčený) kořen."""
        return len(self.retained) / self.total if self.total else 0.0

    def in_plausible_band(self, years: int) -> Optional[bool]:
        """
        Leží retence v očekávaném pásmu pro danou časovou hloubku?

        Vrací None pro nulovou hloubku, kde pásmo nedává smysl.
        """
        if years <= 0:
            return None

        millennia = years / 1000.0
        low, high = PLAUSIBLE_BAND_PER_MILLENNIUM
        return low**millennia <= self.ratio <= high**millennia

    def as_dict(self) -> Dict[str, object]:
        return {
            "ratio": self.ratio,
            "retained": len(self.retained),
            "borrowed": len(self.borrowed),
            "lost": len(self.lost),
            "total": self.total,
        }


class LexicalRetention:
    """
    Vyhodnocení retence proti **fixnímu** diagnostickému seznamu.

    Seznam je měřicí přístroj, ne vlastnost jazyka — musí být pro všechny
    porovnávané uzly identický a neměnný, jinak jsou hodnoty nesrovnatelné
    (5.1). Proto se předává explicitně; odvodit ho z výsledného lexikonu by
    znamenalo měřit pokaždé jiným metrem.
    """

    @staticmethod
    def diagnostic_from(lexicon: Lexicon) -> List[str]:
        """Seznam konceptů protojazyka — rozumný výchozí přístroj pro jednu rodinu."""
        return sorted({word.concept_id for word in lexicon.words})

    @staticmethod
    def evaluate(derived: Lexicon, diagnostic: Iterable[str]) -> RetentionResult:
        """
        Roztřídí sloty diagnostického seznamu podle toho, čím jsou obsazené.

        - **retained** — slot drží domácí slovo (bez `source_id`)
        - **borrowed** — slot drží jen výpůjčka, tedy kořen byl nahrazen
        - **lost** — slot neobsadilo nic
        """
        retained, borrowed, lost = [], [], []

        for concept in diagnostic:
            words = derived.get_words(concept)
            if any(word.source_id is None for word in words):
                retained.append(concept)
            elif words:
                borrowed.append(concept)
            else:
                lost.append(concept)

        return RetentionResult(retained=retained, borrowed=borrowed, lost=lost)

    @staticmethod
    def evaluate_family(
        branches: Dict[str, Lexicon], diagnostic: Sequence[str]
    ) -> Dict[str, RetentionResult]:
        """Retence všech větví proti témuž seznamu, aby byly navzájem srovnatelné."""
        return {
            branch_id: LexicalRetention.evaluate(lexicon, diagnostic)
            for branch_id, lexicon in branches.items()
        }
