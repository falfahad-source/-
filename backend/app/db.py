import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Base

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg2://afaq:afaq@localhost:5432/afaq"
)

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create missing tables and add missing nullable columns. Development
    convenience only — use Alembic migrations for anything touching real data."""
    from .schema_upgrade import add_missing_columns

    Base.metadata.create_all(engine)
    add_missing_columns(engine)


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
