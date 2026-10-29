"""
SQLAlchemy engine and the scoped `db` session shared by models, services and controllers.
"""

from contextvars import ContextVar

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker

from roomchat import settings

_database = settings.DATABASES['default']

engine = create_engine(
    URL.create(
        'postgresql+psycopg',
        username=_database['USER'],
        password=_database['PASSWORD'],
        host=_database['HOST'],
        port=int(_database['PORT']),
        database=_database['NAME'],
    ),
    # Replaces CONN_MAX_AGE/CONN_HEALTH_CHECKS: pooled connections are checked before reuse.
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# One session per scope: the HTTP middleware opens a scope per request and
# database_sync_to_async one per call. There is deliberately no default, so using `db`
# outside an opened scope raises LookupError instead of silently sharing a session.
db_scope = ContextVar('db_scope')

db = scoped_session(SessionLocal, scopefunc=db_scope.get)
