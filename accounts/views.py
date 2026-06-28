from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db.models import Q

import re

from .models import Friendship


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

        if not username:
            errors['username'] = 'Username is required.'
        elif len(username) > 150:
            errors['username'] = 'Username must be 150 characters or fewer.'
        elif not re.match(r'^[\w.@+-]+$', username):
            errors['username'] = 'Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters.'
        elif User.objects.filter(username=username).exists():
            errors['username'] = 'A user with that username already exists.'

        if not email:
            errors['email'] = 'Email is required.'
        elif not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            errors['email'] = 'Enter a valid email address.'

        if not password:
            errors['password'] = 'Password is required.'
        elif len(password) < 8:
            errors['password'] = 'Password must be at least 8 characters long.'

        if not errors:
            try:
                user = User.objects.create_user(username=username, email=email, password=password)
                login(request, user)
                return redirect('dashboard')
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

        if not username:
            errors['username'] = 'Username is required.'
        if not password:
            errors['password'] = 'Password is required.'

        if not errors:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid username or password.')

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

        Friendship.objects.create(sender=request.user, receiver=receiver, status='pending')
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
def friends_list_api(request):
    """Return friends and pending requests as JSON."""
    friendships = Friendship.objects.filter(
        Q(sender=request.user, status='accepted') |
        Q(receiver=request.user, status='accepted')
    )
    friends = []
    for f in friendships:
        friend_user = f.receiver if f.sender == request.user else f.sender
        friends.append({
            'id': f.id,
            'user_id': friend_user.id,
            'username': friend_user.username,
        })

    pending_received = Friendship.objects.filter(
        receiver=request.user, status='pending'
    )
    pending = []
    for f in pending_received:
        pending.append({
            'id': f.id,
            'sender_id': f.sender.id,
            'sender_username': f.sender.username,
            'created_at': f.created_at.isoformat(),
        })

    pending_sent = Friendship.objects.filter(
        sender=request.user, status='pending'
    )
    sent = []
    for f in pending_sent:
        sent.append({
            'id': f.id,
            'receiver_id': f.receiver.id,
            'receiver_username': f.receiver.username,
            'created_at': f.created_at.isoformat(),
        })

    return JsonResponse({
        'friends': friends,
        'pending_received': pending,
        'pending_sent': sent,
    })
