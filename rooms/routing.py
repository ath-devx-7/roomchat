from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/chat/<str:room_code>/', consumers.ChatConsumer.as_asgi()),
    path('ws/notifications/', consumers.NotificationConsumer.as_asgi()),
]
