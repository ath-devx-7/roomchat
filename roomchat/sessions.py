"""
Server-side sessions stored in the existing django_session table (replaces
django.contrib.sessions).

The browser only holds a random key in the `sessionid` cookie. The data itself lives in
the DB as `base64(json):signature`, where the signature is an HMAC made from SECRET_KEY,
so a row edited by hand is detected and ignored.
"""

import base64
import hmac
import json
import string
from datetime import timedelta

from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert

from accounts.models import _now, django_session
from roomchat.auth import get_random_string, salted_hmac
from roomchat.db import db

SESSION_COOKIE_NAME = 'sessionid'
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7 * 2  # two weeks, in seconds (Django's default)
SESSION_KEY_CHARS = string.ascii_lowercase + string.digits


def _sign(payload):
    """HMAC signature of the encoded session payload."""
    return salted_hmac('roomchat.sessions', payload).hexdigest()


def encode(data):
    """Turn the session dict into the `base64(json):signature` string stored in the DB."""
    payload = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    return f'{payload}:{_sign(payload)}'


def decode(session_data):
    """Reverse of encode(). Returns {} if the signature is wrong or the data is unreadable.

    Rows written by Django use a different format and so load as empty sessions.
    That's the one-time logout at cutover the migration plan expects.
    """
    payload, _, signature = session_data.rpartition(':')
    if not hmac.compare_digest(signature.encode(), _sign(payload).encode()):
        return {}
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except ValueError:
        return {}


class SessionStore:
    """One browser's session: dict-style access backed by a django_session row.

    Offers the parts of Django's SessionStore the app uses: `session['x']`, `.get()`,
    `.pop()`, `in`, `del`, plus `.session_key`, `.save()`, `.cycle_key()` and `.flush()`.
    The row is loaded as soon as the object is created.
    """

    def __init__(self, session_key=None):
        self.session_key = session_key
        self.modified = False  # data changed -> SessionMiddleware saves it
        self.accessed = False  # data read or changed -> response gets "Vary: Cookie"
        self._data = self._load()

    def _load(self):
        """Read and decode this key's row if it exists and hasn't expired."""
        if self.session_key is None:
            return {}
        row = db.execute(
            select(django_session.c.session_data).where(
                django_session.c.session_key == self.session_key,
                django_session.c.expire_date > _now(),
            )
        ).first()
        if row is None:
            # Unknown or expired key: drop it so save() makes a fresh one instead of
            # reusing a key the browser invented.
            self.session_key = None
            return {}
        return decode(row.session_data)

    # --- dict-style access -------------------------------------------------------

    def __getitem__(self, key):
        self.accessed = True
        return self._data[key]

    def __setitem__(self, key, value):
        self.accessed = self.modified = True
        self._data[key] = value

    def __delitem__(self, key):
        self.accessed = self.modified = True
        del self._data[key]

    def __contains__(self, key):
        self.accessed = True
        return key in self._data

    def get(self, key, default=None):
        """Like dict.get()."""
        self.accessed = True
        return self._data.get(key, default)

    def pop(self, key, default=None):
        """Like dict.pop(), but returns `default` instead of raising if the key is missing."""
        self.accessed = True
        if key in self._data:
            self.modified = True
        return self._data.pop(key, default)

    def clear(self):
        """Remove all data (the row stays until save() or delete())."""
        self.accessed = self.modified = True
        self._data = {}

    def is_empty(self):
        """True when there is neither a key nor any data (nothing worth a cookie)."""
        return not self.session_key and not self._data

    # --- storage -----------------------------------------------------------------

    def _new_key(self):
        """Pick a random 32-character key that no row uses yet."""
        while True:
            key = get_random_string(32, SESSION_KEY_CHARS)
            taken = db.scalar(select(exists().where(django_session.c.session_key == key)))
            if not taken:
                return key

    def save(self):
        """Write the data to the DB (creating a key first if needed) and restart the 2-week expiry."""
        if self.session_key is None:
            self.session_key = self._new_key()
        values = {
            'session_data': encode(self._data),
            'expire_date': _now() + timedelta(seconds=SESSION_COOKIE_AGE),
        }
        # "Upsert": insert the row, or update it if this key already exists.
        stmt = insert(django_session).values(session_key=self.session_key, **values)
        db.execute(stmt.on_conflict_do_update(index_elements=['session_key'], set_=values))
        db.commit()

    def delete(self, session_key=None):
        """Delete a session row (this session's own row by default)."""
        session_key = session_key or self.session_key
        if session_key is None:
            return
        db.execute(delete(django_session).where(django_session.c.session_key == session_key))
        db.commit()

    def cycle_key(self):
        """Keep the data but move it to a new key, deleting the old row (used at login)."""
        old_key = self.session_key
        self.session_key = self._new_key()
        self.modified = True
        self.save()
        if old_key:
            self.delete(old_key)

    def flush(self):
        """Empty the session and delete its row (used at logout)."""
        self.clear()
        self.delete()
        self.session_key = None
