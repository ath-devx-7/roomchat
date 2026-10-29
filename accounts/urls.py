"""Auth and friends JSON endpoints. Mounted under /api/ by roomchat/urls.py."""

from fastapi import APIRouter

from . import views

# Every route accepts GET and POST, so the method checks inside the views
# (require_POST_json's 405, send_friend_request's 400 "Invalid request.") stay the
# ones that answer, as they did under Django.
METHODS = ['GET', 'POST']

urlpatterns = APIRouter()
urlpatterns.add_api_route('/auth/register/', views.register_api, methods=METHODS, name='register')
urlpatterns.add_api_route('/auth/login/', views.login_api, methods=METHODS, name='login')
urlpatterns.add_api_route('/auth/logout/', views.logout_api, methods=METHODS, name='logout')
urlpatterns.add_api_route('/auth/me/', views.me_api, methods=METHODS, name='me')
urlpatterns.add_api_route('/friends/', views.friends_list_api, methods=METHODS, name='friends_list_api')
urlpatterns.add_api_route('/friends/send/', views.send_friend_request, methods=METHODS, name='send_friend_request')
# {friendship_id:int} only matches digits (like Django's <int:...>), so /accept/abc/
# is a plain 404 instead of FastAPI's 422 validation error.
urlpatterns.add_api_route(
    '/friends/accept/{friendship_id:int}/', views.accept_friend_request,
    methods=METHODS, name='accept_friend_request',
)
urlpatterns.add_api_route(
    '/friends/reject/{friendship_id:int}/', views.reject_friend_request,
    methods=METHODS, name='reject_friend_request',
)
urlpatterns.add_api_route(
    '/friends/remove/{friendship_id:int}/', views.remove_friend,
    methods=METHODS, name='remove_friend',
)
