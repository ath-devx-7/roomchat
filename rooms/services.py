from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import joinedload

from accounts.models import Friendship, User
from roomchat.auth import check_password, make_password
from roomchat.db import db
from .models import Room, RoomBan, RoomMembership, RoomInvitation


def create_room(user, room_data):
    """Create a room owned by `user` (password hashed if given) and return it."""
    # Create a new chat room and assign the user as the owner.

    password_hashed = make_password(room_data.password) if room_data.password else ''

    room = Room(
        name=room_data.name,
        description=room_data.description,
        password=password_hashed,
        capacity=room_data.capacity,
        owner=user,
    )
    db.add(room)
    db.commit()  # rule 2: Django's .objects.create() saved immediately

    return room


def get_pending_invitations(user):
    """Return the pending room invitations `user` has received."""
    # joinedload = select_related; .all() returns a list that can be looped over more
    # than once, like a Django queryset.
    return db.scalars(
        select(RoomInvitation)
        .where(RoomInvitation.receiver == user, RoomInvitation.status == 'pending')
        .options(joinedload(RoomInvitation.room), joinedload(RoomInvitation.sender))
    ).all()


def create_room_invitation(actor, room, target_user_id):
    """Invite a friend into `room`; returns the new invitation's details or {'error': ...}."""
    target_user = db.scalars(select(User).where(User.id == target_user_id)).one_or_none()
    if target_user is None:
        return {'error': 'User not found.'}

    # SELECT EXISTS(...) for a friendship in either direction.
    are_friends = db.scalar(select(exists().where(or_(
        and_(Friendship.sender == actor, Friendship.receiver == target_user, Friendship.status == 'accepted'),
        and_(Friendship.sender == target_user, Friendship.receiver == actor, Friendship.status == 'accepted'),
    ))))

    if not are_friends:
        return {'error': 'You can only invite friends.'}

    # room_detail_api refuses a banned user anyway; catching it here turns a silently
    # dead invitation into an explanation for the sender.
    if db.scalar(select(exists().where(RoomBan.room == room, RoomBan.user == target_user))):
        return {'error': 'That user was removed from this room.'}

    existing = db.scalar(select(exists().where(
        RoomInvitation.room == room,
        RoomInvitation.receiver == target_user,
        RoomInvitation.status == 'pending',
    )))
    if existing:
        return {'error': 'Invitation already sent.'}

    in_room = db.scalar(select(exists().where(
        RoomMembership.user == target_user, RoomMembership.room == room
    )))
    if in_room:
        return {'error': 'User is already in this room.'}

    invitation = RoomInvitation(
        room=room,
        sender=actor,
        receiver=target_user,
    )
    db.add(invitation)
    db.commit()

    return {
        'invitation_id': invitation.id,
        'room_name': room.name,
        'receiver_username': target_user.username,
    }


def accept_room_invitation(user, invitation_id):
    """Mark a pending invitation accepted; returns {'room_code': ...} or None if not found."""
    invitation = db.scalars(select(RoomInvitation).where(
        RoomInvitation.id == invitation_id,
        RoomInvitation.receiver == user,
        RoomInvitation.status == 'pending',
    )).one_or_none()
    if invitation is None:
        return None

    invitation.status = 'accepted'
    db.commit()  # Django's .save()
    return {'room_code': invitation.room.room_code}


def reject_room_invitation(user, invitation_id):
    """Mark a pending invitation declined; returns True, or False if not found."""
    invitation = db.scalars(select(RoomInvitation).where(
        RoomInvitation.id == invitation_id,
        RoomInvitation.receiver == user,
        RoomInvitation.status == 'pending',
    )).one_or_none()
    if invitation is None:
        return False

    invitation.status = 'declined'
    db.commit()
    return True