"""Shared helpers for turning pydantic ValidationErrors into human-readable messages."""

from pydantic import ValidationError


def format_pydantic_errors(exc: ValidationError) -> dict[str, str]:
    """Map a pydantic ValidationError to a {field_name: message} dict.

    Strips pydantic's "Value error, " prefix from custom validator messages
    and turns "Field required" into a friendlier "<Field> is required." message.
    """
    errors = {}
    for error in exc.errors():
        loc = error['loc'][0]
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
