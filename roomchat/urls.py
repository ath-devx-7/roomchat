"""
URL configuration for roomchat project.

Everything the SPA calls lives under /api/. Every other path falls through to the
catch-all, which serves the React shell so client-side routes (/, /login, /dashboard,
/room/<code>) survive a hard refresh or a pasted link.
"""

from starlette.convertors import Convertor, register_url_convertor
from starlette.staticfiles import StaticFiles

from accounts.urls import urlpatterns as accounts_urls
from roomchat import settings
from rooms.routing import websocket_urlpatterns
from rooms.urls import urlpatterns as rooms_urls
from rooms.views import spa


class SpaPathConvertor(Convertor):
    """URL converter for the catch-all: matches any path except the reserved prefixes.

    Same regex the Django re_path used. `(?!...)` is a negative lookahead: "match, but
    only if the path does NOT start with one of these".
    """

    regex = r'(?!static/|media/|api/|admin/|ws/).*'

    def convert(self, value):
        """URL text -> view argument (unchanged)."""
        return value

    def to_string(self, value):
        """View argument -> URL text (unchanged)."""
        return value


# Makes `{path:spa}` usable in route paths, like Starlette's built-in `{x:int}`.
register_url_convertor('spa', SpaPathConvertor())


def include_urls(app):
    """Attach every route to the app, in order. Routes are tried top to bottom."""
    app.include_router(accounts_urls, prefix='/api')
    app.include_router(rooms_urls, prefix='/api')
    app.mount('/' + settings.STATIC_URL.rstrip('/'), StaticFiles(directory=settings.STATICFILES_DIRS[0]), name='static')
    # WebSocket routes (/ws/chat/<code>/, /ws/notifications/). They only match WebSocket
    # connections, and the catch-all below only matches HTTP, so either order would work;
    # they sit here so the catch-all stays visibly last.
    app.router.routes.extend(websocket_urlpatterns)

    # Must stay last: it matches almost every path, so any route added after it would
    # never be reached. The prefixes are excluded so a missing /api/ or /static/ URL
    # gets a JSON 404 instead of the HTML shell with a 200 (a confusing thing to debug),
    # and so the trailing-slash redirect (/api/auth/me -> /api/auth/me/) still fires:
    # Starlette only redirects when no route matches.
    app.add_api_route('/{path:spa}', spa, methods=['GET', 'HEAD'], name='spa')
