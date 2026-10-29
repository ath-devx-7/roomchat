"""
ASGI config for roomchat project: builds the FastAPI app that the server runs.
"""

import os

from fastapi import FastAPI

from roomchat import settings
from roomchat.errors import exception_handlers
from roomchat.middleware import MIDDLEWARE
from roomchat.urls import include_urls

# Temporary, removed in P4: accounts/views.py still sends friend-request notifications
# through Django Channels' Redis layer, which reads CHANNEL_LAYERS via Django's settings
# (only when the first notification is sent, so setting it here is early enough).
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'roomchat.settings')

application = FastAPI(
    middleware=MIDDLEWARE,  # the 8 layers from P2, outermost first
    exception_handlers=exception_handlers,  # 404/405/500 as {"error": ...}
    debug=settings.DEBUG,  # DEBUG on: crashes show a traceback, like Django did
)
include_urls(application)
