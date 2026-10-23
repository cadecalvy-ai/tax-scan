import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.harness import answer_key, grade_all  # noqa: E402


@pytest.fixture(scope="session")
def key():
    return answer_key()


@pytest.fixture(scope="session")
def results():
    """Grade all 24 test clients once per test session (OCR results are cached)."""
    return grade_all()
