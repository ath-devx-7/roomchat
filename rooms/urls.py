"""Room JSON endpoints. Mounted under /api/ by roomchat/urls.py."""

from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard_api, name='dashboard_api'),
    path('rooms/create/', views.create_room, name='create_room'),
    path('rooms/join/', views.join_room, name='join_room'),
    path('rooms/<str:room_code>/', views.room_detail_api, name='room_detail_api'),
    path('invitations/', views.get_invitations_api, name='get_invitations_api'),
]
