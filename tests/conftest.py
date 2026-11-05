import pytest

from app.db import init_db, init_engine


@pytest.fixture
def memory_db():
    init_engine("sqlite:///:memory:")
    init_db()
    yield
