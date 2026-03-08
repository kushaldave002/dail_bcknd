"""
DAIL Backend - Database Connection Management

Synchronous SQLAlchemy engine using pg8000 — a pure-Python PostgreSQL driver.

Driver history:
  - asyncpg:        FAILS on Vercel Lambda — [Errno 16] via OpenSSL /dev/urandom
  - psycopg2-binary: FAILS on Vercel Lambda — same root cause (OpenSSL C extension)
  - pg8000:         WORKS — pure Python, uses Python's ssl module (no OpenSSL C calls)
"""

import ssl
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

# ── Normalise DATABASE_URL scheme to pg8000 ───────────────────────────────
_db_url = str(settings.DATABASE_URL)

_old_schemes = [
    "postgresql+asyncpg://",
    "postgres+asyncpg://",
    "postgresql+psycopg2://",
    "postgres+psycopg2://",
]
_replaced = False
for _old in _old_schemes:
    if _db_url.startswith(_old):
        _db_url = "postgresql+pg8000://" + _db_url[len(_old):]
        _replaced = True
        break

if not _replaced:
    if _db_url.startswith("postgres://"):
        _db_url = "postgresql+pg8000://" + _db_url[len("postgres://"):]
    elif _db_url.startswith("postgresql://"):
        _db_url = "postgresql+pg8000://" + _db_url[len("postgresql://"):]

# ── SSL Context (pure Python ssl module — works on Vercel Lambda) ─────────
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE  # Supabase pooler uses self-signed cert

# ── Engine ────────────────────────────────────────────────────────────────
# NullPool — required for serverless; no persistent connection pools.
engine = create_engine(
    _db_url,
    echo=settings.DEBUG,
    poolclass=NullPool,
    connect_args={"ssl_context": _ssl_ctx},  # pg8000 uses ssl_context key
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
    """FastAPI dependency — sync session per request, runs in thread pool."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
