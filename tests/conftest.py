import pytest
from encinorm.sqlite import SqliteDb


@pytest.fixture
def db():
    return SqliteDb()


@pytest.fixture
async def connected_db():
    db = SqliteDb()
    await db.connect(database=":memory:")
    yield db
    await db.close()
