"""Centralized JSON error handling for pydantic ValidationErrors on opted-in views."""

from functools import wraps

from django.http import JsonResponse
from pydantic import ValidationError

from .errors import format_pydantic_errors


def json_validation_errors(view_func):
    """Mark a view so PydanticValidationErrorMiddleware converts an uncaught
    pydantic ValidationError raised inside it into a JSON 400 response."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        request._json_validation_errors = True
        return view_func(request, *args, **kwargs)
    return wrapper


class PydanticValidationErrorMiddleware:
    """Converts pydantic ValidationErrors into JSON 400 responses, but only for
    views decorated with @json_validation_errors. Views that already catch
    ValidationError themselves (e.g. the HTML form views) are unaffected."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not isinstance(exception, ValidationError):
            return None
        if not getattr(request, '_json_validation_errors', False):
            return None
        return JsonResponse({'errors': format_pydantic_errors(exception)}, status=400)
