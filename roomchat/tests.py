from unittest.mock import Mock

from django.test import SimpleTestCase
from pydantic import ValidationError

from accounts.schemas import UserCreate
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
