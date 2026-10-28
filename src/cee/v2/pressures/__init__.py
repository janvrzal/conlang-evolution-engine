"""Tlaky: komponenty, které hodnotí varianty (iterace 3)."""

from cee.v2.pressures.base import Pressure, PressureBatch
from cee.v2.pressures.linguistic import Appeal
from cee.v2.pressures.social import Conformity

__all__ = ["Appeal", "Conformity", "Pressure", "PressureBatch"]
