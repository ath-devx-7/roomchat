from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.db.models import Q

from accounts.models import Friendship
from .models import Room, RoomMembership, RoomInvitation


def create_room(user, room_data):
    # Create a new chat room and assign the user as the owner.

    password_hashed = make_password(room_data.password) if room_data.password else ''

    room = Room.objects.create(
        name=room_data.name,
        description=room_data.description,
        password=password_hashed,
        capacity=room_data.capacity,
        owner=user,
    )

    return room


def get_pending_invitations(user):
    return RoomInvitation.objects.filter(receiver=user, status='pending').select_related('room', 'sender')


def has_accepted_room_invitation(user, room):
    return RoomInvitation.objects.filter(room=room, receiver=user, status='accepted').exists()


def create_room_invitation(actor, room, target_user_id):
    try:
        target_user = User.objects.get(id=target_user_id)
    except User.DoesNotExist:
        return {'error': 'User not found.'}

    are_friends = Friendship.objects.filter(
        Q(sender=actor, receiver=target_user, status='accepted') |
        Q(sender=target_user, receiver=actor, status='accepted')
    ).exists()

    if not are_friends:
        return {'error': 'You can only invite friends.'}

    existing = RoomInvitation.objects.filter(
        room=room, receiver=target_user, status='pending'
    ).exists()
    if existing:
        return {'error': 'Invitation already sent.'}

    in_room = RoomMembership.objects.filter(user=target_user, room=room).exists()
    if in_room:
        return {'error': 'User is already in this room.'}

    invitation = RoomInvitation.objects.create(
        room=room,
        sender=actor,
        receiver=target_user,
    )

    return {
        'invitation_id': invitation.id,
        'room_name': room.name,
        'receiver_username': target_user.username,
    }


def accept_room_invitation(user, invitation_id):
    try:
        invitation = RoomInvitation.objects.get(id=invitation_id, receiver=user, status='pending')
    except RoomInvitation.DoesNotExist:
        return None

    invitation.status = 'accepted'
    invitation.save()
    return {'room_code': invitation.room.room_code}


def reject_room_invitation(user, invitation_id):
    try:
        invitation = RoomInvitation.objects.get(id=invitation_id, receiver=user, status='pending')
    except RoomInvitation.DoesNotExist:
        return False

    invitation.status = 'declined'
    invitation.save()
    return True