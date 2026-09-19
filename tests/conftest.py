from pathlib import Path

import pytest

from cee.engine.phonology import FeatureMapper

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def mapper() -> FeatureMapper:
    """FeatureMapper je drahý na postavení (načítá celou panphon tabulku)."""
    return FeatureMapper()
