# Phase 3: HTTP controllers, SPA shell

**Branch:** `migration` (on top of `d7d6561`, with P2's report edit still uncommitted). **Status:** implemented and verified, **not committed** (your call). Scope is P3 only. WebSockets (P4), admin (P5) and tests (P6) are untouched.

**What this phase is about.** Up to P2 nothing could answer a request yet. P3 builds the actual web app and moves every HTTP endpoint onto it:

- **The app** (`roomchat/asgi.py`): a FastAPI object wrapped in P2's 8 middleware layers and its JSON error handlers.
- **Routing** (`*/urls.py`): which URL goes to which **view** (the function that answers a request). Same URLs, same trailing slashes.
- **Views** (`accounts/views.py`, `rooms/views.py`), **services** and the `RoomJoin` schema: the Django ORM queries are rewritten for SQLAlchemy, and `request.POST` becomes `form`.
- **The SPA shell** (`templates/index.html`): the one HTML page that loads the React app, now rendered by **Jinja** (a template engine: HTML with `{{ placeholders }}` filled in by Python).

## Files

| File | Change |
|---|---|
| `roomchat/asgi.py` | **Rewritten.** Builds `application = FastAPI(middleware=MIDDLEWARE, exception_handlers=exception_handlers, debug=settings.DEBUG)`, then calls `include_urls(application)`. Keeps `os.environ.setdefault('DJANGO_SETTINGS_MODULE', ...)` as a temporary bridge (D5). Channels' WebSocket stack is gone until P4. |
| `roomchat/urls.py` | **Rewritten.** `SpaPathConvertor`: a **URL converter** (a named pattern a piece of the URL must match, like Django's `<int:id>`) holding the same regex as before, `(?!static/\|media/\|api/\|admin/\|ws/).*`, registered as `spa`. `include_urls(app)` attaches, in order: the accounts routes and the rooms routes (both under `/api`), `StaticFiles` at `/static`, and finally the catch-all `/{path:spa}` (GET + HEAD). Comments explain why the catch-all must be last and why it skips those prefixes. |
| `accounts/urls.py`, `rooms/urls.py` | **Rewritten.** `urlpatterns` is now an `APIRouter` (FastAPI's list of routes), with one `add_api_route` per old `path()`: same paths, same `name=`, methods GET + POST. `<int:friendship_id>` becomes `{friendship_id:int}`. The comment explaining why `rooms/create/` and `rooms/join/` must come before `rooms/{room_code}/` is kept. |
| `accounts/views.py` | Imports swapped. `def` lines gain type hints (`request: Request`, `form=Depends(form_data)` on the 3 views that read the form, `friendship_id: int`). `request.POST.get` becomes `form.get`. ORM queries are translated per rule 3, with `db.commit()` after each write (rule 2). `User.objects.create_user` becomes `create_user`. The Channels imports are kept for P4. |
| `rooms/views.py` | Same treatment for its 5 API views. `create_room` and `join_room` get `form`. `spa` now renders through `templates.TemplateResponse` (a module-level `Jinja2Templates` with `static` added as a template global) and takes `ensure_csrf_cookie` from `roomchat.middleware` and `static` from `roomchat.staticfiles`. Its signature is now `spa(request: Request)`. |
| `rooms/services.py` | Queries translated with signatures unchanged. `make_password`/`check_password` come from `roomchat.auth`. `get_pending_invitations` returns a list (`.all()`). Short docstrings added. |
| `rooms/schemas.py` | `check_password` comes from `roomchat.auth`. `validate_room_access`: `Room.objects.get` becomes `one_or_none()` plus an `is None` check with the same message. Docstring added. |
| `roomchat/auth.py` | **Added** `create_user(username, email='', password=None)` and `normalize_email(email)`. Port of Django's `create_user`: the username is **NFKC-normalized** (Unicode look-alike characters are turned into one standard form), the email's domain is lowercased, and no password means an unusable `!…` hash. Then it saves and commits. `make_password` is unchanged. |
| `roomchat/staticfiles.py` | **New.** `static(path)` returns `/static/<path>?v=<12-char md5 of the file>`. Each file is hashed once per process. A missing file gets its URL without `?v=`. |
| `templates/index.html` | `{% load static %}` removed. `{% static 'x' %}` becomes `{{ static('x') }}`. `json_script` becomes `<script id="roomchat-bootstrap" type="application/json">{{ bootstrap\|tojson }}</script>`. The two comments that named Django mechanics are reworded. |
| `reports/phase-3.md` | **New.** This report. |

### Query translations used (rule 3)

| Django | SQLAlchemy (as written in P3) |
|---|---|
| `X.objects.filter(a=x).exists()` | `db.scalar(select(exists().where(X.a == x)))` |
| `X.objects.get(...)` + `except DoesNotExist` | `db.scalars(select(X).where(...)).one_or_none()` + `if ... is None:` |
| `Q(...) \| Q(...)` | `or_(and_(...), and_(...))` |
| `.filter(...).select_related('a')` | `select(X).where(...).options(joinedload(X.a))`; `'reply_to__sender'` becomes a chained `joinedload` |
| `.order_by('created_at')[:100]` | `.order_by(Message.created_at).limit(100)` |
| `.create(...)` / `.save()` / `.delete()` | construct + `db.add` + `db.commit()` / `db.commit()` / `db.delete` + `db.commit()` |
| `sender=request.user` | `Friendship.sender == request.user` (compares the foreign key) |

## Decisions

**Decided by you**

1. **Debug flag:** `debug=settings.DEBUG`. With DEBUG on, a crash shows a **traceback** (the chain of function calls that led to the error), like Django. With DEBUG off it returns JSON `{"error": "Server error."}`.
2. **Type hints on the `def` lines.** FastAPI decides what to pass a view by reading its hints. Without them it returned a 422 `{"detail": ...}`, a third error shape (I tested this). `spa(request, *args, **kwargs)` became `spa(request: Request)`; Django never filled those extra arguments.
3. **`create_user`:** full port of Django's version, in `roomchat/auth.py`.
4. **`/admin`:** nothing mounted in P3. I found that sqladmin can't even be imported: it needs `greenlet`, which P1 never added. P5 adds greenlet, sqladmin, the admin login and the CSRF exemption together.
5. **Channels bridge:** `asgi.py` keeps the `DJANGO_SETTINGS_MODULE` line so `notify_friend_request` keeps working until P4. Without it, sending a friend request saved the row and then crashed with a 500.
6. **FastAPI's `/docs`, `/redoc` and `/openapi.json` are kept.**
7. **Catch-all** written as a custom URL converter with the plan's exact regex. You first chose "plain catch-all + check inside spa", then switched once it turned out that would silently disable the trailing-slash redirect.
8. **Catch-all edge:** keep the plan's regex (see Behaviour differences).
9. **HEAD:** the spa route answers GET + HEAD; API routes are GET + POST, as the plan says.
10. **Slash redirect:** Starlette's built-in 307.
11. **Comments:** only those made false by P3 are reworded. The rest wait for P8.
12. **Route order** lives in `include_urls(app)` in `roomchat/urls.py`.

**Decided by me** (delegated to me, or small choices written into the plan you approved)

- **Static hash** (you said "Let Claude decide"): hashed once per process. In production every deploy restarts the server, which matches Django computing its manifest once per deploy. Locally, restart daphne after `yarn build`. The hash is the first 12 hex characters of the md5, the same length Django used.
- `urlpatterns` keeps its old name (now an `APIRouter`). Each urls file has a `METHODS = ['GET', 'POST']` constant, so the reason is written once.
- Multi-row queries end in `.all()`, so they return a list that can be looped over more than once, like a Django queryset.
- The Jinja `templates` object lives in `rooms/views.py`, its only user.
- `create_user` builds the unusable password itself (`'!' + get_random_string(40)`, as Django does), so `make_password` stays unchanged.
- `asgi.py` sets the env var *after* its imports. Django's settings are read lazily (only when the first notification is sent), so that is early enough and needs no `# noqa` import hacks.

## Verification

Everything ran on a scratch DB, `roomchat_p3_smoke`, built with `alembic upgrade head` and dropped afterwards. The dev DB `roomchat` was never connected to.

**Method:** the app was **served by daphne** (`daphne -b 127.0.0.1 -p 8765 roomchat.asgi:application`, `DEBUG=True`). A stdlib-only script (`http.client`, no extra packages) drove it the way `frontend/src/lib/api.js` does:
- form-urlencoded POSTs;
- `X-CSRFToken` copied from the `csrftoken` cookie;
- a same-site `Origin` header;
- cookies kept between requests.

**Result: 104/104 checks passed.** The script was then run again on a freshly rebuilt DB, after I fixed one check that had an operator-precedence slip; still 104/104. The daphne log has no errors.

| Area | What was checked | Result |
|---|---|---|
| SPA shell | GET `/` → 200 HTML, sets `csrftoken`, 4 security headers. Bootstrap JSON parses with `user: null`. `heroImage`, CSS and JS URLs carry `?v=` equal to the file's md5. No Django tags left. HEAD `/` → 200 with an empty body. `/dashboard`, `/login`, `/room/ABC123` serve the shell (hard refresh) | Pass |
| Escaping | Template rendered with a hostile `"</script><script>alert(1)</script>&'"` username: the block contains `</script>`, `&` and `'`, has no raw `<`, and JSON-decodes back to the original string | Pass |
| Static | The 3 assets → 200 with correct content types and bytes. `main.js` gzipped when asked for. A repeat request with the **ETag** (a fingerprint the server sends with a file, so the browser can ask "still the same?") → 304 Not Modified. `/static/nope.css` → JSON 404 | Pass |
| Catch-all exclusions | `/api/nope/`, `/media/x`, HTTP GET `/ws/notifications/` and `/api/friends/accept/abc/` → JSON 404. `/admin/` → 307 to `/admin`, which serves the shell (documented below). `/docs`, `/redoc`, `/openapi.json` → 200 | Pass |
| Slash redirect | GET `/api/auth/me` and POST `/api/auth/login` → 307 to the slashed URL | Pass |
| 405 / 401 / CSRF | PUT → JSON 405 with an `Allow` header. GET `/api/auth/login/` and `/api/rooms/create/` → `require_POST_json`'s 405. HEAD on an API route → 405. Anonymous `/api/auth/me/` → JSON 401. POST without `X-CSRFToken` → JSON 403 | Pass |
| Auth | Register: per-field `{"errors"}`; duplicate username → `errors.username`; success → user payload, `sessionid` set, CSRF token rotated, email domain lowercased, stored hash `pbkdf2_sha256$1200000$…`; "Already signed in." for register and login. Bootstrap shows the user after login. Logout drops `sessionid`, and `me` then gives 401. Bad login → `{"error"}`; empty login → `{"errors"}` | Pass |
| Friends | GET on send → 400 "Invalid request.". Empty, self and unknown sends are refused. A valid send succeeds **and a Redis subscriber received the publish** (Channels bridge works). Duplicate → 400. Friends lists for both sides. The sender can't accept their own request (404). Accept, "already friends", reject (row deleted, repeat → 404), remove (repeat → 404) | Pass |
| Rooms | Blank name → `errors.name`. Protected room created (capacity, hashed password, owner saved). Owner detail → 200 without the password. Non-owner without a grant → "protected" 403. Unknown code → 404. Join: wrong password, unknown code and short code each give their error; the right password works (code upper-cased, password stripped). Detail after the grant → 200. History is ordered, with the `reply_to` preview in the same 3-key shape the socket uses. "Room is full." at capacity. Dashboard shows `current_room_code` and the friend's presence. An accepted invitation admits once and is consumed; a new session then gets 403. A ban beats both the grant and the password (403 on detail and join). The invitations API and dashboard list a pending invite | Pass |
| Services for P4 | Called directly inside a `db` scope: `create_room_invitation` (non-friend, unknown user, banned friend, success, duplicate), `accept_room_invitation` (wrong user → None, success → code), `reject_room_invitation` (unknown → False, success → `declined`). `get_pending_invitations` returns a list | Pass |
| Connections | After the run, no Postgres connection is left "idle in transaction" | Pass |
| Debug flag | `application.debug` is True with `DEBUG=True` and False with `DEBUG=False` | Pass |

**Manual browser checklist (for you).** Covers the P3 surface only. WebSockets are P4, so live toasts, chat and presence won't work yet: refresh the page to see changes.

Start with `daphne roomchat.asgi:application` (dev DB, `.env` as usual), then open `http://localhost:8000`.

1. The landing page renders with styles, fonts and the hero image. In DevTools → Network, `main.css`, `main.js` and `hero.jpg` URLs end in `?v=…`. In Application → Cookies, `csrftoken` is set on this first load.
2. Register a new user: you land on the dashboard. Hard-refresh: you stay signed in, with no flash of the signed-out page.
3. Register again with the same username in another window: the error appears under the username field.
4. Log out, then log in with a wrong password: "Invalid username or password." shows. Log in correctly.
5. In a private window, register a second user. Send a friend request from one to the other, then refresh the receiver's dashboard: the request is listed. Accept it, refresh both: each lists the other. Remove the friend. Try reject on a fresh request.
6. Create a room with a password. The room page loads its details, though its socket connection fails until P4. As the other user, join from the dashboard with a wrong password (error shown), then the right one.
7. Hard-refresh on `/room/<code>` and on `/dashboard`: the page loads, not a 404.
8. Visit `/api/nope/`: you see `{"error": "Not found."}`. Visit `/docs`: FastAPI's API docs page loads.

## Behaviour differences to know

- **New URLs:** `/docs`, `/redoc` and `/openapi.json` (FastAPI's API docs, your decision 6). They used to serve the SPA shell.
- **The trailing-slash redirect is 307, not Django's 301.** A 307 makes the browser repeat the same method, so a POST missing its slash still works. Under Django in production it silently became a GET.
- **Bare prefixes:** `/api/`, `/ws/`, `/media/`, `/static/`, and `/admin/` until P5, redirect to the version without the slash, which serves the SPA shell. Django gave a 404. No real page or API call uses these URLs.
- **Methods are limited per route.** Django handed every method to the view.
  - API routes accept GET + POST. PUT/PATCH/DELETE get a JSON 405 from the router (e.g. `send_friend_request` used to answer a PUT with 400 "Invalid request."). HEAD on an API route is 405.
  - The SPA shell accepts GET + HEAD. A POST to e.g. `/dashboard` is now a JSON 405 instead of the HTML page.
- **Missing static files** get a JSON 404 instead of an HTML one.
- **Static caching:** WhiteNoise sent a year-long `Cache-Control` for hashed files. StaticFiles sends none, so browsers revalidate with ETag/Last-Modified (304, verified). `?v=` still busts the cache after a rebuild.
- **WebSockets aren't served until P4**, so the notification socket and room chat fail in the browser for now.

## Open items

1. **P4:** remove the `DJANGO_SETTINGS_MODULE` bridge in `roomchat/asgi.py` together with Channels, and add the WebSocket routes back.
2. **P5:** `greenlet` is missing from `requirements.txt` (a P1 gap: sqladmin imports SQLAlchemy's asyncio module, which needs it). P5 must add it, along with the `/admin` mount, the login and the CSRF exemption (P2 open item 1).
3. **`CLAUDE.md` isn't on disk** (it's gitignored and absent), so I couldn't check P3 against its invariants. I kept the ones the plan and code point to: only the two error shapes (`{"error"}` / `{"errors"}`); room history using the same `MessageResponse` / `reply_to` shape as live socket messages; the room-access check order in `room_detail_api` (ban, then password/invitation, then history) unchanged.
4. **Closed from earlier phases:**
   - P1 item 1 and P2 item 4: `create_user` now exists, and handles unusable passwords.
   - P2 item 3: type hints added.
   - P1 item 2 (defaults only fill in at flush): checked. No P3 view reads a default before its commit.
5. **Still open from P2:** expired session rows are never deleted (item 2).
6. **Optional follow-up:** long-lived `Cache-Control` headers for `?v=` static URLs, if you want WhiteNoise's caching back. It's not in the plan, so I didn't add it.
7. The smoke script is in session scratch space (`/tmp/claude-1000/-home-atharva-projects-roomchat/d0813baa-dbbf-4516-ac84-ad92fb6b3963/scratchpad/p3_smoke.py`). Copy it if you want to keep it. P6 replaces it with pytest.
