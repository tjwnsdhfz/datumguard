from __future__ import annotations

from pathlib import Path

import pytest

from datumguard.models import DesignContract


@pytest.fixture
def sample_contract() -> DesignContract:
    path = Path(__file__).parents[1] / "fixtures" / "examples" / "design_contract.json"
    return DesignContract.model_validate_json(path.read_text(encoding="utf-8"))
