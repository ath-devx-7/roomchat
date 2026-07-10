from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db.models import Q

import re
from pydantic import ValidationError

from roomchat.errors import format_pydantic_errors
from roomchat.middleware import json_validation_errors

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Friendship
from .schemas import (
    UserCreate,
    UserLogin,
    FriendItemResponse,
    FriendPendingReceivedResponse,
    FriendPendingSentResponse,
    FriendsListResponse,
)


def notify_friend_request(friendship):
    """Push a friend request to the receiver's notification socket."""
    from rooms.schemas import WSFriendRequestReceivedEvent

    event = WSFriendRequestReceivedEvent(
        friendship_id=friendship.id,
        sender_username=friendship.sender.username,
        sender_id=friendship.sender.id,
    )
    async_to_sync(get_channel_layer().group_send)(
        f'user_{friendship.receiver.id}',
        event.model_dump(mode='json'),
    )


def register_view(request):
    """Handle user registration."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    errors = {}
    username = ''
    email = ''

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        try:
            user_data = UserCreate(username=username, email=email, password=password)
            if User.objects.filter(username=user_data.username).exists():
                errors['username'] = 'A user with that username already exists.'
            else:
                user = User.objects.create_user(
                    username=user_data.username,
                    email=user_data.email,
                    password=user_data.password
                )
                login(request, user)
                return redirect('dashboard')
        except ValidationError as e:
            errors = format_pydantic_errors(e)
        except Exception as e:
            errors['username'] = f'Error creating user: {str(e)}'

    return render(request, 'accounts/register.html', {
        'errors': errors,
        'username': username,
        'email': email,
    })


def login_view(request):
    """Handle user login."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    errors = {}
    username = ''

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        try:
            login_data = UserLogin(username=username, password=password)
            user = authenticate(request, username=login_data.username, password=login_data.password)
            if user is not None:
                login(request, user)
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid username or password.')
        except ValidationError as e:
            errors = format_pydantic_errors(e)

    return render(request, 'accounts/login.html', {
        'errors': errors,
        'username': username,
    })



def logout_view(request):
    """Handle user logout."""
    if 'authorized_rooms' in request.session:
        del request.session['authorized_rooms']
    logout(request)
    return redirect('login')


@login_required
def send_friend_request(request):
    """Send a friend request to another user (AJAX)."""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()

        if not username:
            return JsonResponse({'error': 'Username is required.'}, status=400)

        if username == request.user.username:
            return JsonResponse({'error': 'You cannot send a friend request to yourself.'}, status=400)

        try:
            receiver = User.objects.get(username=username)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found.'}, status=404)

        # Check for existing friendship in either direction
        existing = Friendship.objects.filter(
            Q(sender=request.user, receiver=receiver) |
            Q(sender=receiver, receiver=request.user)
        ).first()

        if existing:
            if existing.status == 'accepted':
                return JsonResponse({'error': 'You are already friends with this user.'}, status=400)
            else:
                return JsonResponse({'error': 'A friend request already exists.'}, status=400)

        friendship = Friendship.objects.create(sender=request.user, receiver=receiver, status='pending')
        notify_friend_request(friendship)
        return JsonResponse({'success': True, 'message': f'Friend request sent to {username}.'})

    return JsonResponse({'error': 'Invalid request.'}, status=400)


@login_required
def accept_friend_request(request, friendship_id):
    """Accept a pending friend request (AJAX)."""
    if request.method == 'POST':
        try:
            friendship = Friendship.objects.get(
                id=friendship_id, receiver=request.user, status='pending'
            )
        except Friendship.DoesNotExist:
            return JsonResponse({'error': 'Friend request not found.'}, status=404)

        friendship.status = 'accepted'
        friendship.save()
        return JsonResponse({'success': True, 'message': f'You are now friends with {friendship.sender.username}.'})

    return JsonResponse({'error': 'Invalid request.'}, status=400)


@login_required
def reject_friend_request(request, friendship_id):
    """Reject (delete) a pending friend request (AJAX)."""
    if request.method == 'POST':
        try:
            friendship = Friendship.objects.get(
                id=friendship_id, receiver=request.user, status='pending'
            )
        except Friendship.DoesNotExist:
            return JsonResponse({'error': 'Friend request not found.'}, status=404)

        friendship.delete()
        return JsonResponse({'success': True, 'message': 'Friend request rejected.'})

    return JsonResponse({'error': 'Invalid request.'}, status=400)


@login_required
def remove_friend(request, friendship_id):
    """Remove an existing friend (AJAX)."""
    if request.method == 'POST':
        try:
            friendship = Friendship.objects.get(
                Q(id=friendship_id, status='accepted'),
                Q(sender=request.user) | Q(receiver=request.user)
            )
        except Friendship.DoesNotExist:
            return JsonResponse({'error': 'Friendship not found.'}, status=404)

        friendship.delete()
        return JsonResponse({'success': True, 'message': 'Friend removed.'})

    return JsonResponse({'error': 'Invalid request.'}, status=400)


@login_required
@json_validation_errors
def friends_list_api(request):
    """Return friends and pending requests as JSON."""
    friendships = Friendship.objects.filter(
        Q(sender=request.user, status='accepted') |
        Q(receiver=request.user, status='accepted')
    )
    friends_list = []
    for f in friendships:
        friend_user = f.receiver if f.sender == request.user else f.sender
        friends_list.append(FriendItemResponse(
            id=f.id,
            user_id=friend_user.id,
            username=friend_user.username
        ))

    pending_received = Friendship.objects.filter(
        receiver=request.user, status='pending'
    )
    pending_received_list = [
        FriendPendingReceivedResponse(
            id=f.id,
            sender_id=f.sender.id,
            sender_username=f.sender.username,
            created_at=f.created_at
        )
        for f in pending_received
    ]

    pending_sent = Friendship.objects.filter(
        sender=request.user, status='pending'
    )
    pending_sent_list = [
        FriendPendingSentResponse(
            id=f.id,
            receiver_id=f.receiver.id,
            receiver_username=f.receiver.username,
            created_at=f.created_at
        )
        for f in pending_sent
    ]

    response_data = FriendsListResponse(
        friends=friends_list,
        pending_received=pending_received_list,
        pending_sent=pending_sent_list
    )
    return JsonResponse(response_data.model_dump(mode='json'))
