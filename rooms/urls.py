"""Room JSON endpoints. Mounted under /api/ by roomchat/urls.py."""

from fastapi import APIRouter

from . import views

# GET and POST on every route, so the views' own method checks keep answering.
METHODS = ['GET', 'POST']

urlpatterns = APIRouter()
urlpatterns.add_api_route('/dashboard/', views.dashboard_api, methods=METHODS, name='dashboard_api')
# create/ and join/ must stay above rooms/{room_code}/: routes are tried in order, and
# {room_code} would otherwise match the words "create" and "join".
urlpatterns.add_api_route('/rooms/create/', views.create_room, methods=METHODS, name='create_room')
urlpatterns.add_api_route('/rooms/join/', views.join_room, methods=METHODS, name='join_room')
urlpatterns.add_api_route('/rooms/{room_code}/', views.room_detail_api, methods=METHODS, name='room_detail_api')
urlpatterns.add_api_route('/invitations/', views.get_invitations_api, methods=METHODS, name='get_invitations_api')
