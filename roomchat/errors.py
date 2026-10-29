"""Shared helpers for API views: pydantic error formatting, JSON-safe auth, and the
JSON error handlers that keep every error in the `{"error": ...}` shape."""

from functools import wraps

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError


class JsonResponse(JSONResponse):
    """JSONResponse that accepts Django's `status=` keyword, so existing
    `return JsonResponse({...}, status=400)` lines work unchanged."""

    def __init__(self, data, status=200, **kwargs):
        super().__init__(data, status_code=status, **kwargs)


async def form_data(request: Request):
    """Dependency that returns the parsed form body; replaces Django's `request.POST`.

    Used in views as `form = Depends(form_data)`, then `form.get('username')`.
    """
    return await request.form()


def api_login_required(view_func):
    """@login_required for JSON endpoints.

    django.contrib.auth's version redirects to LOGIN_URL, which hands a fetch() caller a
    302 to an HTML page — the frontend then parses markup as JSON and reports a nonsense
    error. Every /api/ view uses this instead so an expired session is an unambiguous 401
    the SPA can act on by routing to /login.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Not authenticated.'}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


def require_POST_json(view_func):
    """Reject non-POST with a JSON 405 rather than Django's HTML error page."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.method != 'POST':
            return JsonResponse({'error': 'Method not allowed.'}, status=405)
        return view_func(request, *args, **kwargs)
    return wrapper


def format_pydantic_errors(exc: ValidationError) -> dict[str, str]:
    """Map a pydantic ValidationError to a {field_name: message} dict.

    Strips pydantic's "Value error, " prefix from custom validator messages
    and turns "Field required" into a friendlier "<Field> is required." message.
    """
    errors = {}
    for error in exc.errors():
        # Model-level validators (@model_validator) report an empty loc. For a
        # discriminated union the tag comes first ('send_message', 'content'),
        # so the field name is always the last element, never the first.
        loc = error['loc'][-1] if error['loc'] else '__all__'
        msg = error['msg']
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        elif msg.startswith("Field required"):
            msg = f"{str(loc).replace('_', ' ').capitalize()} is required."
        elif "email" in str(loc) and any(
            x in msg for x in ["value is not a valid email address", "single @", "must contain a single @"]
        ):
            msg = "Enter a valid email address."
        errors[str(loc)] = msg
    return errors


# --- Error handlers -------------------------------------------------------------------
# Registered on the app in P3. They replace Django's HTML error pages, so the SPA always
# receives the same `{"error": ...}` shape it already shows to the user.

async def not_found(request, exc):
    """404 for any path no route matches."""
    return JsonResponse({'error': 'Not found.'}, status=404)


async def method_not_allowed(request, exc):
    """405 when a route exists but not for this HTTP method."""
    # Keep the `Allow` header Starlette attaches (lists the methods that are allowed).
    return JsonResponse({'error': 'Method not allowed.'}, status=405, headers=exc.headers)


async def server_error(request, exc):
    """500 for any unhandled exception (with DEBUG on, Starlette shows a traceback instead)."""
    return JsonResponse({'error': 'Server error.'}, status=500)


exception_handlers = {
    404: not_found,
    405: method_not_allowed,
    500: server_error,
}
