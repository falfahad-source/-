"""Add new nullable columns to tables that already exist.

`create_all()` creates missing tables but never alters existing ones, so a dev
database made by an earlier version lacks columns added since. Until Alembic is
introduced, this adds any missing *nullable* column (the only kind added so far)
with a plain ALTER TABLE ... ADD COLUMN, which SQLite and Postgres both support.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .models import Base


def add_missing_columns(engine: Engine) -> list[str]:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all() makes it with every column
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                if not col.nullable:
                    raise RuntimeError(f"{table.name}.{col.name} is NOT NULL; needs a real migration")
                col_type = col.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}'))
                added.append(f"{table.name}.{col.name}")
    return added
