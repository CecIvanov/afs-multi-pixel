from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings


def build_engine(settings: Settings | None = None) -> Engine:
    resolved = settings or get_settings()
    return create_engine(
        resolved.database_url,
        pool_pre_ping=True,
        pool_size=resolved.database_pool_size,
        max_overflow=resolved.database_max_overflow,
    )


engine = build_engine(get_settings())
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def release_db_session(db: Session) -> None:
    """Return the connection to the pool before slow external I/O."""
    if db.is_active:
        db.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        release_db_session(db)
