from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Q
from django.templatetags.static import static
from django.views.decorators.csrf import ensure_csrf_cookie
from pydantic import ValidationError

from roomchat.errors import api_login_required, format_pydantic_errors, require_POST_json
from roomchat.middleware import json_validation_errors

from .models import Room, RoomBan, RoomMembership, Message, RoomInvitation
from accounts.models import Friendship
from accounts.views import user_payload
from .schemas import (
    RoomCreate,
    RoomJoin,
    RoomCreatedResponse,
    RoomDetailResponse,
    RoomInvitationResponse,
    RoomSummaryResponse,
    MessageResponse,
    DashboardResponse,
    DashboardFriendResponse,
    DashboardFriendRequestResponse,
)

from . import services


@ensure_csrf_cookie
def spa(request, *args, **kwargs):
    """Serve the React shell for every non-API route.

    @ensure_csrf_cookie is load-bearing: Django only sets the csrftoken cookie when a
    view reads the token, and every write the SPA performs sends it back as an
    X-CSRFToken header. Without this the first POST after a cold load fails with 403.
    """
    bootstrap = {
        # Bootstrapped rather than fetched so the router can redirect on first paint
        # instead of flashing a signed-out UI while /api/auth/me/ is in flight.
        'user': user_payload(request.user) if request.user.is_authenticated else None,
        # Asset URLs must be resolved here, never hardcoded in the bundle: the staticfiles
        # storage renames collected files, so only a static()-resolved path survives.
        'heroImage': static('react/img/hero.jpg'),
    }
    return render(request, 'index.html', {'bootstrap': bootstrap})


@api_login_required
def dashboard_api(request):
    """Everything the dashboard renders on load: friends, incoming friend requests,
    pending room invitations, and which room (if any) the user is currently in."""
    friendships = Friendship.objects.filter(
        Q(sender=request.user, status='accepted') |
        Q(receiver=request.user, status='accepted')
    ).select_related('sender', 'receiver')

    friends = []
    for f in friendships:
        friend_user = f.receiver if f.sender == request.user else f.sender
        membership = RoomMembership.objects.filter(user=friend_user).select_related('room').first()
        friends.append(DashboardFriendResponse(
            friendship_id=f.id,
            user_id=friend_user.id,
            username=friend_user.username,
            current_room_code=membership.room.room_code if membership else None,
            current_room_name=membership.room.name if membership else None,
        ))

    pending_requests = [
        DashboardFriendRequestResponse(
            id=f.id,
            sender_id=f.sender.id,
            sender_username=f.sender.username,
            created_at=f.created_at,
        )
        for f in Friendship.objects.filter(
            receiver=request.user, status='pending'
        ).select_related('sender')
    ]

    pending_invitations = [
        RoomInvitationResponse(
            id=inv.id,
            room_code=inv.room.room_code,
            room_name=inv.room.name,
            sender_username=inv.sender.username,
            created_at=inv.created_at,
            is_protected=bool(inv.room.password),
        )
        for inv in services.get_pending_invitations(request.user)
    ]

    membership = RoomMembership.objects.filter(user=request.user).select_related('room').first()

    payload = DashboardResponse(
        friends=friends,
        pending_requests=pending_requests,
        pending_invitations=pending_invitations,
        current_room_code=membership.room.room_code if membership else None,
    )
    return JsonResponse(payload.model_dump(mode='json'))


@api_login_required
@require_POST_json
def create_room(request):
    """Create a new chat room and return its code."""
    try:
        room_data = RoomCreate(
            name=request.POST.get('name', ''),
            description=request.POST.get('description', ''),
            capacity=request.POST.get('capacity', '10'),
            password=request.POST.get('password', ''),
        )
    except ValidationError as e:
        return JsonResponse({'errors': format_pydantic_errors(e)}, status=400)

    room = services.create_room(request.user, room_data)

    # No grant needed: the creator is the owner, and owners bypass the gate.
    return JsonResponse(RoomCreatedResponse(room_code=room.room_code).model_dump(mode='json'))


@api_login_required
@require_POST_json
def join_room(request):
    """Verify a room code and optional password, then unlock the room for this session."""
    try:
        join_data = RoomJoin(
            room_code=request.POST.get('room_code', ''),
            password=request.POST.get('password', ''),
        )
    except ValidationError as e:
        return JsonResponse({'errors': format_pydantic_errors(e)}, status=400)

    # A correct password does not undo a ban, and a grant must never point at a
    # room the user cannot enter. Owners never hold a ban row, so no exemption.
    if RoomBan.objects.filter(room=join_data.room, user=request.user).exists():
        return JsonResponse({'error': 'You have been removed from this room.'}, status=403)

    # RoomJoin has already verified the password; unlock the room for as long as
    # the user stays connected to it. One slot, so this replaces any prior grant.
    request.session['room_grant'] = join_data.room.room_code

    return JsonResponse(
        RoomCreatedResponse(room_code=join_data.room.room_code).model_dump(mode='json')
    )


@api_login_required
def room_detail_api(request, room_code):
    """Room metadata plus message history, behind the room-access gates.

    The order of the checks below is the security spine of the app — see CLAUDE.md.
    Actual joining still happens over the WebSocket.
    """
    room = Room.objects.filter(room_code=room_code).select_related('owner').first()
    if room is None:
        return JsonResponse({'error': 'This room no longer exists.'}, status=404)

    is_owner = room.owner == request.user

    # A ban is session-independent, so it is checked before anything else: the
    # WebSocket gate alone would still let a banned user load the page and receive
    # the message history below. Sitting above the password gate also closes the
    # invitation bypass for free — we return before the invitation branch runs, so a
    # friend re-inviting a banned user cannot mint a grant.
    if not is_owner and RoomBan.objects.filter(room=room, user=request.user).exists():
        return JsonResponse({'error': 'You have been removed from this room.'}, status=403)

    # The gate runs before the history query below, so a user who has not unlocked
    # the room never receives any of its messages.
    if room.password and not is_owner and request.session.get('room_grant') != room.room_code:
        # An accepted invitation admits the user exactly once: consume the row and
        # mint the same grant a correct password would have. This is the only place
        # an invitation grants access, which is why the WebSocket gate can stay a
        # plain session check.
        invite = RoomInvitation.objects.filter(
            room=room, receiver=request.user, status='accepted'
        ).first()
        if not invite:
            return JsonResponse(
                {'error': 'This room is protected. Please join using the password on the dashboard.'},
                status=403,
            )

        invite.delete()
        request.session['room_grant'] = room.room_code

    history = Message.objects.filter(room=room).select_related(
        'sender', 'reply_to', 'reply_to__sender'
    ).order_by('created_at')[:100]

    payload = RoomDetailResponse(
        room=RoomSummaryResponse(
            room_code=room.room_code,
            name=room.name,
            description=room.description,
            capacity=room.capacity,
            owner_id=room.owner.id,
            owner_username=room.owner.username,
            is_protected=bool(room.password),
        ),
        is_owner=is_owner,
        messages=[
            MessageResponse(
                message_id=m.id,
                sender_id=m.sender.id,
                sender_username=m.sender.username,
                content=m.content,
                created_at=m.created_at,
                edited_at=m.edited_at,
                is_deleted=m.is_deleted,
                # Same three keys the consumer's get_message_preview emits, so the
                # SPA renders history and live messages through one code path.
                reply_to={
                    'message_id': m.reply_to.id,
                    'sender_username': m.reply_to.sender.username,
                    'content': m.reply_to.content[:100],
                } if m.reply_to else None,
            )
            for m in history
        ],
    )
    return JsonResponse(payload.model_dump(mode='json'))


@api_login_required
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
            created_at=inv.created_at,
            is_protected=bool(inv.room.password),
        )
        for inv in invitations
    ]

    return JsonResponse({'invitations': [item.model_dump(mode='json') for item in data]})
