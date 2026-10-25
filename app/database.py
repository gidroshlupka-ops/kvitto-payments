import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models import Base

# sqlite+aiosqlite по умолчанию. Для PostgreSQL:
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/kvitto
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./kvitto.db")

engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
