from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q

from .models import Room, RoomMembership, RoomInvitation, Message
from .forms import CreateRoomForm, JoinRoomForm
from accounts.models import Friendship


@login_required
def dashboard(request):
    """Main dashboard view showing friends, requests, rooms, and invitations."""
    # Get friends
    friendships = Friendship.objects.filter(
        Q(sender=request.user, status='accepted') |
        Q(receiver=request.user, status='accepted')
    )
    friends = []
    for f in friendships:
        friend_user = f.receiver if f.sender == request.user else f.sender
        # Check if friend is in a room
        membership = RoomMembership.objects.filter(user=friend_user).first()
        friends.append({
            'friendship_id': f.id,
            'user': friend_user,
            'current_room': membership.room if membership else None,
        })

    # Get pending friend requests received
    pending_requests = Friendship.objects.filter(
        receiver=request.user, status='pending'
    ).select_related('sender')

    # Get pending room invitations
    pending_invitations = RoomInvitation.objects.filter(
        receiver=request.user, status='pending'
    ).select_related('room', 'sender')

    # Get user's current room membership
    current_membership = RoomMembership.objects.filter(user=request.user).first()

    create_form = CreateRoomForm()
    join_form = JoinRoomForm()

    return render(request, 'rooms/dashboard.html', {
        'friends': friends,
        'pending_requests': pending_requests,
        'pending_invitations': pending_invitations,
        'current_membership': current_membership,
        'create_form': create_form,
        'join_form': join_form,
    })


@login_required
def create_room(request):
    """Create a new chat room."""
    if request.method == 'POST':
        form = CreateRoomForm(request.POST)
        if form.is_valid():
            room = form.save(commit=False)
            room.owner = request.user
            room.save()

            if room.password:
                authorized_rooms = request.session.get('authorized_rooms', [])
                if room.room_code not in authorized_rooms:
                    authorized_rooms.append(room.room_code)
                    request.session['authorized_rooms'] = authorized_rooms

            return redirect('room', room_code=room.room_code)
        else:
            messages.error(request, 'Error creating room. Please check your inputs.')
    return redirect('dashboard')


@login_required
def join_room(request):
    """Join an existing room by code and optional password."""
    if request.method == 'POST':
        form = JoinRoomForm(request.POST)
        if form.is_valid():
            room_code = form.cleaned_data['room_code'].upper().strip()
            password = form.cleaned_data['password']

            try:
                room = Room.objects.get(room_code=room_code)
            except Room.DoesNotExist:
                messages.error(request, 'Room not found. Check the code and try again.')
                return redirect('dashboard')

            # Check password
            if room.password and not check_password(password, room.password):
                messages.error(request, 'Incorrect room password.')
                return redirect('dashboard')

            # Check capacity
            if room.is_full:
                messages.error(request, 'Room is full.')
                return redirect('dashboard')

            # Authorize session for this password-protected room
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

    # Fetch the last 100 historical messages for initial render
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

    data = []
    for inv in invitations:
        data.append({
            'id': inv.id,
            'room_code': inv.room.room_code,
            'room_name': inv.room.name,
            'sender_username': inv.sender.username,
            'created_at': inv.created_at.isoformat(),
        })

    return JsonResponse({'invitations': data})
