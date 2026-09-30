"""
Verifica el único AC que tiene sentido automatizar:
que `alembic upgrade head` sobre una base vacía produce EXACTAMENTE el
mismo esquema que hoy genera Base.metadata.create_all().

No tiene sentido diffear el SQL crudo.
En cambio, se construye el esquema por los dos caminos contra su propio
SQLite, y se compara la introspección de SQLAlchemy mismas
tablas, columnas, foreign keys y unique constraints — incluyendo los NOMBRES de esas constraints, porque
NAMING_CONVENTION (src/database/base.py) es parte de lo que debe
coincidir entre ambos caminos.

Requiere Alembic instalado y alembic.ini/env.py ya configurados.
"""

from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from src import models 
from src.database.base import Base


def _describe_schema(engine) -> dict[str, dict]:
    """Reduce la introspección de SQLAlchemy a algo comparable entre las
    dos formas de crear el esquema."""
    inspector = inspect(engine)
    schema: dict[str, dict] = {}

    for table_name in sorted(inspector.get_table_names()):
        columns = {
            col["name"]: (str(col["type"]), col["nullable"])
            for col in inspector.get_columns(table_name)
        }

        foreign_keys = sorted(
            (fk["name"], tuple(fk["constrained_columns"]), fk["referred_table"])
            for fk in inspector.get_foreign_keys(table_name)
        )

        unique_constraints = sorted(
            (uc["name"], tuple(uc["column_names"]))
            for uc in inspector.get_unique_constraints(table_name)
        )

        pk = inspector.get_pk_constraint(table_name)
        primary_key = (pk.get("name"), tuple(pk.get("constrained_columns", [])))

        schema[table_name] = {
            "columns": columns,
            "foreign_keys": foreign_keys,
            "unique_constraints": unique_constraints,
            "primary_key": primary_key,
        }

    return schema


def test_deberia_matchear_schemas_alembic_upgrade_head_con_create_all(tmp_path):
    # Lo que hoy genera create_all().
    create_all_engine = create_engine("sqlite://")
    Base.metadata.create_all(create_all_engine)
    schema_from_create_all = _describe_schema(create_all_engine)

    # alembic upgrade head, contra un SQLite en un archivo temporal.
    db_path = tmp_path / "alembic_check.db"
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "head")

    migrated_engine = create_engine(f"sqlite:///{db_path}")
    schema_from_migrations = _describe_schema(migrated_engine)

    # alembic_version es bookkeeping propio de Alembic, no existe en ningún modelo 
    # de SQLAlchemy, así que create_all() nunca la genera. Se excluye porque 
    # no es parte del esquema de la aplicación, es metadata de la herramienta.
    schema_from_migrations.pop("alembic_version", None)


    assert schema_from_migrations == schema_from_create_all