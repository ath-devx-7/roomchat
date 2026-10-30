from starlette.routing import WebSocketRoute

from roomchat.realtime import AllowedHostsOriginValidator
from . import consumers

# Each route is wrapped in the origin check, so a page on another site can't open these
# sockets with the visitor's cookies.
websocket_urlpatterns = [
    WebSocketRoute('/ws/chat/{room_code}/', AllowedHostsOriginValidator(consumers.ChatConsumer.as_asgi())),
    WebSocketRoute('/ws/notifications/', AllowedHostsOriginValidator(consumers.NotificationConsumer.as_asgi())),
]
