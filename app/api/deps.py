"""FastAPI dependency injection helpers."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Yield a synchronous database session per-request with auto-commit/rollback.

    FastAPI automatically runs sync dependencies in a thread pool,
    so async endpoints continue to work correctly.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
