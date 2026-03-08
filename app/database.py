"""
DAIL Backend - Database Connection Management

Synchronous SQLAlchemy engine and session factory for PostgreSQL.
Uses psycopg2-binary which works reliably on Vercel's serverless environment.
(asyncpg triggers [Errno 16] Device or resource busy on Vercel's Lambda runtime.)
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

# ── Engine ────────────────────────────────────────────────────────────────
# NullPool — required for serverless; no persistent connection pools.
# psycopg2-binary works on Vercel; asyncpg does not (EBUSY on Lambda).

# Normalise scheme to plain postgresql+psycopg2://
_db_url = str(settings.DATABASE_URL)
for _old in ("postgresql+asyncpg://", "postgres+asyncpg://"):
    if _db_url.startswith(_old):
        _db_url = "postgresql+psycopg2://" + _db_url[len(_old):]
        break
if _db_url.startswith("postgres://"):
    _db_url = "postgresql+psycopg2://" + _db_url[len("postgres://"):]
elif _db_url.startswith("postgresql://"):
    _db_url = "postgresql+psycopg2://" + _db_url[len("postgresql://"):]

# sslmode=require appended for Supabase (safe to add even if already present)
if "sslmode" not in _db_url:
    _db_url += ("&" if "?" in _db_url else "?") + "sslmode=require"

engine = create_engine(
    _db_url,
    echo=settings.DEBUG,
    poolclass=NullPool,
)

# ── Session Factory ───────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


# ── Base Model ────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


# ── Dependency ────────────────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a database session per request."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
