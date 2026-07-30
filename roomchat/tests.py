import asyncio
from unittest.mock import Mock

from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from channels_redis.pubsub import RedisPubSubChannelLayer
from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TransactionTestCase
from pydantic import ValidationError

from accounts.schemas import UserCreate
from rooms.consumers import CLOSE_NOT_AUTHENTICATED
from rooms.models import Room, RoomInvitation
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
    """The WS password gate must mirror room_view: owners and users with an
    accepted invitation bypass the password, everyone else needs the room in
    session['authorized_rooms']."""

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

    async def _assert_rejected(self, communicator):
        connected, _ = await communicator.connect()
        # reject() accepts before closing, so connected is True either way.
        self.assertTrue(connected)
        error = await communicator.receive_json_from()
        self.assertEqual(error['type'], 'error')
        close = await communicator.receive_output()
        self.assertEqual(close['type'], 'websocket.close')
        self.assertEqual(close['code'], CLOSE_NOT_AUTHENTICATED)
        await communicator.disconnect()

    async def _assert_admitted(self, communicator):
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        # First frame after a successful join is a real event, not the error
        # frame that precedes a rejection close.
        first = await communicator.receive_json_from()
        self.assertNotEqual(first['type'], 'error')
        await communicator.disconnect()

    async def test_unauthorized_user_is_rejected(self):
        await self._assert_rejected(self._communicator(self.other))

    async def test_owner_bypasses_password(self):
        await self._assert_admitted(self._communicator(self.owner))

    async def test_accepted_invite_bypasses_password(self):
        await RoomInvitation.objects.acreate(
            room=self.room, sender=self.owner, receiver=self.other,
            status='accepted',
        )
        await self._assert_admitted(self._communicator(self.other))

    async def test_authorized_session_is_admitted(self):
        session = {'authorized_rooms': [self.room.room_code]}
        await self._assert_admitted(self._communicator(self.other, session))
