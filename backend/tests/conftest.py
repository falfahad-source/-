import pytest

from app import cache


@pytest.fixture(autouse=True)
def _empty_response_cache():
    """Each test reads its own database: no response cached by another test."""
    cache.clear()
    yield
    cache.clear()
