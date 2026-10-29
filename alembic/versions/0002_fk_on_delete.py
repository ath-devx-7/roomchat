"""FK ON DELETE: move Django's Python-emulated CASCADE / SET NULL into the database.

Each app-table FK is dropped and recreated under its existing (Django-hashed) name, still
DEFERRABLE INITIALLY DEFERRED; the ON DELETE clause is the only difference. The
Django-only tables' FKs are left as they are.

Revision ID: 0002_fk_on_delete
Revises: 0001_baseline
"""

import sqlalchemy as sa
from alembic import op

revision = '0002_fk_on_delete'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None

# (table, column, referred table, ON DELETE), mirroring each model's on_delete.
FOREIGN_KEYS = [
    ('accounts_friendship', 'sender_id', 'auth_user', 'CASCADE'),
    ('accounts_friendship', 'receiver_id', 'auth_user', 'CASCADE'),
    ('rooms_room', 'owner_id', 'auth_user', 'CASCADE'),
    ('rooms_message', 'room_id', 'rooms_room', 'CASCADE'),
    ('rooms_message', 'sender_id', 'auth_user', 'CASCADE'),
    ('rooms_message', 'reply_to_id', 'rooms_message', 'SET NULL'),
    ('rooms_roommembership', 'room_id', 'rooms_room', 'CASCADE'),
    ('rooms_roommembership', 'user_id', 'auth_user', 'CASCADE'),
    ('rooms_roominvitation', 'room_id', 'rooms_room', 'CASCADE'),
    ('rooms_roominvitation', 'sender_id', 'auth_user', 'CASCADE'),
    ('rooms_roominvitation', 'receiver_id', 'auth_user', 'CASCADE'),
    ('rooms_roomban', 'room_id', 'rooms_room', 'CASCADE'),
    ('rooms_roomban', 'user_id', 'auth_user', 'CASCADE'),
    ('rooms_roomban', 'banned_by_id', 'auth_user', 'SET NULL'),
]


def _recreate_foreign_keys(with_on_delete):
    # Django hashes constraint names, so look each one up rather than hard-coding it.
    inspector = sa.inspect(op.get_bind())
    names = {
        (table, column): next(
            fk['name'] for fk in inspector.get_foreign_keys(table) if fk['constrained_columns'] == [column]
        )
        for table, column, _, _ in FOREIGN_KEYS
    }
    for table, column, referred, on_delete in FOREIGN_KEYS:
        name = names[(table, column)]
        op.drop_constraint(name, table, type_='foreignkey')
        op.create_foreign_key(
            name, table, referred, [column], ['id'],
            ondelete=on_delete if with_on_delete else None,
            deferrable=True, initially='DEFERRED',
        )


def upgrade():
    _recreate_foreign_keys(with_on_delete=True)


def downgrade():
    _recreate_foreign_keys(with_on_delete=False)
