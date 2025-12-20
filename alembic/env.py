"""Alembic migration environment.

This module configures Alembic to work with SQLAlchemy 2.0 and
includes all models for autogenerate support.
"""

from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection

from alembic import context

# TODO: This module uses get_config() directly. Consider DI if Alembic supports it.
from app.core.config import get_config

# Import Base and ALL models for autogenerate
from app.models.base import Base

# IMPORTANT: Import all models so Alembic can detect them
# These imports register models with Base.metadata for autogenerate
from app.models.channel import Channel, Persona
from app.models.content_chunk import ContentChunk
from app.models.script import Script
from app.models.source import Source
from app.models.topic import Topic
from app.models.video import Video

# Ensure models are registered with metadata (prevents unused import warnings)
_MODELS = (Channel, Persona, ContentChunk, Script, Source, Topic, Video)

# this is the Alembic Config object
config = context.config

# Set database URL from config
config.set_main_option("sqlalchemy.url", get_config().database_url_sync)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with given connection.

    Args:
        connection: Database connection
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    from sqlalchemy import engine_from_config

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
