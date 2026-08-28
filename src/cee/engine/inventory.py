"""
Pohled na fonologický inventář jako na dotazovatelnou množinu přirozených tříd.

Podle CEE_master.md 4.3 je cílová třída pravidla *dotaz do aktuálního
inventáře* — pravidlo mířící na prázdnou třídu se nemá vůbec vygenerovat.
`Inventory` v core.models drží jen IPA řetězce, takže na rysové dotazy
nestačí; tahle třída k nim přidává rysové matice z panphonu.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterable, List

from cee.core.models import Inventory, Lexicon, Segment

if TYPE_CHECKING:  # pragma: no cover
    from cee.engine.phonology import FeatureMapper


class InventoryView:
    """Inventář, kterého se lze ptát na obsazenost přirozené třídy."""

    def __init__(self, mapper: "FeatureMapper", segments: Iterable[str] = ()):
        self._mapper = mapper
        self._features: Dict[str, Dict[str, str]] = {}

        for ipa in segments:
            if not ipa or ipa == "?":
                continue
            parsed = mapper.parse_word("_", ipa).segments
            # Vícesegmentové řetězce do inventáře fonémů nepatří.
            if len(parsed) == 1:
                self._features[ipa] = parsed[0].features

    @classmethod
    def from_lexicon(cls, lexicon: Lexicon, mapper: "FeatureMapper") -> "InventoryView":
        segments = {
            mapper.segment_to_ipa(segment)
            for word in lexicon.words
            for segment in word.segments
        }
        return cls(mapper, segments)

    @classmethod
    def from_inventory(cls, inventory: Inventory, mapper: "FeatureMapper") -> "InventoryView":
        return cls(mapper, inventory.segments)

    def to_inventory(self) -> Inventory:
        return Inventory(segments=set(self._features))

    def matching(self, target: Dict[str, str]) -> List[str]:
        """
        Vrátí fonémy spadající do dané přirozené třídy.

        Klíče začínající podtržítkem jsou řídicí (např. `_boundary` označuje
        hranici slova, ne rys segmentu) a do porovnání nevstupují.
        """
        bundle = {k: v for k, v in target.items() if not k.startswith("_")}
        if not bundle:
            return sorted(self._features)

        probe = Segment(features={})
        found = []
        for ipa, features in self._features.items():
            probe.features = features
            if probe.matches(bundle):
                found.append(ipa)
        return sorted(found)

    def has(self, target: Dict[str, str]) -> bool:
        """True, pokud je třída v inventáři neprázdná."""
        return bool(self.matching(target))

    def has_all(self, *targets: Dict[str, str] | None) -> bool:
        """
        True, pokud je neprázdná každá zadaná třída. `None` se přeskakuje,
        stejně jako čistě hraniční prostředí — hranice slova existuje vždy.
        """
        for target in targets:
            if target is None:
                continue
            if not any(not k.startswith("_") for k in target):
                continue
            if not self.has(target):
                return False
        return True

    def apply(self, rule) -> "InventoryView":
        """
        Vrátí inventář po aplikaci pravidla — bez sahání na lexikon.

        Slouží generátoru, aby při skládání chronologie věděl, co v jazyce
        po každé změně existuje (CEE_master.md 4.3, stavový fold).

        Model je záměrně konzervativní:
        - mazací pravidlo inventář nemění; zda foném zanikne, závisí na
          pozicích ve slovech, a ty inventář nezná;
        - nové fonémy se přidají vždy;
        - staré se odeberou jen u pravidla bez prostředí, protože jinak se
          původní hláska jinde ve slově udrží.
        """
        if rule.action.get("delete") == "+":
            return self

        affected = self.matching(rule.target)
        if not affected:
            return self

        unconditional = not rule.env_before and not rule.env_after
        segments = set(self._features)

        for ipa in affected:
            shifted = Segment(features={**self._features[ipa], **rule.action})
            new_ipa = self._mapper.segment_to_ipa(shifted)
            if not new_ipa or new_ipa == "?":
                continue
            segments.add(new_ipa)
            if unconditional and new_ipa != ipa:
                segments.discard(ipa)

        return InventoryView(self._mapper, segments)

    def __contains__(self, ipa: str) -> bool:
        return ipa in self._features

    def __iter__(self):
        return iter(sorted(self._features))

    def __len__(self) -> int:
        return len(self._features)

    def __bool__(self) -> bool:
        return bool(self._features)

    def __repr__(self) -> str:
        return f"InventoryView({' '.join(sorted(self._features))})"
