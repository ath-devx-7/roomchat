from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from pydantic import ValidationError

from .models import Room, RoomMembership, RoomInvitation, Message
from accounts.models import Friendship
from .schemas import RoomCreate, RoomJoin, RoomInvitationResponse


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

    pending_invitations = RoomInvitation.objects.filter(
        receiver=request.user, status='pending'
    ).select_related('room', 'sender')

    current_membership = RoomMembership.objects.filter(user=request.user).first()

    return render(request, 'rooms/dashboard.html', {
        'friends': friends,
        'pending_requests': pending_requests,
        'pending_invitations': pending_invitations,
        'current_membership': current_membership,
    })


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
            for error in e.errors():
                msg = error['msg']
                if msg.startswith("Value error, "):
                    msg = msg[len("Value error, "):]
                elif msg.startswith("Field required"):
                    msg = f"{error['loc'][0].capitalize()} is required."
                messages.error(request, msg)
            return redirect('dashboard')

        room = Room.objects.create(
            name=room_data.name,
            description=room_data.description,
            password=make_password(room_data.password) if room_data.password else '',
            capacity=room_data.capacity,
            owner=request.user,
        )

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
                password=request.POST.get('password', '')
            )
        except ValidationError as e:
            for error in e.errors():
                msg = error['msg']
                if msg.startswith("Value error, "):
                    msg = msg[len("Value error, "):]
                elif msg.startswith("Field required"):
                    msg = f"{error['loc'][0].replace('_', ' ').capitalize()} is required."
                messages.error(request, msg)
            return redirect('dashboard')

        try:
            room = Room.objects.get(room_code=join_data.room_code)
        except Room.DoesNotExist:
            messages.error(request, 'Room not found. Check the code and try again.')
            return redirect('dashboard')

        if room.password and not check_password(join_data.password, room.password):
            messages.error(request, 'Incorrect room password.')
            return redirect('dashboard')

        if room.is_full:
            messages.error(request, 'Room is full.')
            return redirect('dashboard')

        if room.password:
            authorized_rooms = request.session.get('authorized_rooms', [])
            if room.room_code not in authorized_rooms:
                authorized_rooms.append(room.room_code)
                request.session['authorized_rooms'] = authorized_rooms

        return redirect('room', room_code=room.room_code)

    return redirect('dashboard')


@login_required
def room_view(request, room_code):
    """Render the room page. Actual joining happens via WebSocket."""
    room = get_object_or_404(Room, room_code=room_code)
    is_owner = room.owner == request.user

    if room.password and not is_owner:
        has_accepted_invite = RoomInvitation.objects.filter(
            room=room, receiver=request.user, status='accepted'
        ).exists()

        authorized_rooms = request.session.get('authorized_rooms', [])
        if not has_accepted_invite and room.room_code not in authorized_rooms:
            messages.error(request, 'This room is protected. Please join using the password on the dashboard.')
            return redirect('dashboard')

    messages_history = Message.objects.filter(room=room).select_related(
        'sender', 'reply_to', 'reply_to__sender'
    ).order_by('created_at')[:100]

    return render(request, 'rooms/room.html', {
        'room': room,
        'is_owner': is_owner,
        'messages_history': messages_history,
    })


@login_required
def get_invitations_api(request):
    """Return pending room invitations as JSON."""
    invitations = RoomInvitation.objects.filter(
        receiver=request.user, status='pending'
    ).select_related('room', 'sender')

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
