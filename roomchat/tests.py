from unittest.mock import Mock

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TransactionTestCase
from pydantic import ValidationError

from accounts.schemas import UserCreate
from rooms.consumers import CLOSE_NOT_AUTHENTICATED
from rooms.models import Room, RoomInvitation
from rooms.routing import websocket_urlpatterns
from rooms.schemas import RoomCreate
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
