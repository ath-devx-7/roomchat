"""
Command-line tasks for RoomChat. Replaces the one `manage.py` command the project still needs:

    python -m roomchat.cli createsuperuser

It creates a staff user who can log in to the admin at /admin/. The answers go through the
same checks as the register form (accounts/schemas.py UserCreate), except that the email is
optional here.
"""

import argparse
import getpass
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError, field_validator
from sqlalchemy import exists, select

from accounts.models import User
from accounts.schemas import UserCreate
from roomchat.auth import create_user
from roomchat.db import db
from roomchat.errors import format_pydantic_errors
from roomchat.middleware import _in_own_db_scope


class SuperuserCreate(UserCreate):
    """UserCreate with an optional email: blank is allowed, anything else must be valid."""

    email: str = ''

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip()
        if not v:
            return v
        try:
            # The same EmailStr check the register form uses, run on its own.
            return TypeAdapter(EmailStr).validate_python(v)
        except ValidationError:
            raise ValueError('Enter a valid email address.')


def field_errors(answers):
    """Check the answers given so far and return {field: message} for those fields only.

    Fields not asked yet are missing, so pydantic reports them as required; those
    errors are ignored here.
    """
    try:
        SuperuserCreate(**answers)
    except ValidationError as e:
        return {field: msg for field, msg in format_pydantic_errors(e).items() if field in answers}
    return {}


def ask(answers, field, prompt, hidden=False):
    """Ask one question, store the answer, and return its error message (or None)."""
    # getpass is input() that doesn't show what you type, for passwords.
    answers[field] = getpass.getpass(prompt) if hidden else input(prompt)
    return field_errors(answers).get(field)


def createsuperuser():
    """Prompt for a username, email and password, then create an active staff user."""
    answers = {}

    while True:
        error = ask(answers, 'username', 'Username: ')
        if error is None:
            # Same query as register_api: SELECT EXISTS(... WHERE username = ?).
            username = answers['username'].strip()
            if db.scalar(select(exists().where(User.username == username))):
                error = 'A user with that username already exists.'
        if error is None:
            break
        print(f'Error: {error}')

    while True:
        error = ask(answers, 'email', 'Email address (optional): ')
        if error is None:
            break
        print(f'Error: {error}')

    while True:
        ask(answers, 'password', 'Password: ', hidden=True)
        ask(answers, 'confirm_password', 'Password (again): ', hidden=True)
        errors = field_errors(answers)
        # A short password is reported on 'password', a mismatch on 'confirm_password'.
        error = errors.get('password') or errors.get('confirm_password')
        if error is None:
            break
        print(f'Error: {error}')

    details = SuperuserCreate(**answers)  # every field passed above; this gives the cleaned values
    # create_user hashes the password with make_password and commits the new row.
    user = create_user(username=details.username, email=details.email, password=details.password)
    user.is_staff = True  # the admin login (accounts/admin.py) needs is_staff and is_active
    user.is_active = True
    db.commit()  # commit right after the write, like every other write in the app
    print('Superuser created successfully.')


def main(argv=None):
    """Parse the command line and run the chosen command."""
    parser = argparse.ArgumentParser(prog='python -m roomchat.cli')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('createsuperuser', help='create a staff user for /admin/')
    args = parser.parse_args(argv)

    if args.command == 'createsuperuser':
        try:
            # `db` only works inside an opened scope (roomchat/db.py), so open one here.
            _in_own_db_scope(createsuperuser)
        except (KeyboardInterrupt, EOFError):
            # Ctrl+C or Ctrl+D: nothing has been written, because the commit is the last step.
            print('\nCancelled.')
            sys.exit(1)


if __name__ == '__main__':
    main()
