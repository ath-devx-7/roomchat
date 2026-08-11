import asyncio
from unittest.mock import Mock

from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from channels_redis.pubsub import RedisPubSubChannelLayer
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from pydantic import ValidationError

from accounts.models import Friendship
from accounts.schemas import UserCreate
from rooms import services
from rooms.consumers import CLOSE_BANNED, CLOSE_NOT_AUTHENTICATED, ChatConsumer
from rooms.models import Message, Room, RoomBan, RoomInvitation, RoomMembership
from rooms.routing import websocket_urlpatterns
from rooms.schemas import RoomCreate, WSFriendRequestReceivedEvent
from roomchat.errors import format_pydantic_errors
from roomchat.middleware import PydanticValidationErrorMiddleware, json_validation_errors


def _validation_error(model, **kwargs):
    try:
        model(**kwargs)
    except ValidationError as e:
        return e
    raise AssertionError(f"{model} did not raise ValidationError for {kwargs}")


class FormatPydanticErrorsTests(SimpleTestCase):
    def test_missing_required_field(self):
        exc = _validation_error(UserCreate, username='', email='', password='')
        errors = format_pydantic_errors(exc)
        self.assertIn('email', errors)

    def test_invalid_email_message_is_friendly(self):
        exc = _validation_error(UserCreate, username='alice', email='not-an-email', password='hunter22')
        errors = format_pydantic_errors(exc)
        self.assertEqual(errors['email'], 'Enter a valid email address.')

    def test_custom_validator_message_strips_value_error_prefix(self):
        exc = _validation_error(RoomCreate, name='', description='', capacity='10', password='')
        errors = format_pydantic_errors(exc)
        self.assertNotIn('Value error,', errors.get('name', ''))


class ConfirmPasswordTests(SimpleTestCase):
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
        self.assertEqual(user.password, 'hunter22')

    def test_mismatch_reports_on_confirm_password(self):
        exc = _validation_error(
            UserCreate, username='alice', email='alice@example.com',
            password='hunter22', confirm_password='hunter33',
        )
        errors = format_pydantic_errors(exc)
        self.assertEqual(errors['confirm_password'], 'The two passwords do not match.')

    def test_blank_confirmation_is_reported(self):
        exc = _validation_error(
            UserCreate, username='alice', email='alice@example.com',
            password='hunter22', confirm_password='',
        )
        errors = format_pydantic_errors(exc)
        self.assertEqual(errors['confirm_password'], 'Please confirm your password.')

    def test_bad_password_does_not_also_report_a_mismatch(self):
        # password is absent from info.data once it fails, so the match check is
        # skipped rather than firing a second, misleading error.
        exc = _validation_error(
            UserCreate, username='alice', email='alice@example.com',
            password='short', confirm_password='short',
        )
        errors = format_pydantic_errors(exc)
        self.assertEqual(errors['password'], 'Password must be at least 8 characters long.')
        self.assertNotIn('confirm_password', errors)


class PydanticValidationErrorMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.get_response = Mock(return_value='response')
        self.middleware = PydanticValidationErrorMiddleware(self.get_response)
        self.exc = _validation_error(UserCreate, username='', email='', password='')

    def test_ignores_non_validation_errors(self):
        request = Mock(_json_validation_errors=True)
        self.assertIsNone(self.middleware.process_exception(request, ValueError('boom')))

    def test_ignores_validation_error_when_not_opted_in(self):
        request = Mock(spec=[])
        self.assertIsNone(self.middleware.process_exception(request, self.exc))

    def test_returns_json_400_when_opted_in(self):
        request = Mock(_json_validation_errors=True)
        response = self.middleware.process_exception(request, self.exc)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'"errors"', response.content)


class JsonValidationErrorsDecoratorTests(SimpleTestCase):
    def test_sets_flag_on_request_before_calling_view(self):
        seen = {}

        def view(request):
            seen['flag'] = getattr(request, '_json_validation_errors', False)
            return 'ok'

        wrapped = json_validation_errors(view)
        request = Mock(spec=[])
        result = wrapped(request)

        self.assertTrue(seen['flag'])
        self.assertEqual(result, 'ok')


class RedisChannelLayerTests(SimpleTestCase):
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
        return RedisPubSubChannelLayer(**settings.CHANNEL_LAYERS['default']['CONFIG'])

    def test_configured_backend_is_redis_pubsub(self):
        self.assertEqual(
            settings.CHANNEL_LAYERS['default']['BACKEND'],
            'channels_redis.pubsub.RedisPubSubChannelLayer',
        )
        self.assertIsInstance(get_channel_layer(), RedisPubSubChannelLayer)

    def test_config_omits_options_the_pubsub_layer_ignores(self):
        # capacity/expiry/group_expiry are core-layer options. The pubsub layer
        # silently drops them, so leaving them in CONFIG would read as working
        # backpressure that does not exist.
        config = settings.CHANNEL_LAYERS['default']['CONFIG']
        self.assertEqual(config['hosts'], [settings.REDIS_URL])
        for ignored in ('capacity', 'expiry', 'group_expiry'):
            self.assertNotIn(ignored, config)

    async def test_group_send_crosses_layer_instances(self):
        """room_<code> broadcasts — messages, presence, moderation."""
        sender, receiver = self._layer(), self._layer()
        try:
            channel = await receiver.new_channel()
            await receiver.group_add('room_ABC123', channel)

            event = {'type': 'message_created', 'message_id': 1, 'content': 'hi'}
            await sender.group_send('room_ABC123', event)

            got = await asyncio.wait_for(receiver.receive(channel), self.TIMEOUT)
            self.assertEqual(got, event)
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

            self.assertEqual(
                await asyncio.wait_for(receiver_a.receive(channel_a), self.TIMEOUT),
                event,
            )
            self.assertEqual(
                await asyncio.wait_for(receiver_b.receive(channel_b), self.TIMEOUT),
                event,
            )
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
            self.assertEqual(got, event)
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

            with self.assertRaises(asyncio.TimeoutError):
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

            with self.assertRaises(asyncio.TimeoutError):
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
            self.assertEqual(got, event)
            # The type literal is what group_send dispatches on.
            self.assertEqual(got['type'], 'friend_request_received')
        finally:
            await sender.flush()
            await receiver.flush()


class NotificationConsumerCrossProcessTests(TransactionTestCase):
    """End-to-end proof: a live NotificationConsumer receives an event sent from
    a channel layer instance it does not share.

    This is the exact path accounts.views.notify_friend_request takes — a
    synchronous HTTP view on one process reaching a socket held by another.
    """

    TIMEOUT = 5

    def setUp(self):
        self.user = User.objects.create_user('alice', password='x')

    async def test_friend_request_reaches_socket_from_another_layer_instance(self):
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns), '/ws/notifications/',
        )
        communicator.scope['user'] = self.user
        communicator.scope['session'] = {}

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # A separate layer object: the consumer above subscribed through
        # get_channel_layer(), this publishes through its own Redis connection.
        sender = RedisPubSubChannelLayer(**settings.CHANNEL_LAYERS['default']['CONFIG'])
        try:
            event = WSFriendRequestReceivedEvent(
                friendship_id=1, sender_username='bob', sender_id=self.user.id + 1,
            ).model_dump(mode='json')
            await sender.group_send(f'user_{self.user.id}', event)

            got = await asyncio.wait_for(
                communicator.receive_json_from(self.TIMEOUT), self.TIMEOUT,
            )
            self.assertEqual(got, event)
        finally:
            await sender.flush()
            await communicator.disconnect()


class ChatConsumerPasswordGateTests(TransactionTestCase):
    """The WS gate is a plain session check: owners bypass, everyone else needs
    session['room_grant'] to hold this room's code.

    room_view is the only thing that mints a grant — including from an accepted
    invitation — so an invitation alone does not open a socket."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', password='x')
        self.other = User.objects.create_user('other', password='x')
        # Non-empty password marks the room protected; the gate only checks
        # truthiness, so the value need not be a real hash.
        self.room = Room.objects.create(
            name='Secret', owner=self.owner, password='hashed'
        )

    def _communicator(self, user, session=None):
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f'/ws/chat/{self.room.room_code}/',
        )
        communicator.scope['user'] = user
        communicator.scope['session'] = session or {}
        return communicator

    async def _assert_rejected(self, communicator, code=CLOSE_NOT_AUTHENTICATED):
        connected, _ = await communicator.connect()
        # reject() accepts before closing, so connected is True either way.
        self.assertTrue(connected)
        error = await communicator.receive_json_from()
        self.assertEqual(error['type'], 'error')
        close = await communicator.receive_output()
        self.assertEqual(close['type'], 'websocket.close')
        self.assertEqual(close['code'], code)
        await communicator.disconnect()

    async def _assert_admitted(self, communicator):
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        # First frame after a successful join is a real event, not the error
        # frame that precedes a rejection close.
        first = await communicator.receive_json_from()
        self.assertNotEqual(first['type'], 'error')
        await communicator.disconnect()

    async def test_user_without_grant_is_rejected(self):
        await self._assert_rejected(self._communicator(self.other))

    async def test_owner_bypasses_password(self):
        await self._assert_admitted(self._communicator(self.owner))

    async def test_accepted_invite_alone_is_rejected(self):
        # The invitation is consumed by room_view, not read here.
        await RoomInvitation.objects.acreate(
            room=self.room, sender=self.owner, receiver=self.other,
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
        await RoomBan.objects.acreate(room=self.room, user=self.other, banned_by=self.owner)
        session = {'room_grant': self.room.room_code}
        await self._assert_rejected(self._communicator(self.other, session), CLOSE_BANNED)


class RoomBanTests(TransactionTestCase):
    """ban_member is the only writer of RoomBan, and it refuses anyone who is
    not currently a member — see the helper's docstring."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', password='x')
        self.other = User.objects.create_user('other', password='x')
        self.room = Room.objects.create(name='Secret', owner=self.owner, password='hashed')

    def _consumer(self, user):
        """A consumer instance just complete enough to drive ban_member()."""
        consumer = ChatConsumer()
        consumer.room = self.room
        consumer.user = user
        return consumer

    async def test_ban_member_refuses_a_non_member(self):
        # Without the membership requirement a crafted kick_user frame could
        # lock out a user who was never in the room.
        self.assertFalse(await self._consumer(self.owner).ban_member(self.other.id))
        self.assertFalse(await RoomBan.objects.filter(room=self.room).aexists())

    async def test_owner_cannot_be_banned(self):
        await RoomMembership.objects.acreate(room=self.room, user=self.owner)
        self.assertFalse(await self._consumer(self.owner).ban_member(self.owner.id))
        self.assertFalse(await RoomBan.objects.filter(room=self.room).aexists())
        self.assertTrue(
            await RoomMembership.objects.filter(room=self.room, user=self.owner).aexists()
        )

    async def test_ban_member_removes_presence_and_records_the_issuer(self):
        await RoomMembership.objects.acreate(room=self.room, user=self.other)
        self.assertTrue(await self._consumer(self.owner).ban_member(self.other.id))
        ban = await RoomBan.objects.aget(room=self.room, user=self.other)
        self.assertEqual(ban.banned_by_id, self.owner.id)
        self.assertFalse(
            await RoomMembership.objects.filter(room=self.room, user=self.other).aexists()
        )


class RoomBanHTTPGateTests(TestCase):
    """room_view is the gate that matters: the WS check alone would still let a
    banned user render the page and receive the message history."""

    PASSWORD = 'hunter22'

    def setUp(self):
        self.owner = User.objects.create_user('owner', password='x')
        self.other = User.objects.create_user('other', password='x')
        self.room = Room.objects.create(
            name='Secret', owner=self.owner, password=make_password(self.PASSWORD),
        )
        self.secret_line = 'topsecretchatter'
        Message.objects.create(room=self.room, sender=self.owner, content=self.secret_line)
        RoomBan.objects.create(room=self.room, user=self.other, banned_by=self.owner)
        self.client.force_login(self.other)

    def _url(self):
        return f'/room/{self.room.room_code}/'

    def test_banned_user_redirects_and_leaks_no_history(self):
        response = self.client.get(self._url(), follow=True)
        self.assertRedirects(response, '/dashboard/')
        self.assertNotContains(response, self.secret_line)
        self.assertNotIn('room_grant', self.client.session)

    def test_accepted_invitation_does_not_override_a_ban(self):
        # Asserts the gate ordering: the ban check returns before the invitation
        # branch, so the invitation is neither consumed nor able to mint a grant.
        RoomInvitation.objects.create(
            room=self.room, sender=self.owner, receiver=self.other, status='accepted',
        )
        response = self.client.get(self._url(), follow=True)
        self.assertRedirects(response, '/dashboard/')
        self.assertNotContains(response, self.secret_line)
        self.assertNotIn('room_grant', self.client.session)
        self.assertTrue(
            RoomInvitation.objects.filter(room=self.room, receiver=self.other).exists()
        )

    def test_correct_password_does_not_mint_a_grant_for_a_banned_user(self):
        response = self.client.post('/room/join/', {
            'room_code': self.room.room_code, 'password': self.PASSWORD,
        }, follow=True)
        self.assertRedirects(response, '/dashboard/')
        self.assertNotIn('room_grant', self.client.session)

    def test_invitation_to_a_banned_user_is_refused_with_a_reason(self):
        Friendship.objects.create(sender=self.owner, receiver=self.other, status='accepted')
        result = services.create_room_invitation(self.owner, self.room, self.other.id)
        self.assertEqual(result['error'], 'That user was removed from this room.')
        self.assertFalse(RoomInvitation.objects.filter(room=self.room).exists())

    def test_deleting_the_room_cascades_the_ban(self):
        # The room's lifetime is the ban's lifetime — that is why there is no
        # expires_at. A recycled room code lands on a new Room row.
        self.room.delete()
        self.assertFalse(RoomBan.objects.filter(user=self.other).exists())


class RoomViewGateTests(TestCase):
    """room_view is the HTTP gate and the only place a grant is minted."""

    PASSWORD = 'hunter22'

    def setUp(self):
        self.owner = User.objects.create_user('owner', password='x')
        self.other = User.objects.create_user('other', password='x')
        self.room = Room.objects.create(
            name='Secret', owner=self.owner, password=make_password(self.PASSWORD),
        )
        self.open_room = Room.objects.create(name='Open', owner=self.owner)
        # Distinctive enough that finding it in a response body means the
        # history query ran for someone who had not unlocked the room.
        self.secret_line = 'topsecretchatter'
        Message.objects.create(room=self.room, sender=self.owner, content=self.secret_line)
        self.client.force_login(self.other)

    def _url(self, room):
        return f'/room/{room.room_code}/'

    def test_locked_room_without_grant_redirects_and_leaks_no_history(self):
        response = self.client.get(self._url(self.room), follow=True)
        self.assertRedirects(response, '/dashboard/')
        self.assertNotContains(response, self.secret_line)
        self.assertNotIn('room_grant', self.client.session)

    def test_correct_password_mints_grant_and_admits(self):
        response = self.client.post('/room/join/', {
            'room_code': self.room.room_code, 'password': self.PASSWORD,
        })
        self.assertRedirects(response, self._url(self.room))
        self.assertEqual(self.client.session['room_grant'], self.room.room_code)
        self.assertContains(self.client.get(self._url(self.room)), self.secret_line)

    def test_bare_code_with_empty_password_is_rejected(self):
        response = self.client.post('/room/join/', {
            'room_code': self.room.room_code, 'password': '',
        }, follow=True)
        self.assertContains(response, 'Incorrect room password.')
        self.assertNotIn('room_grant', self.client.session)

    def test_accepted_invitation_admits_exactly_once(self):
        RoomInvitation.objects.create(
            room=self.room, sender=self.owner, receiver=self.other, status='accepted',
        )
        self.assertContains(self.client.get(self._url(self.room)), self.secret_line)
        self.assertFalse(
            RoomInvitation.objects.filter(room=self.room, receiver=self.other).exists()
        )

        # Stand in for the socket dropping, which is what revokes the grant.
        session = self.client.session
        del session['room_grant']
        session.save()

        again = self.client.get(self._url(self.room), follow=True)
        self.assertRedirects(again, '/dashboard/')
        self.assertNotContains(again, self.secret_line)

    def test_owner_needs_no_grant(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(self._url(self.room)), self.secret_line)
        self.assertNotIn('room_grant', self.client.session)

    def test_open_room_is_reachable_directly(self):
        self.assertEqual(self.client.get(self._url(self.open_room)).status_code, 200)
