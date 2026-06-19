from django.urls import path
from django.shortcuts import redirect
from . import views

urlpatterns = [
    path('', lambda request: redirect('dashboard'), name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('room/create/', views.create_room, name='create_room'),
    path('room/join/', views.join_room, name='join_room'),
    path('room/<str:room_code>/', views.room_view, name='room'),
    path('api/invitations/', views.get_invitations_api, name='get_invitations_api'),
]
