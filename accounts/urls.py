"""Auth and friends JSON endpoints. Mounted under /api/ by roomchat/urls.py."""

from django.urls import path
from . import views

urlpatterns = [
    path('auth/register/', views.register_api, name='register'),
    path('auth/login/', views.login_api, name='login'),
    path('auth/logout/', views.logout_api, name='logout'),
    path('auth/me/', views.me_api, name='me'),
    path('friends/', views.friends_list_api, name='friends_list_api'),
    path('friends/send/', views.send_friend_request, name='send_friend_request'),
    path('friends/accept/<int:friendship_id>/', views.accept_friend_request, name='accept_friend_request'),
    path('friends/reject/<int:friendship_id>/', views.reject_friend_request, name='reject_friend_request'),
    path('friends/remove/<int:friendship_id>/', views.remove_friend, name='remove_friend'),
]
