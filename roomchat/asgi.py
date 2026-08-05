"""
ASGI config for roomchat project.
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'roomchat.settings')

django_asgi_app = get_asgi_application()

from rooms.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    # The handshake carries the session cookie and there is no CSRF check on WebSockets,
    # so the Origin allowlist is the only thing stopping another site from opening an
    # authenticated socket and driving moderation commands.
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
