"""
Pure-ASGI middleware replacing Django's MIDDLEWARE setting, plus the two view decorators
that talk to it (`json_validation_errors`, `ensure_csrf_cookie`).

"Pure ASGI" means each class is just `async __call__(scope, receive, send)`. It can read
the request (`scope`) and edit the response by wrapping `send`. `MIDDLEWARE` at the bottom
lists the layers outermost first; P3 passes it to the app.
"""

import hmac
from functools import wraps
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import HTTPConnection

from roomchat import settings
from roomchat.auth import get_random_string, get_user
from roomchat.db import db, db_scope
from roomchat.sessions import SESSION_COOKIE_AGE, SESSION_COOKIE_NAME, SessionStore

from .errors import JsonResponse, format_pydantic_errors

CSRF_COOKIE_NAME = 'csrftoken'
CSRF_COOKIE_AGE = 60 * 60 * 24 * 7 * 52  # one year, in seconds (Django's default)
CSRF_TOKEN_LENGTH = 32
SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS', 'TRACE')
ADMIN_PATH_PREFIX = '/admin/'  # sqladmin's mount; CsrfViewMiddleware checks it by Origin only

# Same values Django's SecurityMiddleware / XFrameOptionsMiddleware sent.
SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',  # browser must not guess file types
    'X-Frame-Options': 'DENY',  # page can't be embedded in another site's <iframe>
    'Referrer-Policy': 'same-origin',  # full URL only sent to our own pages
    'Cross-Origin-Opener-Policy': 'same-origin',  # other sites' popups can't reach our window
}


# --- small helpers --------------------------------------------------------------------

async def run_db(scope, func):
    """Run a blocking DB function on a worker thread, so the event loop isn't frozen.

    HTTP reuses the request's `db` opened by DBSessionMiddleware. A WebSocket gets its own
    short scope that closes straight away, so no connection is held while the socket is open.
    """
    if scope['type'] == 'websocket':
        return await run_in_threadpool(_in_own_db_scope, func)
    return await run_in_threadpool(func)


def _in_own_db_scope(func):
    """Call `func` inside a fresh `db` scope and close it afterwards."""
    token = db_scope.set(object())
    try:
        return func()
    finally:
        db.remove()
        db_scope.reset(token)


def cookie_header(name, value, max_age, http_only, secure):
    """Build one Set-Cookie header value (path=/, SameSite=Lax, as Django did)."""
    cookie = SimpleCookie()
    cookie[name] = value
    cookie[name]['path'] = '/'
    cookie[name]['max-age'] = max_age
    cookie[name]['expires'] = max_age  # SimpleCookie turns seconds-from-now into a date
    cookie[name]['samesite'] = 'Lax'
    if http_only:
        cookie[name]['httponly'] = True  # JavaScript can't read it
    if secure:
        cookie[name]['secure'] = True  # only sent over HTTPS
    return cookie.output(header='').strip()


def trusted_hosts():
    """ALLOWED_HOSTS translated to Starlette's TrustedHostMiddleware patterns.

    Like Django: with DEBUG on and ALLOWED_HOSTS empty, localhost is allowed. A Django-style
    '.example.com' (the domain plus all subdomains) becomes 'example.com' + '*.example.com'.
    """
    hosts = settings.ALLOWED_HOSTS
    if settings.DEBUG and not hosts:
        hosts = ['.localhost', '127.0.0.1', '[::1]']
    patterns = []
    for host in hosts:
        if host.startswith('.'):
            patterns += [host[1:], '*' + host]
        else:
            patterns.append(host)
    return patterns


def _is_same_domain(host, pattern):
    """Django's rule: '.example.com' matches example.com and any subdomain; otherwise exact."""
    pattern = pattern.lower()
    host = host.lower()
    if pattern.startswith('.'):
        return host.endswith(pattern) or host == pattern[1:]
    return host == pattern


def _origin_ok(origin, scheme, host):
    """True if the Origin header is our own site or listed in CSRF_TRUSTED_ORIGINS."""
    if origin == f'{scheme}://{host}' or origin in settings.CSRF_TRUSTED_ORIGINS:
        return True
    # Wildcard entries like 'https://*.example.com' allow any subdomain on that scheme.
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    for trusted in settings.CSRF_TRUSTED_ORIGINS:
        if '*' in trusted:
            trusted = urlsplit(trusted)
            if parsed.scheme == trusted.scheme and _is_same_domain(
                parsed.netloc, trusted.netloc.lstrip('*')
            ):
                return True
    return False


def _referer_ok(referer, host):
    """HTTPS requests without an Origin header must come from an https page on our site
    (or on a trusted origin), as Django checked."""
    if not referer:
        return False
    try:
        parsed = urlsplit(referer)
    except ValueError:
        return False
    if parsed.scheme != 'https' or not parsed.netloc:
        return False
    trusted = [urlsplit(o).netloc.lstrip('*') for o in settings.CSRF_TRUSTED_ORIGINS]
    return any(_is_same_domain(parsed.netloc, h) for h in [host, *trusted])


def _valid_csrf_token(token):
    """A token we issued: 32 letters/digits. Anything else is treated as no cookie."""
    return len(token) == CSRF_TOKEN_LENGTH and token.isascii() and token.isalnum()


# --- 1. TrustedHostMiddleware is Starlette's own (configured in MIDDLEWARE below) ---------

# --- 2. Security headers --------------------------------------------------------------

class SecurityHeadersMiddleware:
    """Adds SECURITY_HEADERS to every HTTP response, unless the response already set one."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)


# --- 3. GZipMiddleware is Starlette's own --------------------------------------------------

# --- 4. DB-session scope --------------------------------------------------------------

class DBSessionMiddleware:
    """Opens one `db` session per HTTP request and closes it when the request ends (rule 1).

    WebSockets are skipped: consumers open a scope per database_sync_to_async call, and the
    handshake loads use run_db()'s short scope.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        # A new unique value = a new key in the scoped_session registry = a new `db`.
        token = db_scope.set(object())
        try:
            await self.app(scope, receive, send)
        finally:
            await run_in_threadpool(db.remove)  # rolls back anything uncommitted, frees the connection
            db_scope.reset(token)


# --- 5. Sessions ----------------------------------------------------------------------

class SessionMiddleware:
    """Loads `scope['session']` from the `sessionid` cookie (so `request.session` works).

    HTTP: when the response starts, saves the session if it changed and sets the cookie, or
    deletes the cookie if the session was emptied (logout). WebSocket: load only.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)

        session_key = HTTPConnection(scope).cookies.get(SESSION_COOKIE_NAME)
        session = await run_db(scope, lambda: SessionStore(session_key))
        scope['session'] = session

        if scope['type'] == 'websocket':
            return await self.app(scope, receive, send)

        async def send_with_session(message):
            if message['type'] == 'http.response.start':
                await self.update_cookie(scope, message, session, had_cookie=session_key is not None)
            await send(message)

        await self.app(scope, receive, send_with_session)

    async def update_cookie(self, scope, message, session, had_cookie):
        """Same decisions as Django's SessionMiddleware.process_response."""
        headers = MutableHeaders(scope=message)
        if had_cookie and session.is_empty():
            # Session was flushed (logout): tell the browser to drop the cookie.
            headers.append('Set-Cookie', cookie_header(
                SESSION_COOKIE_NAME, '', 0, http_only=True, secure=settings.SESSION_COOKIE_SECURE,
            ))
            headers.add_vary_header('Cookie')
            return

        if session.accessed:
            # The response depends on who is asking, so shared caches must not reuse it.
            headers.add_vary_header('Cookie')
        # Skip saving on a 5xx: the request crashed, so its changes may be half-done.
        if session.modified and not session.is_empty() and message['status'] < 500:
            await run_db(scope, session.save)
            headers.append('Set-Cookie', cookie_header(
                SESSION_COOKIE_NAME, session.session_key, SESSION_COOKIE_AGE,
                http_only=True, secure=settings.SESSION_COOKIE_SECURE,
            ))


# --- 6. Authentication ----------------------------------------------------------------

class AuthenticationMiddleware:
    """Sets `scope['user']` (so `request.user` works) to the logged-in User or AnonymousUser."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] in ('http', 'websocket'):
            session = scope['session']
            scope['user'] = await run_db(scope, lambda: get_user(session))
        await self.app(scope, receive, send)


# --- 7. CSRF --------------------------------------------------------------------------

class CsrfViewMiddleware:
    """Blocks cross-site form/fetch posts (CSRF = another site making your browser send a
    request with your cookies).

    For unsafe methods (POST etc.):
      1. if an Origin header is sent, it must be our site or a CSRF_TRUSTED_ORIGINS entry;
         over HTTPS without Origin, the Referer must match instead;
      2. the X-CSRFToken header must equal the csrftoken cookie.
    Under /admin/ (sqladmin) only step 1 runs, and the Origin (or https Referer) is required.
    Failures get JSON 403 `{"error": "CSRF verification failed."}`.

    On the response it sets the csrftoken cookie when a view asked for it
    (@ensure_csrf_cookie) or when login() asked for a new token.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        # Views flag what they need on request.state, which Starlette keeps in scope['state'].
        state = scope.setdefault('state', {})
        cookie_token = HTTPConnection(scope).cookies.get(CSRF_COOKIE_NAME, '')
        if not _valid_csrf_token(cookie_token):
            cookie_token = ''

        if scope['method'] not in SAFE_METHODS and not self.request_ok(scope, cookie_token):
            response = JsonResponse({'error': 'CSRF verification failed.'}, status=403)
            return await response(scope, receive, send)

        async def send_with_token(message):
            if message['type'] == 'http.response.start':
                token = None
                if state.get('csrf_rotate'):
                    token = get_random_string(CSRF_TOKEN_LENGTH)
                elif state.get('csrf_cookie_needed'):
                    token = cookie_token or get_random_string(CSRF_TOKEN_LENGTH)
                if token:
                    headers = MutableHeaders(scope=message)
                    # Not HttpOnly: the SPA's JavaScript reads it to fill X-CSRFToken.
                    headers.append('Set-Cookie', cookie_header(
                        CSRF_COOKIE_NAME, token, CSRF_COOKIE_AGE,
                        http_only=False, secure=settings.CSRF_COOKIE_SECURE,
                    ))
                    headers.add_vary_header('Cookie')
            await send(message)

        await self.app(scope, receive, send_with_token)

    def request_ok(self, scope, cookie_token):
        """Run the Origin/Referer and token checks for one unsafe request."""
        headers = Headers(scope=scope)
        host = headers.get('host', '')
        origin = headers.get('origin')

        if scope['path'].startswith(ADMIN_PATH_PREFIX):
            # sqladmin's plain HTML forms (and its jQuery DELETE) can't send X-CSRFToken, so
            # the admin is protected by its origin instead: browsers always send Origin on
            # these requests and another site can't fake it. Unlike below, a missing Origin
            # is refused (over https a matching Referer may stand in).
            if origin is not None:
                return _origin_ok(origin, scope['scheme'], host)
            return scope['scheme'] == 'https' and _referer_ok(headers.get('referer'), host)

        if origin is not None:
            if not _origin_ok(origin, scope['scheme'], host):
                return False
        elif scope['scheme'] == 'https':
            if not _referer_ok(headers.get('referer'), host):
                return False

        header_token = headers.get('x-csrftoken', '')
        # compare_digest = constant-time comparison, so timing can't reveal the token.
        return bool(cookie_token) and hmac.compare_digest(header_token.encode(), cookie_token.encode())


def ensure_csrf_cookie(view_func):
    """Make the response to this view carry the csrftoken cookie.

    The SPA shell uses it so the first POST after a cold load has a token to send back.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        request.state.csrf_cookie_needed = True
        return view_func(request, *args, **kwargs)
    return wrapper


# --- 8. Pydantic validation errors ----------------------------------------------------

def json_validation_errors(view_func):
    """Mark a view so PydanticValidationErrorMiddleware converts an uncaught
    pydantic ValidationError raised inside it into a JSON 400 response."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        request.state._json_validation_errors = True
        return view_func(request, *args, **kwargs)
    return wrapper


class PydanticValidationErrorMiddleware:
    """Converts pydantic ValidationErrors into JSON 400 responses, but only for
    views decorated with @json_validation_errors. Views that already catch
    ValidationError themselves (e.g. the HTML form views) are unaffected."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        state = scope.setdefault('state', {})
        try:
            await self.app(scope, receive, send)
        except ValidationError as exception:
            if not state.get('_json_validation_errors'):
                raise
            response = JsonResponse({'errors': format_pydantic_errors(exception)}, status=400)
            await response(scope, receive, send)


# --- The order (same as Django's MIDDLEWARE; first = outermost) -----------------------

MIDDLEWARE = [
    # 1. Reject requests whose Host header isn't in ALLOWED_HOSTS (400). No www-redirect,
    #    which Django never did.
    Middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts(), www_redirect=False),
    Middleware(SecurityHeadersMiddleware),  # 2.
    Middleware(GZipMiddleware),  # 3. compresses responses bigger than 500 bytes
    Middleware(DBSessionMiddleware),  # 4.
    Middleware(SessionMiddleware),  # 5.
    Middleware(AuthenticationMiddleware),  # 6.
    Middleware(CsrfViewMiddleware),  # 7.
    Middleware(PydanticValidationErrorMiddleware),  # 8.
]
