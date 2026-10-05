import os
import re

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Base



def sqlalchemy_url(url: str) -> str:
    """Hosts (Render, Heroku...) give postgres:// or postgresql:// URLs; SQLAlchemy would pick
    a driver that is not installed for those, so name psycopg2 explicitly."""
    return re.sub(r"^postgres(?:ql)?://", "postgresql+psycopg2://", url.strip())


DATABASE_URL = sqlalchemy_url(os.environ.get(
    "DATABASE_URL", "postgresql+psycopg2://afaq:afaq@localhost:5432/afaq"
))

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
