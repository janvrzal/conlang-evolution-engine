"""Rodič všech změn (iterace 1 a 3)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Mapping, Sequence

import numpy as np

from cee.v2.pressures.base import Pressure
from cee.v2.repertoire import VariableKind, Variant

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
        self, context: InnovationContext, site: str, rng: np.random.Generator, index: int
    ) -> Variant | None:
        """Nová varianta pro ``site``; ``index`` odliší více inovací v kroku."""

    def on_established(self, context: InnovationContext, variant: Variant) -> list[Any]:
        """Restrukturalizace po ustálení (fonologizace od M2); v M1 nic."""
        return []

    def rate_scale(self, context: InnovationContext) -> float:
        """Násobek míry pro celou skupinu, když se místa neliší (výchozí 1)."""
        return 1.0

    def uses_uniform_rate(self) -> bool:
        return type(self).rate is Change.rate
