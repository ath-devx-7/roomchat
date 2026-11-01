"""
Admin panel (sqladmin) for accounts: the admin login backend, Users and Friendships.

sqladmin keeps Django admin's ideas under other names: `list_display` -> `column_list`,
`list_filter` -> `column_filters`, and the form fields are listed in `form_columns`.
"""

import hmac

from sqladmin import ModelView
from sqladmin.authentication import AuthenticationBackend
from sqladmin.filters import BooleanFilter, StaticValuesFilter
from starlette.concurrency import run_in_threadpool
from wtforms import SelectField

from roomchat import auth
from roomchat.db import db

from .models import Friendship, User


class AdminAuth(AuthenticationBackend):
    """Login for /admin/: same username + password check as the SPA, but staff only.

    The admin login lives in its own signed cookie (`admin_session`, set by the Starlette
    SessionMiddleware that this backend adds to the admin sub-app only). It never touches
    the SPA's `sessionid`, so logging in on one side doesn't log you in on the other.

    Each method runs inside the request's `db` scope (opened by DBSessionMiddleware), and the
    sync DB calls go through run_in_threadpool so the event loop isn't blocked.
    """

    async def login(self, request):
        """Check the login form. Only active staff users get in."""
        form = await request.form()
        user = await run_in_threadpool(
            auth.authenticate, request,
            username=form.get('username'), password=form.get('password'),
        )
        # auth.authenticate already refuses wrong passwords and inactive users.
        if user is None or not user.is_staff:
            return False

        # request.session here is the admin cookie's dict, not the SPA's SessionStore.
        request.session.update({
            'user_id': user.id,
            # Password fingerprint, like the SPA session: a password change logs the admin out.
            'auth_hash': auth.get_session_auth_hash(user),
        })
        return True

    async def logout(self, request):
        """Forget the admin login (the cookie is deleted on this response)."""
        request.session.clear()
        return True

    async def authenticate(self, request):
        """Runs on every admin page: is the stored user still an active staff member
        with the same password? If not, clear the admin login and send them to /admin/login."""
        user_id = request.session.get('user_id')
        if user_id is None:
            return False

        user = await run_in_threadpool(db.get, User, user_id)
        if (
            user is None
            or not user.is_active
            or not user.is_staff
            # compare_digest = constant-time comparison, so timing can't reveal the hash.
            or not hmac.compare_digest(
                request.session.get('auth_hash', '').encode(),
                auth.get_session_auth_hash(user).encode(),
            )
        ):
            request.session.clear()
            return False
        return True


class UserAdmin(ModelView, model=User):
    """Users, as Django's built-in UserAdmin listed them (django.contrib.auth registered it).

    The password is never in the form, so the admin can't save one as raw text; users are
    created through sign-up instead (`can_create = False`).
    """

    column_list = [User.username, User.email, User.first_name, User.last_name, User.is_staff]
    # Django also filtered by groups; there is no Group model any more.
    column_filters = [BooleanFilter(User.is_staff), BooleanFilter(User.is_superuser), BooleanFilter(User.is_active)]
    column_searchable_list = [User.username, User.first_name, User.last_name, User.email]
    # Own columns only. The password hash is never shown, and reverse relations (friendships,
    # rooms, …) are left out: rendering them after sqladmin's session closes would crash.
    column_details_list = [
        User.id, User.username, User.first_name, User.last_name, User.email, User.is_active,
        User.is_staff, User.is_superuser, User.last_login, User.date_joined,
    ]
    form_columns = [
        User.username, User.first_name, User.last_name, User.email,
        User.is_active, User.is_staff, User.is_superuser, User.last_login, User.date_joined,
    ]
    can_create = False


class FriendshipAdmin(ModelView, model=Friendship):
    """Friend requests and friendships."""

    column_list = [Friendship.sender, Friendship.receiver, Friendship.status, Friendship.created_at]
    column_filters = [StaticValuesFilter(Friendship.status, values=Friendship.STATUS_CHOICES)]
    column_details_list = [
        Friendship.id, Friendship.sender, Friendship.receiver, Friendship.status, Friendship.created_at,
    ]
    form_columns = [Friendship.sender, Friendship.receiver, Friendship.status]
    # A dropdown of the allowed values, as Django showed for a field with choices.
    form_overrides = {'status': SelectField}
    form_args = {'status': {'choices': Friendship.STATUS_CHOICES}}
