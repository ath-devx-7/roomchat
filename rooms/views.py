from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from pydantic import ValidationError

from roomchat.errors import format_pydantic_errors
from roomchat.middleware import json_validation_errors

from .models import Room, RoomMembership, Message, RoomInvitation
from accounts.models import Friendship
from .schemas import RoomCreate, RoomJoin, RoomInvitationResponse

from . import services


@login_required
def dashboard(request):
    """Main dashboard view showing friends, requests, rooms, and invitations."""
    friendships = Friendship.objects.filter(
        Q(sender=request.user, status='accepted') |
        Q(receiver=request.user, status='accepted')
    )
    friends = []
    for f in friendships:
        friend_user = f.receiver if f.sender == request.user else f.sender
        membership = RoomMembership.objects.filter(user=friend_user).first()
        friends.append({
            'friendship_id': f.id,
            'user': friend_user,
            'current_room': membership.room if membership else None,
        })

    pending_requests = Friendship.objects.filter(
        receiver=request.user, status='pending'
    ).select_related('sender')

    pending_invitations = services.get_pending_invitations(request.user)

    current_membership = RoomMembership.objects.filter(user=request.user).first()

    context = {
        'friends': friends,
        'pending_requests': pending_requests,
        'pending_invitations': pending_invitations,
        'current_membership': current_membership,
    }
    return render(request, 'rooms/dashboard.html', context=context)


@login_required
def create_room(request):
    """Create a new chat room."""
    if request.method != 'POST':
        return redirect('dashboard')

    try:
        room_data = RoomCreate(
            name=request.POST.get('name', ''),
            description=request.POST.get('description', ''),
            capacity=request.POST.get('capacity', '10'),
            password=request.POST.get('password', '')
        )
    except ValidationError as e:
        for msg in format_pydantic_errors(e).values():
            messages.error(request, msg)
        return redirect('dashboard')

    room = services.create_room(request.user, room_data)

    # No grant needed: the creator is the owner, and owners bypass the gate.
    return redirect('room', room_code=room.room_code)


@login_required
def join_room(request):
    """Join an existing room by code and optional password."""
    if request.method != 'POST':
        return redirect('dashboard')

    try:
        join_data = RoomJoin(
            room_code=request.POST.get('room_code', ''),
            password=request.POST.get('password', ''),
        )
    except ValidationError as e:
        for msg in format_pydantic_errors(e).values():
            messages.error(request, msg)
        return redirect('dashboard')

    # RoomJoin has already verified the password; unlock the room for as long as
    # the user stays connected to it. One slot, so this replaces any prior grant.
    request.session['room_grant'] = join_data.room.room_code

    return redirect('room', room_code=join_data.room.room_code)


@login_required
def room_view(request, room_code):
    """Render the room page. Actual joining happens via WebSocket."""
    room = get_object_or_404(Room, room_code=room_code)
    is_owner = room.owner == request.user

    # The gate runs before the history query below, so a user who has not
    # unlocked the room never receives any of its messages.
    if room.password and not is_owner and request.session.get('room_grant') != room.room_code:
        # An accepted invitation admits the user exactly once: consume the row
        # and mint the same grant a correct password would have. This is the only
        # place an invitation grants access, which is why the WebSocket gate can
        # stay a plain session check.
        invite = RoomInvitation.objects.filter(
            room=room, receiver=request.user, status='accepted'
        ).first()
        if not invite:
            messages.error(request, 'This room is protected. Please join using the password on the dashboard.')
            return redirect('dashboard')

        invite.delete()
        request.session['room_grant'] = room.room_code

    messages_history = Message.objects.filter(room=room).select_related(
        'sender', 'reply_to', 'reply_to__sender'
    ).order_by('created_at')[:100]

    context = {
        'room': room,
        'is_owner': is_owner,
        'messages_history': messages_history,
    }
    return render(request, 'rooms/room.html', context=context)


@login_required
@json_validation_errors
def get_invitations_api(request):
    """Return pending room invitations as JSON."""
    invitations = services.get_pending_invitations(request.user)

    data = [
        RoomInvitationResponse(
            id=inv.id,
            room_code=inv.room.room_code,
            room_name=inv.room.name,
            sender_username=inv.sender.username,
            created_at=inv.created_at
        )
        for inv in invitations
    ]

    return JsonResponse({'invitations': [item.model_dump(mode='json') for item in data]})
