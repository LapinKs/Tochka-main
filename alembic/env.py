from logging.config import fileConfig
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from alembic import context
import asyncio
from app.db_manager import Base
from app.models_DB import *

target_metadata = Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

async def run_async_migrations():
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"), poolclass=NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda sync_conn: context.configure( connection=sync_conn,
                target_metadata=target_metadata, compare_type=True)
        )
        await connection.run_sync(context.run_migrations)

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure( url=url, target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()