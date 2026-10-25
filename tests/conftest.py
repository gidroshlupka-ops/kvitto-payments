import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

DB_PATH = Path(__file__).resolve().parent / "pytest_kvitto.db"
if DB_PATH.exists():
    DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"

from app.main import app  # noqa: E402


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client(anyio_backend: str) -> AsyncIterator[AsyncClient]:
    del anyio_backend
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as async_client:
            yield async_client
