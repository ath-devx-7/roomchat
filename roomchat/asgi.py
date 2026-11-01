"""
ASGI config for roomchat project: builds the FastAPI app that the server runs.
"""

from fastapi import FastAPI

from roomchat import settings
from roomchat.errors import exception_handlers
from roomchat.middleware import MIDDLEWARE
from roomchat.urls import include_urls

application = FastAPI(
    middleware=MIDDLEWARE,  # the 8 layers from P2, outermost first
    exception_handlers=exception_handlers,  # 404/405/500 as {"error": ...}
    debug=settings.DEBUG,  # DEBUG on: crashes show a traceback, like Django did
)
include_urls(application)
