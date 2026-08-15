"""
URL configuration for roomchat project.

Everything the SPA calls lives under /api/. Every other path falls through to the
catch-all, which serves the React shell so client-side routes (/, /login, /dashboard,
/room/<code>) survive a hard refresh or a pasted link.
"""

from django.contrib import admin
from django.urls import path, re_path, include

from rooms.views import spa

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('accounts.urls')),
    path('api/', include('rooms.urls')),

    # Must stay last. 'static' and 'media' are excluded defensively — WhiteNoise
    # middleware already answers /static/ before URL resolution runs, but in DEBUG
    # a missing asset would otherwise be served the HTML shell with a 200 instead of
    # a 404, which is a genuinely confusing thing to debug.
    re_path(r'^(?!static/|media/|api/|admin/|ws/).*$', spa, name='spa'),
]
