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


def add_missing_indexes(engine: Engine) -> list[str]:
    """Index every foreign-key column that has no index starting with it.

    Postgres does not index foreign keys by itself, and the verse page looks rows up by them
    (tafsir by verse, meanings by verse, verses by topic...). Without these, each verse page
    read the whole tafsir table (about 40 MB) to find a few rows: fast where the table stays in
    memory, seconds on a small hosted database. Created once, at start-up; IF NOT EXISTS makes
    later starts free."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    created = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            indexed = {ix["column_names"][0] for ix in inspector.get_indexes(table.name) if ix["column_names"]}
            indexed |= {u["column_names"][0] for u in inspector.get_unique_constraints(table.name) if u["column_names"]}
            pk = inspector.get_pk_constraint(table.name).get("constrained_columns") or []
            if pk:
                indexed.add(pk[0])
            for fk in table.foreign_keys:
                col = fk.parent.name
                if col in indexed:
                    continue
                name = f"ix_{table.name}_{col}"
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table.name} ({col})"))
                indexed.add(col)
                created.append(name)
    return created
