"""
Password hashing and login/logout, ported from django.contrib.auth with the same behaviour.

Hashes keep Django's `pbkdf2_sha256$<iterations>$<salt>$<hash>` format, so passwords (and
room passwords) written by Django still check, and new ones would still work in Django.
"""

import base64
import hashlib
import hmac
import secrets
import string
import unicodedata

from sqlalchemy import select

from accounts.models import User, _now
from roomchat import settings
from roomchat.db import db

# Django 6.0's iteration count for pbkdf2_sha256 (how many times the hash is repeated;
# more = slower to brute-force).
PBKDF2_ITERATIONS = 1_200_000
ALGORITHM = 'pbkdf2_sha256'
UNUSABLE_PASSWORD_PREFIX = '!'

# Session keys that mark who is logged in (same names as Django's).
SESSION_KEY = '_auth_user_id'
HASH_SESSION_KEY = '_auth_user_hash'


def get_random_string(length, allowed_chars=string.ascii_letters + string.digits):
    """Return a cryptographically secure random string (salts, session keys, CSRF tokens)."""
    return ''.join(secrets.choice(allowed_chars) for _ in range(length))


def salted_hmac(key_salt, value):
    """HMAC-SHA256 of `value`, keyed by SECRET_KEY + `key_salt` (port of Django's helper).

    The salt gives every use its own key, so a stamp made for sessions can never be
    passed off as a stamp for something else.
    """
    key = hashlib.sha256((key_salt + settings.SECRET_KEY).encode()).digest()
    return hmac.new(key, value.encode(), hashlib.sha256)


def make_password(password, salt=None, iterations=PBKDF2_ITERATIONS):
    """Hash a plain-text password into Django's pbkdf2_sha256 format."""
    salt = salt or get_random_string(22)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations)
    hash_b64 = base64.b64encode(digest).decode('ascii').strip()
    return f'{ALGORITHM}${iterations}${salt}${hash_b64}'


def check_password(password, encoded, setter=None):
    """Return True if `password` matches the stored hash `encoded`.

    `setter(password)` is called after a correct check when the hash uses an old
    iteration count, so the caller can store a stronger hash (Django does the same).
    """
    if password is None or not encoded or encoded.startswith(UNUSABLE_PASSWORD_PREFIX):
        return False
    try:
        algorithm, iterations, salt, _ = encoded.split('$', 3)
        iterations = int(iterations)
    except ValueError:
        return False
    if algorithm != ALGORITHM:
        return False

    # Re-hash with the same salt and iterations, then compare in constant time
    # (takes the same time wherever the strings differ, so timing leaks nothing).
    is_correct = hmac.compare_digest(
        encoded.encode(), make_password(password, salt, iterations).encode()
    )
    if is_correct and setter and iterations != PBKDF2_ITERATIONS:
        setter(password)
    return is_correct


def get_session_auth_hash(user):
    """Fingerprint of the user's password hash, stored in the session at login.

    If the password changes, the fingerprint no longer matches and old sessions log out.
    """
    return salted_hmac('roomchat.auth.get_session_auth_hash', user.password).hexdigest()


class AnonymousUser:
    """What `request.user` is when nobody is logged in (mirrors Django's AnonymousUser)."""

    id = None
    pk = None
    username = ''
    is_staff = False
    is_superuser = False
    is_active = False
    is_authenticated = False
    is_anonymous = True

    def __str__(self):
        return 'AnonymousUser'

    def __eq__(self, other):
        return isinstance(other, self.__class__)

    def __hash__(self):
        return 1


def normalize_email(email):
    """Lowercase the domain part of an email address, as Django's UserManager does.

    Only the domain is lowercased: the part before the @ can be case-sensitive.
    """
    email = email or ''
    try:
        email_name, domain_part = email.strip().rsplit('@', 1)
    except ValueError:
        return email  # no @ in it: leave it as it is
    return email_name + '@' + domain_part.lower()


def create_user(username, email='', password=None):
    """Create, save and return a new User (port of Django's User.objects.create_user).

    With no password, the user gets an unusable one: it starts with '!', so
    check_password() never accepts anything for it.
    """
    if password is None:
        hashed_password = UNUSABLE_PASSWORD_PREFIX + get_random_string(40)
    else:
        hashed_password = make_password(password)

    user = User(
        # NFKC turns look-alike Unicode characters into one standard form, so two
        # usernames that look identical are stored identically (Django does the same).
        username=unicodedata.normalize('NFKC', username),
        email=normalize_email(email),
        password=hashed_password,
    )
    db.add(user)
    db.commit()  # rule 2: commit right after the write, like Django's autocommit
    return user


def authenticate(request=None, username=None, password=None):
    """Return the User for these credentials, or None. Inactive users are rejected."""
    if username is None or password is None:
        return None

    user = db.scalars(select(User).where(User.username == username)).one_or_none()
    if user is None:
        # Hash anyway, so "no such user" takes as long as "wrong password" and response
        # time can't reveal which usernames exist.
        make_password(password)
        return None

    def upgrade_hash(raw_password):
        """Store a fresh hash with today's iteration count."""
        user.password = make_password(raw_password)
        db.commit()

    if check_password(password, user.password, setter=upgrade_hash) and user.is_active:
        return user
    return None


def login(request, user):
    """Log `user` in on this request's session (same steps as Django's login)."""
    session = request.session
    session_auth_hash = get_session_auth_hash(user)

    if SESSION_KEY in session:
        # The session belongs to someone else (or is stale): start a clean one so no
        # data leaks from the previous user.
        if int(session[SESSION_KEY]) != user.id or not hmac.compare_digest(
            session.get(HASH_SESSION_KEY, '').encode(), session_auth_hash.encode()
        ):
            session.flush()
    else:
        # New key for the same data, so a key planted before login is useless
        # (protects against "session fixation").
        session.cycle_key()

    session[SESSION_KEY] = str(user.id)
    session[HASH_SESSION_KEY] = session_auth_hash
    request.scope['user'] = user  # request.user reads scope['user']

    # Ask CsrfViewMiddleware for a new CSRF token on this response, like Django's rotate_token.
    request.state.csrf_rotate = True

    user.last_login = _now()
    db.commit()


def logout(request):
    """Wipe the session and make the request anonymous."""
    request.session.flush()
    request.scope['user'] = AnonymousUser()


def get_user(session):
    """Return the logged-in User for this session, or AnonymousUser.

    Used by AuthenticationMiddleware. A deleted or deactivated user counts as logged out,
    and a session whose password fingerprint no longer matches is wiped.
    """
    user_id = session.get(SESSION_KEY)
    if user_id is None:
        return AnonymousUser()

    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        return AnonymousUser()

    if not hmac.compare_digest(
        session.get(HASH_SESSION_KEY, '').encode(), get_session_auth_hash(user).encode()
    ):
        session.flush()
        return AnonymousUser()
    return user
