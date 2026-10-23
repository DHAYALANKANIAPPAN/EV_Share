from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401  (register tables)
from app.config import settings
from app.database import Base

target_metadata = Base.metadata
URL = settings.database_url
IS_SQLITE = URL.startswith("sqlite")


def run_migrations_offline() -> None:
    context.configure(url=URL, target_metadata=target_metadata, literal_binds=True, render_as_batch=IS_SQLITE)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=IS_SQLITE)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
