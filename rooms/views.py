from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import joinedload

from roomchat import settings
from roomchat.db import db
from roomchat.errors import (
    JsonResponse, api_login_required, form_data, format_pydantic_errors, require_POST_json,
)
from roomchat.middleware import ensure_csrf_cookie, json_validation_errors
from roomchat.staticfiles import static

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

# Jinja renders templates/index.html. `static` is made available inside templates so
# index.html can write {{ static('react/css/main.css') }}.
templates = Jinja2Templates(directory=settings.BASE_DIR / 'templates')
templates.env.globals['static'] = static


@ensure_csrf_cookie
def spa(request: Request):
    """Serve the React shell for every non-API route.

    @ensure_csrf_cookie is load-bearing: the csrftoken cookie is only set when a view
    asks for it, and every write the SPA performs sends it back as an X-CSRFToken
    header. Without this the first POST after a cold load fails with 403.
    """
    bootstrap = {
        # Bootstrapped rather than fetched so the router can redirect on first paint
        # instead of flashing a signed-out UI while /api/auth/me/ is in flight.
        'user': user_payload(request.user) if request.user.is_authenticated else None,
        # Asset URLs must be resolved here, never hardcoded in the bundle: static()
        # adds the ?v=<hash> that makes browsers fetch a rebuilt file.
        'heroImage': static('react/img/hero.jpg'),
    }
    return templates.TemplateResponse(request, 'index.html', {'bootstrap': bootstrap})


@api_login_required
def dashboard_api(request: Request):
    """Everything the dashboard renders on load: friends, incoming friend requests,
    pending room invitations, and which room (if any) the user is currently in."""
    # joinedload = Django's select_related: fetch sender and receiver in the same query.
    friendships = db.scalars(select(Friendship).where(or_(
        and_(Friendship.sender == request.user, Friendship.status == 'accepted'),
        and_(Friendship.receiver == request.user, Friendship.status == 'accepted'),
    )).options(joinedload(Friendship.sender), joinedload(Friendship.receiver))).all()

    friends = []
    for f in friendships:
        # Same session as request.user, so `==` finds the same object (identity map).
        friend_user = f.receiver if f.sender == request.user else f.sender
        membership = db.scalars(
            select(RoomMembership).where(RoomMembership.user == friend_user)
            .options(joinedload(RoomMembership.room))
        ).first()
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
        for f in db.scalars(select(Friendship).where(
            Friendship.receiver == request.user, Friendship.status == 'pending'
        ).options(joinedload(Friendship.sender))).all()
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

    membership = db.scalars(
        select(RoomMembership).where(RoomMembership.user == request.user)
        .options(joinedload(RoomMembership.room))
    ).first()

    payload = DashboardResponse(
        friends=friends,
        pending_requests=pending_requests,
        pending_invitations=pending_invitations,
        current_room_code=membership.room.room_code if membership else None,
    )
    return JsonResponse(payload.model_dump(mode='json'))


@api_login_required
@require_POST_json
def create_room(request: Request, form=Depends(form_data)):
    """Create a new chat room and return its code."""
    try:
        room_data = RoomCreate(
            name=form.get('name', ''),
            description=form.get('description', ''),
            capacity=form.get('capacity', '10'),
            password=form.get('password', ''),
        )
    except ValidationError as e:
        return JsonResponse({'errors': format_pydantic_errors(e)}, status=400)

    room = services.create_room(request.user, room_data)

    # No grant needed: the creator is the owner, and owners bypass the gate.
    return JsonResponse(RoomCreatedResponse(room_code=room.room_code).model_dump(mode='json'))


@api_login_required
@require_POST_json
def join_room(request: Request, form=Depends(form_data)):
    """Verify a room code and optional password, then unlock the room for this session."""
    try:
        join_data = RoomJoin(
            room_code=form.get('room_code', ''),
            password=form.get('password', ''),
        )
    except ValidationError as e:
        return JsonResponse({'errors': format_pydantic_errors(e)}, status=400)

    # A correct password does not undo a ban, and a grant must never point at a
    # room the user cannot enter. Owners never hold a ban row, so no exemption.
    if db.scalar(select(exists().where(
        RoomBan.room == join_data.room, RoomBan.user == request.user
    ))):
        return JsonResponse({'error': 'You have been removed from this room.'}, status=403)

    # RoomJoin has already verified the password; unlock the room for as long as
    # the user stays connected to it. One slot, so this replaces any prior grant.
    request.session['room_grant'] = join_data.room.room_code

    return JsonResponse(
        RoomCreatedResponse(room_code=join_data.room.room_code).model_dump(mode='json')
    )


@api_login_required
def room_detail_api(request: Request, room_code: str):
    """Room metadata plus message history, behind the room-access gates.

    The order of the checks below is the security spine of the app — see CLAUDE.md.
    Actual joining still happens over the WebSocket.
    """
    room = db.scalars(
        select(Room).where(Room.room_code == room_code).options(joinedload(Room.owner))
    ).first()
    if room is None:
        return JsonResponse({'error': 'This room no longer exists.'}, status=404)

    is_owner = room.owner == request.user

    # A ban is session-independent, so it is checked before anything else: the
    # WebSocket gate alone would still let a banned user load the page and receive
    # the message history below. Sitting above the password gate also closes the
    # invitation bypass for free — we return before the invitation branch runs, so a
    # friend re-inviting a banned user cannot mint a grant.
    if not is_owner and db.scalar(select(exists().where(
        RoomBan.room == room, RoomBan.user == request.user
    ))):
        return JsonResponse({'error': 'You have been removed from this room.'}, status=403)

    # The gate runs before the history query below, so a user who has not unlocked
    # the room never receives any of its messages.
    if room.password and not is_owner and request.session.get('room_grant') != room.room_code:
        # An accepted invitation admits the user exactly once: consume the row and
        # mint the same grant a correct password would have. This is the only place
        # an invitation grants access, which is why the WebSocket gate can stay a
        # plain session check.
        invite = db.scalars(select(RoomInvitation).where(
            RoomInvitation.room == room,
            RoomInvitation.receiver == request.user,
            RoomInvitation.status == 'accepted',
        )).first()
        if not invite:
            return JsonResponse(
                {'error': 'This room is protected. Please join using the password on the dashboard.'},
                status=403,
            )

        db.delete(invite)
        db.commit()  # rule 2: the invitation is consumed immediately, as in Django
        request.session['room_grant'] = room.room_code

    # The chained joinedload is Django's 'reply_to__sender': the replied-to message and
    # its sender come back in the same query. [:100] becomes .limit(100).
    history = db.scalars(
        select(Message).where(Message.room == room)
        .options(
            joinedload(Message.sender),
            joinedload(Message.reply_to).joinedload(Message.sender),
        )
        .order_by(Message.created_at)
        .limit(100)
    ).all()

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
def get_invitations_api(request: Request):
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
