from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from kineticloop.persistence.metadata import metadata

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = metadata


def url() -> str:
    value = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not value:
        raise RuntimeError("DATABASE_URL is required for migration execution")
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def offline() -> None:
    context.configure(url=url(), target_metadata=target_metadata, literal_binds=True, include_schemas=True)
    with context.begin_transaction():
        context.run_migrations()


def online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = url()
    engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_schemas=True)
        with context.begin_transaction():
            context.run_migrations()


offline() if context.is_offline_mode() else online()
