import pytest_asyncio

from app.db.session import engine, run_seed

@pytest_asyncio.fixture(autouse=True)
async def reseed():
    """Each test starts from the clean demo dataset."""
    await run_seed()
    yield

@pytest_asyncio.fixture(scope="session", autouse=True)
async def _dispose_engine():
    yield
    await engine.dispose()
