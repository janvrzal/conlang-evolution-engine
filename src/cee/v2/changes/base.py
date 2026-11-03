"""Rodič všech změn (iterace 1 a 3)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Mapping, Sequence

import numpy as np

from cee.v2 import phases
from cee.v2.pressures.base import Pressure
from cee.v2.repertoire import VariableKind, Variant
from cee.v2.rng import RandomSource

if TYPE_CHECKING:
    from cee.v2.world import Code, SpeechGroup, World

#: ``generation``: změna vzniká při osvojování, tempo × podíl obnovené
#: populace. ``year``: změnu dělají dospělí, tempo × délka kroku v letech.
RateBasis = Literal["generation", "year"]


@dataclass(frozen=True, slots=True)
class InnovationContext:
    world: World
    group: SpeechGroup
    code: Code
    tick: int
    year: float


class Change(ABC):
    """Mechanismus, který vyrábí nové varianty.

    Podtřída říká jen *kde* a *jak často* může inovace vzniknout a *jakou
    variantu* vyrobí. O jejím osudu rozhodují tlaky a společné šíření.
    """

    kind: ClassVar[str]
    target: ClassVar[VariableKind]
    #: Tlaky, které hodnotí varianty cílového typu proměnné, a jejich váhy.
    pressures: ClassVar[Mapping[type[Pressure], float]]
    #: Očekávaný počet inovací na jedno místo a jednotku tempa.
    base_rate: ClassVar[float]
    rate_basis: ClassVar[RateBasis]

    @abstractmethod
    def sites(self, context: InnovationContext) -> Sequence[str]:
        """ID proměnných, kde inovace může vzniknout."""

    def rate(self, context: InnovationContext, site: str) -> float:
        """Míra pro jedno místo; podtřída ji přepíše, jen když se místa liší."""
        return self.base_rate

    @abstractmethod
    def propose(
        self, context: InnovationContext, site: str, rng: RandomSource, index: int
    ) -> Variant | None:
        """Nová varianta pro ``site``; ``index`` odliší více inovací v kroku."""

    def on_established(self, context: InnovationContext, variant: Variant) -> list[Any]:
        """Restrukturalizace po ustálení (fonologizace od M2); v M1 nic."""
        return []

    def rate_scale(self, context: InnovationContext) -> float:
        """Násobek míry pro celou skupinu, když se místa neliší (výchozí 1)."""
        return 1.0

    def rates(self, context: InnovationContext, sites: Sequence[str]) -> list[float]:
        """Míry všech míst; podtřída je může počítat naráz."""
        return [self.rate(context, site) for site in sites]

    def total_rate(self, context: InnovationContext) -> float:
        """Celková míra všech míst ve skupině; indexované změny ji vrátí bez stavby seznamu míst."""
        sites = self.sites(context)
        if not sites:
            return 0.0
        if self.uses_uniform_rate():
            return float(phases.uniform_rate(self.base_rate, len(sites), self.rate_scale(context)))
        return phases.rate_total(self.rates(context, sites))

    def weighted_sites(
        self, context: InnovationContext
    ) -> tuple[Sequence[str], np.ndarray | None]:
        """Seřazená místa a normalizované váhy pro nenulový počet inovací."""
        sites = self.sites(context)
        if not sites:
            return (), None
        if self.uses_uniform_rate():
            return sites, None
        _, weights = phases.site_weights(self.rates(context, sites))
        if weights is None:
            return (), None
        return sites, weights

    def uses_uniform_rate(self) -> bool:
        return type(self).rate is Change.rate
