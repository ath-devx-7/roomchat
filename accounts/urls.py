from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('friends/', views.friends_list_api, name='friends_list_api'),
    path('friends/send/', views.send_friend_request, name='send_friend_request'),
    path('friends/accept/<int:friendship_id>/', views.accept_friend_request, name='accept_friend_request'),
    path('friends/reject/<int:friendship_id>/', views.reject_friend_request, name='reject_friend_request'),
    path('friends/remove/<int:friendship_id>/', views.remove_friend, name='remove_friend'),
]
