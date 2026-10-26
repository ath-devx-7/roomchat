from logging.config import fileConfig

from alembic import context

import accounts.models  # noqa: F401  (registers auth_user, accounts_friendship, django_session)
import rooms.models  # noqa: F401
from roomchat.db import Base, engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Created by Django's migrations and kept in the baseline, but no longer used by the app.
# Excluding them keeps autogenerate from ever proposing to drop them.
DJANGO_ONLY_TABLES = {
    'auth_group',
    'auth_group_permissions',
    'auth_permission',
    'auth_user_groups',
    'auth_user_user_permissions',
    'django_admin_log',
    'django_content_type',
    'django_migrations',
}


def include_object(object, name, type_, reflected, compare_to):
    return not (type_ == 'table' and name in DJANGO_ONLY_TABLES)


def run_migrations_offline():
    context.configure(
        url=engine.url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
