"""
`static(path)`: the URL of a file in STATICFILES_DIRS, with a content hash attached.

Replaces Django's `static` template tag and its renamed collectstatic files. Instead of
renaming `main.js` to `main.3f9a1c2b4d5e.js`, the hash goes in a query string
(`/static/react/js/main.js?v=3f9a1c2b4d5e`). When the file changes, so does the URL, and
browsers download the new file instead of reusing a cached old one.
"""

import hashlib

from roomchat import settings

# path -> hash. Each file is hashed once per server process (files only change on a
# rebuild, which is followed by a restart or a deploy).
_hashes = {}


def static(path):
    """Return the URL for a static file, e.g. static('react/css/main.css')."""
    url = '/' + settings.STATIC_URL + path
    if path not in _hashes:
        file = settings.STATICFILES_DIRS[0] / path
        if not file.is_file():
            return url  # missing file: plain URL, so the browser gets a clear 404
        # First 12 hex characters of the md5, the same length Django's manifest used.
        _hashes[path] = hashlib.md5(file.read_bytes()).hexdigest()[:12]
    return f'{url}?v={_hashes[path]}'
