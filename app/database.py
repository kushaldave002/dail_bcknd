"""
DAIL Backend - Database Connection Management

Async SQLAlchemy engine and session factory for PostgreSQL.
"""

import ssl
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

# ── SSL Context ──────────────────────────────────────────────────────────
# Vercel's serverless environment (AWS Lambda) restricts how asyncpg
# initialises SSL when passed as a plain string ("require").
# Passing a pre-built ssl.SSLContext avoids [Errno 16] Device or resource busy.
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

# ── Async Engine ─────────────────────────────────────────────────────────
# NullPool is required for serverless environments (Vercel).
# Persistent connection pools cannot survive cold starts in stateless functions.

# Auto-correct DATABASE_URL to use asyncpg driver (psycopg2 is not available on Vercel)
_db_url = str(settings.DATABASE_URL)
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    _db_url,
    echo=settings.DEBUG,
    poolclass=NullPool,
    connect_args={"ssl": _ssl_ctx},
)

# ── Session Factory ──────────────────────────────────────────────────────
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Base Model ───────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


# ── Dependency ───────────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides a database session per request."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
