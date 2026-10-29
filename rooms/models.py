import random
import string
from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, String, Text,
    UniqueConstraint, exists, select,
)
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from accounts.models import User, _now
from roomchat.db import Base, db

# Every FK is ON DELETE in the DB (alembic 0002); the ORM side only defers to it.
_CASCADE = 'save-update, merge, delete'


def _fk(target, name, ondelete='CASCADE'):
    return ForeignKey(target, ondelete=ondelete, deferrable=True, initially='DEFERRED', name=name)


def generate_room_code():
    """Generate a unique 6-character alphanumeric uppercase room code."""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not db.scalar(select(exists().where(Room.room_code == code))):
            return code


class Room(Base):
    """A chat room that users can join via a unique code."""

    __tablename__ = 'rooms_room'
    __table_args__ = (
        UniqueConstraint('room_code', name='rooms_room_room_code_key'),
        CheckConstraint('capacity >= 0', name='rooms_room_capacity_check'),
        Index('rooms_room_owner_id_13734245', 'owner_id'),
        Index(
            'rooms_room_room_code_c2832b2c_like', 'room_code',
            postgresql_ops={'room_code': 'varchar_pattern_ops'},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    room_code: Mapped[str] = mapped_column(String(6))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default='')
    password: Mapped[str] = mapped_column(String(128), default='')
    capacity: Mapped[int] = mapped_column(Integer, default=10)
    owner_id: Mapped[int] = mapped_column(_fk('auth_user.id', 'rooms_room_owner_id_13734245_fk_auth_user_id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    owner = relationship(User, backref=backref('owned_rooms', cascade=_CASCADE, passive_deletes=True))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.room_code:
            with db.no_autoflush:
                self.room_code = generate_room_code()

    @property
    def active_user_count(self):
        return self.memberships.count()

    @property
    def is_full(self):
        return self.active_user_count >= self.capacity

    def __str__(self):
        return f"{self.name} ({self.room_code})"


class RoomMembership(Base):
    """Tracks currently active users in a room (created on WS connect, deleted on disconnect)."""

    __tablename__ = 'rooms_roommembership'
    __table_args__ = (
        UniqueConstraint('user_id', 'room_id', name='rooms_roommembership_user_id_room_id_f7ab799d_uniq'),
        Index('rooms_roommembership_room_id_bc44aa96', 'room_id'),
        Index('rooms_roommembership_user_id_22caa5ba', 'user_id'),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    channel_name: Mapped[str] = mapped_column(String(255), default='')
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    room_id: Mapped[int] = mapped_column(_fk('rooms_room.id', 'rooms_roommembership_room_id_bc44aa96_fk_rooms_room_id'))
    user_id: Mapped[int] = mapped_column(_fk('auth_user.id', 'rooms_roommembership_user_id_22caa5ba_fk_auth_user_id'))

    user = relationship(User, backref=backref('room_memberships', cascade=_CASCADE, passive_deletes=True))
    room = relationship(Room, backref=backref(
        'memberships', lazy='dynamic', cascade=_CASCADE, passive_deletes=True
    ))

    def __str__(self):
        return f"{self.user.username} in {self.room.name}"


class RoomBan(Base):
    """A user removed from a room by its owner, checked at every entry point.

    Deliberately no expires_at: a room is deleted as soon as its last member
    disconnects, so the CASCADE from Room is the only lifetime a ban can
    meaningfully have. A recycled room code lands on a new Room row, so an old
    ban cannot follow it onto someone else's room.
    """

    __tablename__ = 'rooms_roomban'
    __table_args__ = (
        UniqueConstraint('room_id', 'user_id', name='rooms_roomban_room_id_user_id_69c6b872_uniq'),
        Index('rooms_roomban_banned_by_id_1c95e66a', 'banned_by_id'),
        Index('rooms_roomban_room_id_735367a8', 'room_id'),
        Index('rooms_roomban_user_id_01545f0a', 'user_id'),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Audit data, not a constraint — ownership transfers, and losing the issuer
    # must not lift the ban.
    banned_by_id: Mapped[int | None] = mapped_column(
        _fk('auth_user.id', 'rooms_roomban_banned_by_id_1c95e66a_fk_auth_user_id', ondelete='SET NULL')
    )
    room_id: Mapped[int] = mapped_column(_fk('rooms_room.id', 'rooms_roomban_room_id_735367a8_fk_rooms_room_id'))
    user_id: Mapped[int] = mapped_column(_fk('auth_user.id', 'rooms_roomban_user_id_01545f0a_fk_auth_user_id'))

    room = relationship(Room, backref=backref('bans', cascade=_CASCADE, passive_deletes=True))
    user = relationship(User, foreign_keys=[user_id], backref=backref(
        'room_bans', cascade=_CASCADE, passive_deletes=True
    ))
    banned_by = relationship(User, foreign_keys=[banned_by_id], backref=backref(
        'bans_issued', passive_deletes=True
    ))

    def __str__(self):
        return f"{self.user.username} banned from {self.room.name}"


class RoomInvitation(Base):
    """An invitation to join a room, sent from one user to another."""

    __tablename__ = 'rooms_roominvitation'
    __table_args__ = (
        Index('rooms_roominvitation_receiver_id_c11bed1f', 'receiver_id'),
        Index('rooms_roominvitation_room_id_529657ea', 'room_id'),
        Index('rooms_roominvitation_sender_id_19ea8b3b', 'sender_id'),
    )

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    status: Mapped[str] = mapped_column(String(10), default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    receiver_id: Mapped[int] = mapped_column(
        _fk('auth_user.id', 'rooms_roominvitation_receiver_id_c11bed1f_fk_auth_user_id')
    )
    room_id: Mapped[int] = mapped_column(_fk('rooms_room.id', 'rooms_roominvitation_room_id_529657ea_fk_rooms_room_id'))
    sender_id: Mapped[int] = mapped_column(_fk('auth_user.id', 'rooms_roominvitation_sender_id_19ea8b3b_fk_auth_user_id'))

    room = relationship(Room, backref=backref('invitations', cascade=_CASCADE, passive_deletes=True))
    sender = relationship(User, foreign_keys=[sender_id], backref=backref(
        'sent_invitations', cascade=_CASCADE, passive_deletes=True
    ))
    receiver = relationship(User, foreign_keys=[receiver_id], backref=backref(
        'received_invitations', cascade=_CASCADE, passive_deletes=True
    ))

    def __str__(self):
        return f"{self.sender.username} invited {self.receiver.username} to {self.room.name}"


class Message(Base):
    """A chat message within a room."""

    __tablename__ = 'rooms_message'
    __table_args__ = (
        Index('rooms_message_reply_to_id_34dd708a', 'reply_to_id'),
        Index('rooms_message_room_id_ec9477f2', 'room_id'),
        Index('rooms_message_sender_id_05bf05fe', 'sender_id'),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_deleted: Mapped[bool] = mapped_column(default=False)
    reply_to_id: Mapped[int | None] = mapped_column(
        _fk('rooms_message.id', 'rooms_message_reply_to_id_34dd708a_fk_rooms_message_id', ondelete='SET NULL')
    )
    sender_id: Mapped[int] = mapped_column(_fk('auth_user.id', 'rooms_message_sender_id_05bf05fe_fk_auth_user_id'))
    room_id: Mapped[int] = mapped_column(_fk('rooms_room.id', 'rooms_message_room_id_ec9477f2_fk_rooms_room_id'))

    room = relationship(Room, backref=backref('messages', cascade=_CASCADE, passive_deletes=True))
    sender = relationship(User, backref=backref('messages', cascade=_CASCADE, passive_deletes=True))
    reply_to = relationship('Message', remote_side=[id], backref=backref('replies', passive_deletes=True))

    def __str__(self):
        return f"{self.sender.username}: {self.content[:50]}"
