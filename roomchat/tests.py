"""RoomChat test suite (pytest + pytest-asyncio).

Run with `.venv/bin/pytest`. It needs Postgres and Redis up, and no dev server using the
same Redis. The suite builds its own database, test_<DB_NAME>, and drops it at the end.
"""

import os
from pathlib import Path

from dotenv import dotenv_values

# --- Test settings: must run before anything imports roomchat.settings ------------------
# roomchat/db.py builds the engine from DB_NAME the moment it is imported, so the test DB
# name has to be in the environment first. Otherwise TRUNCATE would wipe the dev DB.
# Env vars that are already set win over .env, so these lines override it.
_BASE_DIR = Path(__file__).resolve().parent.parent
_dev_db_name = os.environ.get('DB_NAME') or dotenv_values(_BASE_DIR / '.env').get('DB_NAME')
if not _dev_db_name:
    raise RuntimeError('DB_NAME is not set (env or .env), so there is no test DB name to derive.')
os.environ['DB_NAME'] = f'test_{_dev_db_name}'
os.environ['DEBUG'] = 'True'  # cookies without Secure, so the http test client sends them
os.environ['ALLOWED_HOSTS'] = '127.0.0.1'  # the host the test client and sockets use
os.environ['CSRF_TRUSTED_ORIGINS'] = ''

# Project imports come after the lines above on purpose.
import asyncio  # noqa: E402
import json  # noqa: E402
from urllib.parse import unquote, urlsplit  # noqa: E402

import pytest  # noqa: E402
import redis  # noqa: E402
from alembic import command as alembic_command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from asgiref.testing import ApplicationCommunicator  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from sqlalchemy import create_engine, exists, select, text  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.routing import Router  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from accounts.models import Friendship  # noqa: E402
from accounts.schemas import UserCreate  # noqa: E402
from rooms import services  # noqa: E402
from rooms.consumers import CLOSE_BANNED, CLOSE_NOT_AUTHENTICATED, ChatConsumer  # noqa: E402
from rooms.models import Message, Room, RoomBan, RoomInvitation, RoomMembership  # noqa: E402
from rooms.routing import websocket_urlpatterns  # noqa: E402
from rooms.schemas import RoomCreate, WSFriendRequestReceivedEvent  # noqa: E402
from roomchat import settings  # noqa: E402
from roomchat.asgi import application  # noqa: E402
from roomchat.auth import (  # noqa: E402
    HASH_SESSION_KEY, SESSION_KEY, create_user, get_session_auth_hash, make_password,
)
from roomchat.db import Base, db, db_scope, engine  # noqa: E402
from roomchat.errors import format_pydantic_errors  # noqa: E402
from roomchat.middleware import (  # noqa: E402
    CSRF_COOKIE_NAME, SAFE_METHODS, PydanticValidationErrorMiddleware, json_validation_errors,
)
from roomchat.realtime import RedisChannelLayer, get_channel_layer  # noqa: E402
from roomchat.sessions import SESSION_COOKIE_NAME, SessionStore  # noqa: E402

TEST_DB_NAME = settings.DATABASES['default']['NAME']
# Last line of defence: never let the per-test TRUNCATE near a non-test database.
if not TEST_DB_NAME.startswith('test_') or engine.url.database != TEST_DB_NAME:
    raise RuntimeError(f'Refusing to run: the engine points at {engine.url.database!r}, not a test_ DB.')

HOST = '127.0.0.1'
# Not 'localhost': Python's cookie jar files localhost cookies under 'localhost.local', so a
# cookie set by hand (force_login) would sit next to the server's copy instead of replacing it.
BASE_URL = f'http://{HOST}'


# --- Fixtures ----------------------------------------------------------------------------
# A fixture is a setUp that pytest hands to any test (or other fixture) naming it as an
# argument. The code after `yield` is its tearDown. autouse=True runs it for every test.

def _check_redis_is_idle():
    """Stop the run if Redis is unreachable or a dev server is already listening on it.

    Redis pub/sub ignores the DB number, so a running dev server on the same Redis would share
    group names like asgi__group__user_1 with the tests and receive their broadcasts.
    """
    client = redis.Redis.from_url(settings.REDIS_URL)
    try:
        busy = client.pubsub_channels('asgi*')  # every channel/group our layer subscribes to
    except redis.exceptions.ConnectionError as e:
        pytest.exit(f'Redis is not reachable at {settings.REDIS_URL} ({e}). Start Redis first.', returncode=1)
    finally:
        client.close()
    if busy:
        pytest.exit(
            f'Redis at {settings.REDIS_URL} already has {len(busy)} asgi* subscriptions: a dev '
            'server seems to be using it. Stop it before running the tests.', returncode=1,
        )


@pytest.fixture(scope='session', autouse=True)
def _test_database():
    """Build test_<DB_NAME> once for the whole run with the real migrations; drop it at the end."""
    _check_redis_is_idle()
    # CREATE/DROP DATABASE can't run inside a transaction, hence AUTOCOMMIT, and they can't
    # target the DB you're connected to, hence the 'postgres' maintenance DB.
    admin_engine = create_engine(engine.url.set(database='postgres'), isolation_level='AUTOCOMMIT')
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"'))  # left by a crashed run
        conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    alembic_command.upgrade(AlembicConfig(str(_BASE_DIR / 'alembic.ini')), 'head')

    yield

    engine.dispose()  # close the app engine's pooled connections, or the DROP would fail
    with admin_engine.connect() as conn:
        # No FORCE on purpose: a connection the suite leaked makes this fail loudly.
        conn.execute(text(f'DROP DATABASE "{TEST_DB_NAME}"'))
    admin_engine.dispose()


@pytest.fixture(autouse=True)
def _db_scope():
    """Give each test its own `db` session, then empty every table after it.

    Rolling back can't undo the test's writes: the HTTP app and the consumers commit over
    their own connections. So the tables are emptied instead. TRUNCATE ... RESTART IDENTITY
    CASCADE empties them all in one statement, resets id counters to 1, and follows FKs.
    alembic_version isn't in Base.metadata, so it is never touched.
    """
    token = db_scope.set(object())  # a new key = a new `db` session (see roomchat/db.py)
    try:
        yield
    finally:
        # Close the test's session first: an open transaction holds table locks that
        # would make the TRUNCATE below wait forever.
        db.remove()
        db_scope.reset(token)
        tables = ', '.join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as conn:
            conn.execute(text(f'TRUNCATE {tables} RESTART IDENTITY CASCADE'))


class RoomChatClient(TestClient):
    """TestClient that behaves like the SPA's api.js, plus Django's client.session and
    client.force_login.

    TestClient calls the app in-process (no server). Before every unsafe request (POST, ...)
    it copies the current csrftoken cookie into X-CSRFToken and sends a same-site Origin.
    The cookie is re-read every time because login hands out a new token.
    """

    def __init__(self):
        super().__init__(application, base_url=BASE_URL)

    def request(self, method, url, **kwargs):
        """Send one request, adding the CSRF header and Origin to unsafe methods."""
        if method.upper() not in SAFE_METHODS:
            headers = dict(kwargs.pop('headers', None) or {})
            headers.setdefault('Origin', BASE_URL)
            token = self.cookies.get(CSRF_COOKIE_NAME)
            if token:
                headers.setdefault('X-CSRFToken', token)
            kwargs['headers'] = headers
        return super().request(method, url, **kwargs)

    @property
    def session(self):
        """The server-side session behind the sessionid cookie (Django's client.session)."""
        return SessionStore(self.cookies.get(SESSION_COOKIE_NAME))

    def force_login(self, user):
        """Log `user` in without a password: write a logged-in session row and use its cookie."""
        session = SessionStore()
        # The same two keys roomchat.auth.login() stores.
        session[SESSION_KEY] = str(user.id)
        session[HASH_SESSION_KEY] = get_session_auth_hash(user)
        session.save()
        # Same domain the server's own Set-Cookie lands on, so it replaces any earlier login.
        self.cookies.set(SESSION_COOKIE_NAME, session.session_key, domain=HOST)


@pytest.fixture
def client():
    """A RoomChatClient that already holds a csrftoken, like a browser after a cold load."""
    client = RoomChatClient()
    client.get('/')  # the SPA shell is @ensure_csrf_cookie, so this sets csrftoken
    yield client
    client.close()


class WebsocketCommunicator(ApplicationCommunicator):
    """Drives a WebSocket app in-process, with the method names of Channels' version.

    ApplicationCommunicator (asgiref) runs an ASGI app as a task and lets the test push
    messages in (send_input) and pull what the app sent out (receive_output). Like Channels,
    the test may fill scope['user'] / scope['session'] after building it: the app only
    starts on the first send or receive.
    """

    def __init__(self, application, path, headers=None):
        parsed = urlsplit(path)
        scope = {
            'type': 'websocket',
            'path': unquote(parsed.path),
            'raw_path': parsed.path.encode(),
            'query_string': parsed.query.encode(),
            # AllowedHostsOriginValidator refuses sockets without an allowed Origin.
            'headers': headers if headers is not None else [(b'origin', BASE_URL.encode())],
            'subprotocols': [],
        }
        super().__init__(application, scope)

    async def connect(self, timeout=1):
        """Open the socket. Returns (True, subprotocol) if accepted, (False, code) if refused."""
        await self.send_input({'type': 'websocket.connect'})
        response = await self.receive_output(timeout)
        if response['type'] == 'websocket.close':
            return (False, response.get('code', 1000))
        return (True, response.get('subprotocol', None))

    async def send_json_to(self, data):
        """Send one JSON text frame to the app, as the browser would."""
        await self.send_input({'type': 'websocket.receive', 'text': json.dumps(data)})

    async def receive_json_from(self, timeout=1):
        """Wait for the next text frame from the app and decode its JSON."""
        response = await self.receive_output(timeout)
        assert response['type'] == 'websocket.send', response
        return json.loads(response['text'])

    async def disconnect(self, code=1000, timeout=1):
        """Close from the browser side and wait for the app (and its disconnect()) to finish."""
        await self.send_input({'type': 'websocket.disconnect', 'code': code})
        await self.wait(timeout)


def create(model, **fields):
    """Insert one row and commit it: the stand-in for Django's Model.objects.create().

    Committing matters: the app reads over its own DB connections, so it only sees committed rows.
    """
    obj = model(**fields)
    db.add(obj)
    db.commit()
    return obj


# --- Tests -------------------------------------------------------------------------------

def _validation_error(model, **kwargs):
    try:
        model(**kwargs)
    except ValidationError as e:
        return e
    raise AssertionError(f"{model} did not raise ValidationError for {kwargs}")


class FormatPydanticErrorsTests:
    def test_missing_required_field(self):
        exc = _validation_error(UserCreate, username='', email='', password='')
        errors = format_pydantic_errors(exc)
        assert 'email' in errors

    def test_invalid_email_message_is_friendly(self):
        exc = _validation_error(UserCreate, username='alice', email='not-an-email', password='hunter22')
        errors = format_pydantic_errors(exc)
        assert errors['email'] == 'Enter a valid email address.'

    def test_custom_validator_message_strips_value_error_prefix(self):
        exc = _validation_error(RoomCreate, name='', description='', capacity='10', password='')
        errors = format_pydantic_errors(exc)
        assert 'Value error,' not in errors.get('name', '')


class ConfirmPasswordTests:
    """UserCreate.confirm_password must report under its own field name.

    A @model_validator would land on '__all__', which the Django template
    language cannot render (variables may not start with an underscore), so the
    check lives in a field validator reading info.data instead.
    """

    def test_matching_passwords_validate(self):
        user = UserCreate(
            username='alice', email='alice@example.com',
            password='hunter22', confirm_password='hunter22',
        )
        assert user.password == 'hunter22'

    def test_mismatch_reports_on_confirm_password(self):
        exc = _validation_error(
            UserCreate, username='alice', email='alice@example.com',
            password='hunter22', confirm_password='hunter33',
        )
        errors = format_pydantic_errors(exc)
        assert errors['confirm_password'] == 'The two passwords do not match.'

    def test_blank_confirmation_is_reported(self):
        exc = _validation_error(
            UserCreate, username='alice', email='alice@example.com',
            password='hunter22', confirm_password='',
        )
        errors = format_pydantic_errors(exc)
        assert errors['confirm_password'] == 'Please confirm your password.'

    def test_bad_password_does_not_also_report_a_mismatch(self):
        # password is absent from info.data once it fails, so the match check is
        # skipped rather than firing a second, misleading error.
        exc = _validation_error(
            UserCreate, username='alice', email='alice@example.com',
            password='short', confirm_password='short',
        )
        errors = format_pydantic_errors(exc)
        assert errors['password'] == 'Password must be at least 8 characters long.'
        assert 'confirm_password' not in errors


class PydanticValidationErrorMiddlewareTests:
    """The middleware is pure ASGI now, so it is driven as one: it wraps a tiny fake inner
    app that raises, and the test collects every message it sends back. "Ignores" means
    the exception passes straight through (Django's process_exception returned None)."""

    @pytest.fixture(autouse=True)
    def setUp(self):
        """Build the ValidationError the tests raise."""
        self.exc = _validation_error(UserCreate, username='', email='', password='')

    async def _run(self, exc, opted_in):
        """Run the middleware around an inner app that raises `exc`; return what it sent."""
        async def inner_app(scope, receive, send):
            # Stands in for the routed view that raised.
            raise exc

        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}

        sent = []

        async def send(message):
            sent.append(message)

        # @json_validation_errors puts this flag in request.state, i.e. scope['state'].
        state = {'_json_validation_errors': True} if opted_in else {}
        scope = {'type': 'http', 'method': 'POST', 'path': '/', 'headers': [], 'state': state}
        await PydanticValidationErrorMiddleware(inner_app)(scope, receive, send)
        return sent

    async def test_ignores_non_validation_errors(self):
        with pytest.raises(ValueError):
            await self._run(ValueError('boom'), opted_in=True)

    async def test_ignores_validation_error_when_not_opted_in(self):
        with pytest.raises(ValidationError):
            await self._run(self.exc, opted_in=False)

    async def test_returns_json_400_when_opted_in(self):
        sent = await self._run(self.exc, opted_in=True)
        assert sent  # a response was sent
        assert sent[0]['status'] == 400
        assert b'"errors"' in sent[1]['body']


class JsonValidationErrorsDecoratorTests:
    def test_sets_flag_on_request_before_calling_view(self):
        seen = {}

        def view(request):
            seen['flag'] = getattr(request.state, '_json_validation_errors', False)
            return 'ok'

        wrapped = json_validation_errors(view)
        request = Request({'type': 'http'})  # a bare request, no flag set yet
        result = wrapped(request)

        assert seen['flag']
        assert result == 'ok'


class RedisChannelLayerTests:
    """The channel layer must carry broadcasts between *independent* layer
    instances.

    Every test here builds two layers from the same settings and sends through
    one while receiving through the other. That is the whole reason for moving
    off InMemoryChannelLayer: a single-instance round-trip passes on the
    in-memory layer too, so it would prove nothing. Two instances stand in for
    two ASGI worker processes.

    Requires a running Redis at settings.REDIS_URL; there is no in-memory
    fallback, so a connection failure here is a real failure.
    """

    # Generous enough to absorb a slow first connection, short enough that a
    # broken layer fails the suite instead of hanging it.
    TIMEOUT = 5
    # Used when asserting a message must *not* arrive.
    SILENCE_TIMEOUT = 0.5

    def _layer(self):
        return RedisChannelLayer(**settings.CHANNEL_LAYERS['default']['CONFIG'])

    def test_configured_backend_is_redis_pubsub(self):
        assert settings.CHANNEL_LAYERS['default']['BACKEND'] == 'roomchat.realtime.RedisChannelLayer'
        assert isinstance(get_channel_layer(), RedisChannelLayer)

    def test_config_omits_options_the_pubsub_layer_ignores(self):
        # capacity/expiry/group_expiry are core-layer options. A pub/sub layer has no
        # backpressure, so leaving them in CONFIG would read as working
        # backpressure that does not exist.
        config = settings.CHANNEL_LAYERS['default']['CONFIG']
        assert config['hosts'] == [settings.REDIS_URL]
        for ignored in ('capacity', 'expiry', 'group_expiry'):
            assert ignored not in config

    async def test_group_send_crosses_layer_instances(self):
        """room_<code> broadcasts — messages, presence, moderation."""
        sender, receiver = self._layer(), self._layer()
        try:
            channel = await receiver.new_channel()
            await receiver.group_add('room_ABC123', channel)

            event = {'type': 'message_created', 'message_id': 1, 'content': 'hi'}
            await sender.group_send('room_ABC123', event)

            got = await asyncio.wait_for(receiver.receive(channel), self.TIMEOUT)
            assert got == event
        finally:
            await sender.flush()
            await receiver.flush()

    async def test_group_send_reaches_every_subscriber(self):
        """A broadcast fans out to all members, not just the first one."""
        sender, receiver_a, receiver_b = self._layer(), self._layer(), self._layer()
        try:
            channel_a = await receiver_a.new_channel()
            channel_b = await receiver_b.new_channel()
            await receiver_a.group_add('room_ABC123', channel_a)
            await receiver_b.group_add('room_ABC123', channel_b)

            event = {'type': 'user_joined', 'username': 'alice', 'user_id': 1}
            await sender.group_send('room_ABC123', event)

            assert await asyncio.wait_for(receiver_a.receive(channel_a), self.TIMEOUT) == event
            assert await asyncio.wait_for(receiver_b.receive(channel_b), self.TIMEOUT) == event
        finally:
            await sender.flush()
            await receiver_a.flush()
            await receiver_b.flush()

    async def test_direct_channel_send_crosses_layer_instances(self):
        """The kick path: ChatConsumer.handle_kick_user sends to one stored
        channel_name, which now lives in another process."""
        sender, receiver = self._layer(), self._layer()
        try:
            channel = await receiver.new_channel()

            event = {'type': 'user_kicked', 'message': 'You have been kicked.'}
            await sender.send(channel, event)

            got = await asyncio.wait_for(receiver.receive(channel), self.TIMEOUT)
            assert got == event
        finally:
            await sender.flush()
            await receiver.flush()

    async def test_group_discard_stops_delivery(self):
        """Disconnect must actually unsubscribe, or a closed socket's channel
        keeps collecting broadcasts."""
        sender, receiver = self._layer(), self._layer()
        try:
            channel = await receiver.new_channel()
            await receiver.group_add('room_ABC123', channel)
            await receiver.group_discard('room_ABC123', channel)

            await sender.group_send('room_ABC123', {'type': 'user_left'})

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(receiver.receive(channel), self.SILENCE_TIMEOUT)
        finally:
            await sender.flush()
            await receiver.flush()

    async def test_groups_are_isolated_from_each_other(self):
        sender, receiver = self._layer(), self._layer()
        try:
            channel = await receiver.new_channel()
            await receiver.group_add('room_ABC123', channel)

            await sender.group_send('room_XYZ789', {'type': 'message_created'})

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(receiver.receive(channel), self.SILENCE_TIMEOUT)
        finally:
            await sender.flush()
            await receiver.flush()

    async def test_pydantic_event_survives_the_round_trip(self):
        """Events go over the wire as model_dump(mode='json') and are forwarded
        verbatim by the handler, so msgpack must return them unchanged."""
        sender, receiver = self._layer(), self._layer()
        try:
            channel = await receiver.new_channel()
            await receiver.group_add('user_1', channel)

            event = WSFriendRequestReceivedEvent(
                friendship_id=7, sender_username='alice', sender_id=2,
            ).model_dump(mode='json')
            await sender.group_send('user_1', event)

            got = await asyncio.wait_for(receiver.receive(channel), self.TIMEOUT)
            assert got == event
            # The type literal is what group_send dispatches on.
            assert got['type'] == 'friend_request_received'
        finally:
            await sender.flush()
            await receiver.flush()


class NotificationConsumerCrossProcessTests:
    """End-to-end proof: a live NotificationConsumer receives an event sent from
    a channel layer instance it does not share.

    This is the exact path accounts.views.notify_friend_request takes — a
    synchronous HTTP view on one process reaching a socket held by another.
    """

    TIMEOUT = 5

    @pytest.fixture(autouse=True)
    def setUp(self):
        """Create the user whose notification socket is opened."""
        self.user = create_user('alice', password='x')

    async def test_friend_request_reaches_socket_from_another_layer_instance(self):
        communicator = WebsocketCommunicator(
            Router(websocket_urlpatterns), '/ws/notifications/',
        )
        communicator.scope['user'] = self.user
        communicator.scope['session'] = {}

        connected, _ = await communicator.connect()
        assert connected

        # A separate layer object: the consumer above subscribed through
        # get_channel_layer(), this publishes through its own Redis connection.
        sender = RedisChannelLayer(**settings.CHANNEL_LAYERS['default']['CONFIG'])
        try:
            event = WSFriendRequestReceivedEvent(
                friendship_id=1, sender_username='bob', sender_id=self.user.id + 1,
            ).model_dump(mode='json')
            await sender.group_send(f'user_{self.user.id}', event)

            got = await asyncio.wait_for(
                communicator.receive_json_from(self.TIMEOUT), self.TIMEOUT,
            )
            assert got == event
        finally:
            await sender.flush()
            await communicator.disconnect()


class ChatConsumerPasswordGateTests:
    """The WS gate is a plain session check: owners bypass, everyone else needs
    session['room_grant'] to hold this room's code.

    room_detail_api is the only thing that mints a grant — including from an accepted
    invitation — so an invitation alone does not open a socket."""

    @pytest.fixture(autouse=True)
    def setUp(self):
        """Create the owner, another user, and a password-protected room."""
        self.owner = create_user('owner', password='x')
        self.other = create_user('other', password='x')
        # Non-empty password marks the room protected; the gate only checks
        # truthiness, so the value need not be a real hash.
        self.room = create(Room, name='Secret', owner=self.owner, password='hashed')

    def _communicator(self, user, session=None):
        communicator = WebsocketCommunicator(
            Router(websocket_urlpatterns),
            f'/ws/chat/{self.room.room_code}/',
        )
        communicator.scope['user'] = user
        communicator.scope['session'] = session or {}
        return communicator

    async def _assert_rejected(self, communicator, code=CLOSE_NOT_AUTHENTICATED):
        connected, _ = await communicator.connect()
        # reject() accepts before closing, so connected is True either way.
        assert connected
        error = await communicator.receive_json_from()
        assert error['type'] == 'error'
        close = await communicator.receive_output()
        assert close['type'] == 'websocket.close'
        assert close['code'] == code
        await communicator.disconnect()

    async def _assert_admitted(self, communicator):
        connected, _ = await communicator.connect()
        assert connected
        # First frame after a successful join is a real event, not the error
        # frame that precedes a rejection close.
        first = await communicator.receive_json_from()
        assert first['type'] != 'error'
        await communicator.disconnect()

    async def test_user_without_grant_is_rejected(self):
        await self._assert_rejected(self._communicator(self.other))

    async def test_owner_bypasses_password(self):
        await self._assert_admitted(self._communicator(self.owner))

    async def test_accepted_invite_alone_is_rejected(self):
        # The invitation is consumed by room_detail_api, not read here.
        # (A plain sync insert: nothing else is running on the loop at this point.)
        create(
            RoomInvitation, room=self.room, sender=self.owner, receiver=self.other,
            status='accepted',
        )
        await self._assert_rejected(self._communicator(self.other))

    async def test_matching_grant_is_admitted(self):
        session = {'room_grant': self.room.room_code}
        await self._assert_admitted(self._communicator(self.other, session))

    async def test_grant_for_another_room_is_rejected(self):
        session = {'room_grant': 'OTHER1'}
        await self._assert_rejected(self._communicator(self.other, session))

    async def test_banned_user_is_refused_despite_a_valid_grant(self):
        # A ban is not session state, so the grant that admitted them before the
        # kick no longer helps — and the close code says why.
        create(RoomBan, room=self.room, user=self.other, banned_by=self.owner)
        session = {'room_grant': self.room.room_code}
        await self._assert_rejected(self._communicator(self.other, session), CLOSE_BANNED)


class RoomBanTests:
    """ban_member is the only writer of RoomBan, and it refuses anyone who is
    not currently a member — see the helper's docstring."""

    @pytest.fixture(autouse=True)
    def setUp(self):
        """Create the owner, another user, and a protected room."""
        self.owner = create_user('owner', password='x')
        self.other = create_user('other', password='x')
        self.room = create(Room, name='Secret', owner=self.owner, password='hashed')

    def _consumer(self, user):
        """A consumer instance just complete enough to drive ban_member()."""
        consumer = ChatConsumer()
        consumer.room = self.room
        consumer.user = user
        return consumer

    # The DB checks below are plain sync calls (Django used aexists/acreate/aget): the
    # consumer is idle between awaits, so briefly blocking the loop is harmless here.

    async def test_ban_member_refuses_a_non_member(self):
        # Without the membership requirement a crafted kick_user frame could
        # lock out a user who was never in the room.
        assert not await self._consumer(self.owner).ban_member(self.other.id)
        assert not db.scalar(select(exists().where(RoomBan.room == self.room)))

    async def test_owner_cannot_be_banned(self):
        # FK ids, not room=self.room: setting the relationship would also mark self.room's
        # dynamic `memberships` collection as changed, which ban_member's merge can't copy.
        # Django's acreate never touched self.room either.
        create(RoomMembership, room_id=self.room.id, user_id=self.owner.id)
        assert not await self._consumer(self.owner).ban_member(self.owner.id)
        assert not db.scalar(select(exists().where(RoomBan.room == self.room)))
        assert db.scalar(select(exists().where(
            RoomMembership.room == self.room, RoomMembership.user == self.owner,
        )))

    async def test_ban_member_removes_presence_and_records_the_issuer(self):
        create(RoomMembership, room_id=self.room.id, user_id=self.other.id)  # FK ids: see above
        assert await self._consumer(self.owner).ban_member(self.other.id)
        ban = db.scalars(select(RoomBan).where(RoomBan.room == self.room, RoomBan.user == self.other)).one()
        assert ban.banned_by_id == self.owner.id
        assert not db.scalar(select(exists().where(
            RoomMembership.room == self.room, RoomMembership.user == self.other,
        )))


class RoomBanHTTPGateTests:
    """room_detail_api is the gate that matters: the WS check alone would still let a
    banned user load the room and receive the message history."""

    PASSWORD = 'hunter22'

    @pytest.fixture(autouse=True)
    def setUp(self, client):
        """A protected room with one secret message, and `other` banned and logged in."""
        self.client = client
        self.owner = create_user('owner', password='x')
        self.other = create_user('other', password='x')
        self.room = create(
            Room, name='Secret', owner=self.owner, password=make_password(self.PASSWORD),
        )
        self.secret_line = 'topsecretchatter'
        create(Message, room=self.room, sender=self.owner, content=self.secret_line)
        create(RoomBan, room=self.room, user=self.other, banned_by=self.owner)
        self.client.force_login(self.other)

    def _url(self):
        return f'/api/rooms/{self.room.room_code}/'

    def test_banned_user_is_refused_and_leaks_no_history(self):
        response = self.client.get(self._url())
        assert response.status_code == 403
        assert self.secret_line not in response.text
        assert 'messages' not in response.json()
        assert 'room_grant' not in self.client.session

    def test_accepted_invitation_does_not_override_a_ban(self):
        # Asserts the gate ordering: the ban check returns before the invitation
        # branch, so the invitation is neither consumed nor able to mint a grant.
        create(
            RoomInvitation, room=self.room, sender=self.owner, receiver=self.other, status='accepted',
        )
        response = self.client.get(self._url())
        assert response.status_code == 403
        assert self.secret_line not in response.text
        assert 'room_grant' not in self.client.session
        assert db.scalar(select(exists().where(
            RoomInvitation.room == self.room, RoomInvitation.receiver == self.other,
        )))

    def test_correct_password_does_not_mint_a_grant_for_a_banned_user(self):
        response = self.client.post('/api/rooms/join/', data={
            'room_code': self.room.room_code, 'password': self.PASSWORD,
        })
        assert response.status_code == 403
        assert 'room_grant' not in self.client.session

    def test_invitation_to_a_banned_user_is_refused_with_a_reason(self):
        create(Friendship, sender=self.owner, receiver=self.other, status='accepted')
        result = services.create_room_invitation(self.owner, self.room, self.other.id)
        assert result['error'] == 'That user was removed from this room.'
        assert not db.scalar(select(exists().where(RoomInvitation.room == self.room)))

    def test_deleting_the_room_cascades_the_ban(self):
        # The room's lifetime is the ban's lifetime — that is why there is no
        # expires_at. A recycled room code lands on a new Room row.
        db.delete(self.room)
        db.commit()
        assert not db.scalar(select(exists().where(RoomBan.user == self.other)))


class RoomDetailGateTests:
    """room_detail_api is the HTTP gate; it and join_room are the only two places a
    grant is minted."""

    PASSWORD = 'hunter22'

    @pytest.fixture(autouse=True)
    def setUp(self, client):
        """A protected room with one secret message, an open room, and `other` logged in."""
        self.client = client
        self.owner = create_user('owner', password='x')
        self.other = create_user('other', password='x')
        self.room = create(
            Room, name='Secret', owner=self.owner, password=make_password(self.PASSWORD),
        )
        self.open_room = create(Room, name='Open', owner=self.owner)
        # Distinctive enough that finding it in a response body means the
        # history query ran for someone who had not unlocked the room.
        self.secret_line = 'topsecretchatter'
        create(Message, room=self.room, sender=self.owner, content=self.secret_line)
        self.client.force_login(self.other)

    def _url(self, room):
        return f'/api/rooms/{room.room_code}/'

    def _contents(self, response):
        assert response.status_code == 200
        return [m['content'] for m in response.json()['messages']]

    def test_locked_room_without_grant_is_refused_and_leaks_no_history(self):
        response = self.client.get(self._url(self.room))
        assert response.status_code == 403
        assert self.secret_line not in response.text
        assert 'messages' not in response.json()
        assert 'room_grant' not in self.client.session

    def test_correct_password_mints_grant_and_admits(self):
        response = self.client.post('/api/rooms/join/', data={
            'room_code': self.room.room_code, 'password': self.PASSWORD,
        })
        assert response.status_code == 200
        assert response.json()['room_code'] == self.room.room_code
        assert self.client.session['room_grant'] == self.room.room_code
        assert self.secret_line in self._contents(self.client.get(self._url(self.room)))

    def test_bare_code_with_empty_password_is_rejected(self):
        response = self.client.post('/api/rooms/join/', data={
            'room_code': self.room.room_code, 'password': '',
        })
        assert response.status_code == 400
        assert 'Incorrect room password.' in response.json()['errors'].values()
        assert 'room_grant' not in self.client.session

    def test_accepted_invitation_admits_exactly_once(self):
        create(
            RoomInvitation, room=self.room, sender=self.owner, receiver=self.other, status='accepted',
        )
        assert self.secret_line in self._contents(self.client.get(self._url(self.room)))
        assert not db.scalar(select(exists().where(
            RoomInvitation.room == self.room, RoomInvitation.receiver == self.other,
        )))

        # Stand in for the socket dropping, which is what revokes the grant.
        session = self.client.session
        del session['room_grant']
        session.save()

        again = self.client.get(self._url(self.room))
        assert again.status_code == 403
        assert self.secret_line not in again.text

    def test_owner_needs_no_grant(self):
        self.client.force_login(self.owner)
        assert self.secret_line in self._contents(self.client.get(self._url(self.room)))
        assert 'room_grant' not in self.client.session

    def test_open_room_is_reachable_directly(self):
        assert self.client.get(self._url(self.open_room)).status_code == 200

    def test_unknown_room_is_404_json(self):
        response = self.client.get('/api/rooms/ZZZZZZ/')
        assert response.status_code == 404
        assert response.json()['error'] == 'This room no longer exists.'

    def test_room_payload_never_carries_the_password_hash(self):
        self.client.force_login(self.owner)
        room = self.client.get(self._url(self.room)).json()['room']
        assert room['is_protected']
        assert 'password' not in room

    def test_history_carries_the_reply_preview_shape_the_socket_uses(self):
        parent = db.scalars(
            select(Message).where(Message.room == self.room, Message.content == self.secret_line)
        ).one()
        create(
            Message, room=self.room, sender=self.owner, content='a reply', reply_to=parent,
        )
        self.client.force_login(self.owner)
        messages = self.client.get(self._url(self.room)).json()['messages']
        preview = messages[-1]['reply_to']
        # The same three keys ChatConsumer.get_message_preview emits, so the frontend
        # renders history and live messages through one code path.
        assert set(preview) == {'message_id', 'sender_username', 'content'}
        assert preview['sender_username'] == self.owner.username


class ApiAuthTests:
    """The SPA cannot follow a redirect to an HTML login page, so an unauthenticated
    API call must answer 401 JSON."""

    @pytest.fixture(autouse=True)
    def setUp(self, client):
        """Hand each test the CSRF-primed client."""
        self.client = client

    def test_unauthenticated_api_call_is_401_json(self):
        response = self.client.get('/api/dashboard/')
        assert response.status_code == 401
        assert response.json()['error'] == 'Not authenticated.'

    def test_register_signs_the_user_in(self):
        response = self.client.post('/api/auth/register/', data={
            'username': 'newbie', 'email': 'newbie@example.com',
            'password': 'hunter22', 'confirm_password': 'hunter22',
        })
        assert response.status_code == 200
        assert response.json()['user']['username'] == 'newbie'
        assert self.client.get('/api/dashboard/').status_code == 200

    def test_register_reports_field_errors(self):
        response = self.client.post('/api/auth/register/', data={
            'username': 'newbie', 'email': 'newbie@example.com',
            'password': 'hunter22', 'confirm_password': 'mismatch',
        })
        assert response.status_code == 400
        assert 'confirm_password' in response.json()['errors']

    def test_duplicate_username_is_a_field_error(self):
        create_user('taken', password='hunter22')
        response = self.client.post('/api/auth/register/', data={
            'username': 'taken', 'email': 'taken@example.com',
            'password': 'hunter22', 'confirm_password': 'hunter22',
        })
        assert response.status_code == 400
        assert response.json()['errors']['username'] == 'A user with that username already exists.'

    def test_login_and_logout_round_trip(self):
        create_user('someone', password='hunter22')
        login_res = self.client.post('/api/auth/login/', data={
            'username': 'someone', 'password': 'hunter22',
        })
        assert login_res.status_code == 200
        assert self.client.get('/api/auth/me/').status_code == 200

        assert self.client.post('/api/auth/logout/').status_code == 200
        assert self.client.get('/api/auth/me/').status_code == 401

    def test_bad_credentials_do_not_say_which_half_was_wrong(self):
        create_user('someone', password='hunter22')
        response = self.client.post('/api/auth/login/', data={
            'username': 'someone', 'password': 'wrong',
        })
        assert response.status_code == 400
        assert response.json()['error'] == 'Invalid username or password.'
        assert 'errors' not in response.json()

    def test_logout_rejects_get(self):
        # A GET logout is reachable by a link prefetch or a stray <a href>.
        assert self.client.get('/api/auth/logout/').status_code == 405


class SpaShellTests:
    """Client-side routes must survive a hard refresh, and the shell has to hand the
    SPA a CSRF cookie and the signed-in user."""

    @pytest.fixture(autouse=True)
    def setUp(self, client):
        """Hand each test the CSRF-primed client."""
        self.client = client

    def test_client_routes_serve_the_shell(self):
        # One test looping over the paths (Django's subTest), so the test count is unchanged.
        for path in ('/', '/login', '/dashboard', '/room/ABC123'):
            response = self.client.get(path)
            assert response.status_code == 200, path
            assert 'id="root"' in response.text, path

    def test_shell_sets_the_csrf_cookie(self):
        response = self.client.get('/login')
        assert 'csrftoken' in response.cookies

    def test_shell_bootstraps_the_signed_in_user(self):
        user = create_user('someone', password='x', email='s@example.com')
        self.client.force_login(user)
        response = self.client.get('/dashboard')
        assert response.status_code == 200
        assert 'someone' in response.text
        assert 'roomchat-bootstrap' in response.text

    def test_shell_bootstraps_null_for_anonymous(self):
        response = self.client.get('/dashboard')
        assert response.status_code == 200
        assert '"user": null' in response.text

    def test_api_paths_never_fall_through_to_the_shell(self):
        response = self.client.get('/api/nope/')
        assert response.status_code == 404
        assert 'id="root"' not in response.text
