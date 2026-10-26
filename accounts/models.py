from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey, Identity, Index, Integer, String, Table, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from roomchat.db import Base


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    """Django's auth_user table, all 11 columns, unchanged."""

    __tablename__ = 'auth_user'
    __table_args__ = (
        UniqueConstraint('username', name='auth_user_username_key'),
        Index(
            'auth_user_username_6821ab7c_like', 'username',
            postgresql_ops={'username': 'varchar_pattern_ops'},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    password: Mapped[str] = mapped_column(String(128))
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_superuser: Mapped[bool] = mapped_column(default=False)
    username: Mapped[str] = mapped_column(String(150))
    first_name: Mapped[str] = mapped_column(String(150), default='')
    last_name: Mapped[str] = mapped_column(String(150), default='')
    email: Mapped[str] = mapped_column(String(254), default='')
    is_staff: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    date_joined: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def __str__(self):
        return self.username


# Server-side session rows (roomchat/sessions.py). Declared here so the metadata covers
# every table the app owns.
django_session = Table(
    'django_session',
    Base.metadata,
    Column('session_key', String(40), primary_key=True),
    Column('session_data', Text, nullable=False),
    Column('expire_date', DateTime(timezone=True), nullable=False),
    Index('django_session_expire_date_a5c62663', 'expire_date'),
    Index(
        'django_session_session_key_c0390e0f_like', 'session_key',
        postgresql_ops={'session_key': 'varchar_pattern_ops'},
    ),
)


class Friendship(Base):
    """Represents a friend request / friendship between two users."""

    __tablename__ = 'accounts_friendship'
    __table_args__ = (
        UniqueConstraint(
            'sender_id', 'receiver_id', name='accounts_friendship_sender_id_receiver_id_d5e8507f_uniq'
        ),
        Index('accounts_friendship_receiver_id_dfb0a89e', 'receiver_id'),
        Index('accounts_friendship_sender_id_e7d1ff85', 'sender_id'),
    )

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
    ]

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey(
        'auth_user.id', ondelete='CASCADE', deferrable=True, initially='DEFERRED',
        name='accounts_friendship_sender_id_e7d1ff85_fk_auth_user_id',
    ))
    receiver_id: Mapped[int] = mapped_column(ForeignKey(
        'auth_user.id', ondelete='CASCADE', deferrable=True, initially='DEFERRED',
        name='accounts_friendship_receiver_id_dfb0a89e_fk_auth_user_id',
    ))
    status: Mapped[str] = mapped_column(String(10), default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    sender = relationship(User, foreign_keys=[sender_id], backref=backref(
        'sent_friend_requests', cascade='save-update, merge, delete', passive_deletes=True
    ))
    receiver = relationship(User, foreign_keys=[receiver_id], backref=backref(
        'received_friend_requests', cascade='save-update, merge, delete', passive_deletes=True
    ))

    def __str__(self):
        return f"{self.sender.username} -> {self.receiver.username} ({self.status})"
