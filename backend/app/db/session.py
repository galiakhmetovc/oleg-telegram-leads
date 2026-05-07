from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


@lru_cache
def create_engine(database_url: str | None = None) -> AsyncEngine:
    return create_async_engine(database_url or get_settings().database_url)


@lru_cache
def create_sessionmaker(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    engine = create_engine(database_url)
    return async_sessionmaker(engine, expire_on_commit=False)


async def session_scope() -> AsyncIterator[AsyncSession]:
    session_factory = create_sessionmaker()
    async with session_factory() as session:
        yield session
