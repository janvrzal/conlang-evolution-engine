"""Brány milníků (``*_gate.py``) jsou pomalé: dlouhé simulace celých scénářů.

Označí se značkou ``slow``, takže rychlá sada je ``pytest -m "not slow"``.
"""

import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        if item.path.name.endswith("_gate.py"):
            item.add_marker(pytest.mark.slow)
