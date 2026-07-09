from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from pydantic import ValidationError

from roomchat.errors import format_pydantic_errors
from roomchat.middleware import json_validation_errors

from .models import Room, RoomMembership, Message
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
    if request.method == 'POST':
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
    
    if room_data.password:
        authorized_rooms = request.session.get('authorized_rooms', [])
        if room.room_code not in authorized_rooms:
            authorized_rooms.append(room.room_code)
            request.session['authorized_rooms'] = authorized_rooms

        return redirect('room', room_code=room.room_code)

    return redirect('dashboard')


@login_required
def join_room(request):
    """Join an existing room by code and optional password."""
    if request.method == 'POST':
        try:
            join_data = RoomJoin(
                room_code=request.POST.get('room_code', ''),
                password=request.POST.get('password', ''),
            )
        except ValidationError as e:
            for msg in format_pydantic_errors(e).values():
                messages.error(request, msg)
            return redirect('dashboard')

        if join_data.room.password:
            authorized_rooms = request.session.get('authorized_rooms', [])
            if join_data.room.room_code not in authorized_rooms:
                authorized_rooms.append(join_data.room.room_code)
                request.session['authorized_rooms'] = authorized_rooms

        return redirect('room', room_code=join_data.room.room_code)

    return redirect('dashboard')


@login_required
def room_view(request, room_code):
    """Render the room page. Actual joining happens via WebSocket."""
    room = get_object_or_404(Room, room_code=room_code)
    is_owner = room.owner == request.user

    if room.password and not is_owner:
        has_accepted_invite = services.has_accepted_room_invitation(request.user, room)

        authorized_rooms = request.session.get('authorized_rooms', [])
        if not has_accepted_invite and room.room_code not in authorized_rooms:
            messages.error(request, 'This room is protected. Please join using the password on the dashboard.')
            return redirect('dashboard')

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
