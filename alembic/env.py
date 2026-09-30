"""
env.py de Alembic — generado por `alembic init alembic`

  1. target_metadata = Base.metadata, para que `--autogenerate` pueda
     hacer diff de los modelos reales contra el estado de la base.
  2. La URL de conexión sale de settings.DATABASE_URL, la misma fuente
     que usa el engine real de la app, src/database/base.py, en vez de
     estar hardcodeada en alembic.ini.

El resto de las funciones (run_migrations_offline/online) es el
boilerplate estándar de `alembic init`, no hace falta tocarlas.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

from src.config.settings import settings
from src.database.base import Base

# Si bien no se utiliza el models directamente en el script, es un Import 
# necesario para que Base.metadata conozca todas las tablas antes
# de que Alembic las compare. 
from src import models

# Este es el objeto de configuración de Alembic, que proporciona
# acceso a los valores del archivo .ini en uso.
config = context.config

# Interpreta el archivo de configuración para el registro de eventos (logging) de Python.
# Básicamente, esta línea configura los registradores (loggers).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# añade aquí el objeto MetaData de tu modelo
# para el soporte de 'autogenerate'
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# Una sola fuente de verdad para la URL: la misma que usa la app.
# Así no hace falta, ni conviene, tener sqlalchemy.url en alembic.ini.
# Sólo si nadie seteó sqlalchemy.url antes puede forzar otra
# URL sin que se la pisemos acá.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Esto configura el contexto utilizando únicamente una URL
    y no un *Engine*, aunque un *Engine* también es aceptable
    en este caso. Al omitir la creación del *Engine*,
    ni siquiera es necesario disponer de una DBAPI.

    Las llamadas a `context.execute()` en este punto envían la cadena especificada
    a la salida del *script*.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    En este escenario, necesitamos crear un motor
    y asociar una conexión con el contexto.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
