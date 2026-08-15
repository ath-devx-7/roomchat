from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db.models import Q

from pydantic import ValidationError

from roomchat.errors import api_login_required, format_pydantic_errors, require_POST_json
from roomchat.middleware import json_validation_errors

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Friendship
from .schemas import (
    AuthUserResponse,
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


def user_payload(user) -> dict:
    """Serialize a User for the auth endpoints and the SPA bootstrap."""
    return AuthUserResponse(
        id=user.id, username=user.username, email=user.email
    ).model_dump(mode='json')


@require_POST_json
def register_api(request):
    """Create an account and sign the new user in."""
    if request.user.is_authenticated:
        return JsonResponse({'error': 'Already signed in.'}, status=400)

    try:
        user_data = UserCreate(
            username=request.POST.get('username', ''),
            email=request.POST.get('email', ''),
            # Passwords are never stripped — trimming one silently changes it.
            password=request.POST.get('password', ''),
            confirm_password=request.POST.get('confirm_password', ''),
        )
    except ValidationError as e:
        return JsonResponse({'errors': format_pydantic_errors(e)}, status=400)

    # Keyed under 'username' so the SPA can pin the message to that field, matching
    # how format_pydantic_errors reports every other registration failure.
    if User.objects.filter(username=user_data.username).exists():
        return JsonResponse(
            {'errors': {'username': 'A user with that username already exists.'}}, status=400
        )

    user = User.objects.create_user(
        username=user_data.username,
        email=user_data.email,
        password=user_data.password,
    )
    login(request, user)
    return JsonResponse({'user': user_payload(user)})


@require_POST_json
def login_api(request):
    """Authenticate and open a session."""
    if request.user.is_authenticated:
        return JsonResponse({'error': 'Already signed in.'}, status=400)

    try:
        login_data = UserLogin(
            username=request.POST.get('username', ''),
            password=request.POST.get('password', ''),
        )
    except ValidationError as e:
        return JsonResponse({'errors': format_pydantic_errors(e)}, status=400)

    user = authenticate(request, username=login_data.username, password=login_data.password)
    if user is None:
        # Deliberately not a per-field error: saying which half was wrong tells an
        # attacker whether the username exists.
        return JsonResponse({'error': 'Invalid username or password.'}, status=400)

    login(request, user)
    return JsonResponse({'user': user_payload(user)})


@require_POST_json
def logout_api(request):
    """End the session. POST-only, so a stray link or prefetch cannot sign a user out."""
    logout(request)
    return JsonResponse({'success': True})


@api_login_required
def me_api(request):
    """The signed-in user. The SPA bootstraps from window.__ROOMCHAT__ and only calls
    this to re-check a session it suspects has expired."""
    return JsonResponse({'user': user_payload(request.user)})


@api_login_required
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


@api_login_required
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


@api_login_required
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


@api_login_required
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


@api_login_required
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
