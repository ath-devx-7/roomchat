# RoomChat: Django → FastAPI migration plan

## Context

RoomChat is a Django 6 + Channels app: a JSON API, two WebSocket consumers, and a committed React bundle.
The goal is to swap the **framework** to FastAPI while keeping these unchanged:

- the project layout,
- function names and bodies (wherever the swap doesn't force a change),
- the three layers: `models.py` = data, `services.py` = service, `views.py`/`consumers.py` = controller,
- middleware behaviour, auth, the DB schema, every URL, and the frontend.

Daphne serves the new app until a late phase swaps it for uvicorn.

**Status:** planned, not yet implemented. Every decision in the table below was confirmed with the user.

## Decisions (all confirmed with user)

| Concern | Django today | Replacement |
|---|---|---|
| ORM / migrations | Django ORM, `*/migrations/` | **SQLAlchemy 2.0 sync** + **Alembic** |
| Realtime | channels + channels_redis `RedisPubSubChannelLayer` | **in-house layer** on `redis.asyncio` + msgpack (both already deps) |
| Sessions | `django.contrib.sessions` (DB) | own server-side store **on the existing `django_session` table**, cookie `sessionid` |
| Password hashing | `django.contrib.auth.hashers` | **stdlib port**: `make_password`/`check_password`, same `pbkdf2_sha256$…` format |
| CSRF | `CsrfViewMiddleware`, `@ensure_csrf_cookie` | **hand-written** middleware + decorator, same `csrftoken` cookie / `X-CSRFToken` header |
| Admin `/admin/` | django.contrib.admin | **sqladmin** (+ itsdangerous, admin-only login session) |
| Static | whitenoise + collectstatic manifest | Starlette `StaticFiles` + `static()` helper adding `?v=<content-hash>`; `GZipMiddleware` |
| Template | Django template | **Jinja2** (`Jinja2Templates`) |
| Request data | `request.POST` | `form = Depends(form_data)` (python-multipart); `request.user`/`request.session` unchanged (Starlette reads `scope['user']`/`scope['session']`) |
| Tests | Django TestCase + WebsocketCommunicator | **pytest + pytest-asyncio + httpx** (still `roomchat/tests.py`) |
| CLI | `manage.py` | deleted; `uvicorn` / `alembic` / `pytest` + `roomchat/cli.py createsuperuser` |
| FK deletes | Django emulates CASCADE/SET_NULL in Python | **DB-level `ON DELETE`** via Alembic migration. This is the one approved schema change. |
| Server | daphne | **uvicorn[standard]** (late phase) |
| Kept | asgiref, pydantic, psycopg, redis, msgpack, python-dotenv, email-validator | |
| Rollout | n/a | one feature branch, one commit per phase, merge when the full suite passes |

## Translation rules (apply everywhere, described once)

1. **DB session.** `roomchat/db.py` exposes `db = scoped_session(SessionLocal, scopefunc=<ContextVar>.get)`,
   with `expire_on_commit=False` and `pool_pre_ping=True` (replaces `CONN_MAX_AGE`/`CONN_HEALTH_CHECKS`).
   It works like Django's global ORM, so **service and view signatures keep their parameters**: there is
   no `db` argument threaded through. Scopes:
   - HTTP: one `db` per request, opened and closed in middleware.
   - Consumers: one `db` per `@database_sync_to_async` call.
2. **Autocommit parity.** Django commits every write immediately. So each translated write
   (`create`/`save`/`delete`/`update_or_create`/`get_or_create`) is followed by `db.commit()` at that spot,
   and `with transaction.atomic():` becomes one block ending in a single commit. This keeps
   `notify_friend_request`'s publish after the commit (`accounts/views.py:26`).
3. **Queries, 1:1:**

   | Django | SQLAlchemy |
   |---|---|
   | `Model.objects.filter(a=x).first()` | `db.scalars(select(Model).where(Model.a == x)).first()` |
   | `Q(...) \| Q(...)` | `or_(...)` |
   | `.exists()` | `db.scalar(select(exists().where(...)))` |
   | `select_related` | `options(joinedload(...))` |
   | `X.DoesNotExist` / `.get()` | `.one_or_none()` plus the same `None` branch |

   Message default ordering (`Meta.ordering`) only matters where queries already `order_by`.
4. **Models keep their names, columns and table names** (`__tablename__ = 'rooms_room'`, etc.).
   - `User` maps `auth_user` (all 11 columns, `Integer` PK) and lives in `accounts/models.py`;
     `from django.contrib.auth.models import User` becomes `from accounts.models import User`.
   - `User` gets `is_authenticated`/`is_anonymous` properties. `roomchat/auth.py` has an `AnonymousUser`
     counterpart.
   - `auto_now_add` becomes a Python-side default (no DB default, so the schema is unchanged).
   - `Room.memberships` is `lazy="dynamic"`, so `active_user_count`/`is_full` stay literally
     `self.memberships.count()` (`rooms/models.py:33-38`).
   - `Room.save()`'s code generation moves into `Room.__init__` (still calls `generate_room_code()`,
     under `db.no_autoflush`).
   - All relationships use `passive_deletes=True`, because the DB now does the cascading.
5. **Detached `self.room` in consumers.** Each helper runs in its own session. A helper that writes
   `self.room` or reads a relationship off it starts with `self.room = db.merge(self.room, load=False)`:
   `is_room_full`, `transfer_room_ownership`, `delete_room_from_db`, `ban_member`,
   `check_and_delete_room_if_empty`. The remaining bodies are unchanged.
6. **Responses.** `roomchat/errors.py` defines `JsonResponse(JSONResponse)` taking Django's `status=`
   kwarg, so every `return JsonResponse({...}, status=400)` line stays as is.
7. **Settings.** `roomchat/settings.py` stays a plain module with the same names and env vars.
   `from django.conf import settings` becomes `from roomchat import settings`.

## Files

**New (kept to the minimum the swap needs):**
- `roomchat/db.py`: engine, `SessionLocal`, `Base`, `db`.
- `roomchat/sessions.py`: `SessionStore` on `django_session`. HMAC-signed JSON with `SECRET_KEY`,
  2-week expiry; dict API plus `.session_key`, `.save()`, `.cycle_key()`, `.flush()`.
- `roomchat/auth.py`: `make_password`, `check_password`, `authenticate`, `login`, `logout`
  (same semantics as Django), `AnonymousUser`.
  - `login`: cycle key, set `_auth_user_id` / `_auth_user_hash`, update `last_login`.
  - `authenticate`: rejects `is_active=False`.
- `roomchat/realtime.py`: `RedisChannelLayer`, `get_channel_layer()`, `AsyncWebsocketConsumer`,
  `database_sync_to_async`, `AllowedHostsOriginValidator` (see Phase 4).
- `roomchat/staticfiles.py`: `static(path)` with a content-hash cache.
- `roomchat/cli.py`: `createsuperuser`.
- `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_baseline.py`, `alembic/versions/0002_fk_on_delete.py`.
- `pytest.ini`.

**Rewritten in place (same names):**
- `roomchat/settings.py`, `roomchat/asgi.py` (builds the FastAPI app, still exports `application`),
  `roomchat/urls.py`, `roomchat/errors.py`, `roomchat/middleware.py`, `roomchat/tests.py`.
- `accounts/{models,views,urls,admin}.py`, `rooms/{models,views,urls,routing,consumers,services,schemas,admin}.py`.
- `templates/index.html`, `requirements.txt`, `render.yaml`, `README.md`, `CLAUDE.md`, `.env.example`.

**Deleted:** `manage.py`, `roomchat/wsgi.py`, `accounts/apps.py`, `rooms/apps.py`,
`accounts/migrations/`, `rooms/migrations/`.

**Untouched:** `frontend/**`, `static/react/**`.

## Phases (one commit each, branch `fastapi-migration`)

**P0: Capture the schema (while Django still runs).**
`manage.py migrate` into a fresh DB, then `pg_dump --schema-only --no-owner`. The output becomes the
raw-SQL body of `0001_baseline.py`. It includes the Django-only tables (`auth_group*`, `auth_permission`,
`django_content_type`, `django_admin_log`, `django_migrations`), so the structure is byte-identical.

**P1: Foundation.**
- Add deps: fastapi, sqlalchemy, alembic, jinja2, python-multipart, sqladmin, itsdangerous.
- `roomchat/db.py`, settings rewrite, SQLAlchemy models (rule 4).
- Alembic:
  - `0001_baseline` **skips its DDL if `rooms_room` already exists**, so prod (Render free tier has no
    shell to `alembic stamp`) adopts it on the first `upgrade head`.
  - `0002_fk_on_delete` drops and recreates each FK with `ON DELETE`. Constraint names are looked up via
    the inspector because Django hashes them. CASCADE everywhere Django had CASCADE; SET NULL for
    `rooms_message.reply_to_id` and `rooms_roomban.banned_by_id`.
  - `env.py` `include_object` ignores the Django-only tables so autogenerate never drops them.

**P2: Auth, sessions, CSRF, middleware.**
`roomchat/sessions.py`, `roomchat/auth.py`. `roomchat/middleware.py` holds pure-ASGI middleware, in the
same order as `settings.MIDDLEWARE` today:
1. `TrustedHostMiddleware` (ALLOWED_HOSTS; localhost allowed when DEBUG with an empty list).
2. Security headers: nosniff, `X-Frame-Options: DENY`, `Referrer-Policy`, COOP.
3. `GZipMiddleware`.
4. DB-session scope.
5. `SessionMiddleware`: loads `scope['session']`; on http, saves if modified and sets the cookie
   (HttpOnly, SameSite=Lax, Secure unless DEBUG); on websocket, load only.
6. `AuthenticationMiddleware`: sets `scope['user']`.
7. `CsrfViewMiddleware`: on unsafe methods, compares header to cookie (constant-time) and checks
   Origin against host / `CSRF_TRUSTED_ORIGINS`. Answers JSON `{"error": "CSRF verification failed."}`
   403. This replaces Django's HTML 403, which the SPA already rendered as "Server error (403)".
8. `PydanticValidationErrorMiddleware`: same name and opt-in contract (`roomchat/middleware.py:21`).
   `json_validation_errors` sets `request.state._json_validation_errors`; the middleware catches
   `ValidationError` and returns `{"errors": format_pydantic_errors(e)}` 400.

`ensure_csrf_cookie` decorator, same name. `roomchat/errors.py` keeps `api_login_required`,
`require_POST_json` and `format_pydantic_errors` unchanged, and adds `JsonResponse`, `form_data`, and
404/405/500 exception handlers that emit `{"error": ...}`, so no third error shape appears.

**P3: HTTP controllers, SPA shell.**
- `accounts/urls.py`, `rooms/urls.py`: `APIRouter`s with the same paths and trailing slashes.
  - Routes accept GET and POST so the in-view method checks stay authoritative. For example,
    `send_friend_request`'s 400 "Invalid request." and `require_POST_json`'s 405 keep their behaviour.
- `roomchat/urls.py` assembles: `/api` routers, sqladmin at `/admin`, `StaticFiles` at `/static`, and
  the `spa` catch-all **last** with the same `(?!static/|media/|api/|admin/|ws/)` exclusion.
  `redirect_slashes` keeps the old APPEND_SLASH behaviour.
- View bodies: `request.POST.get` becomes `form.get`, plus the query translations. Nothing else changes.
- `rooms/schemas.py` `RoomJoin.validate_room_access` (`:73`) and `rooms/services.py` keep their
  signatures; only the queries are translated, and `make_password`/`check_password` are now imported
  from `roomchat.auth`.
- `spa` (`rooms/views.py:31`) renders `templates/index.html` via Jinja:
  - `{{ static('react/css/main.css') }}`
  - `<script id="roomchat-bootstrap" type="application/json">{{ bootstrap|tojson }}</script>`
    (`tojson` escapes `< > & '`, which keeps the `</script>` protection).
- Smoke-test under `daphne roomchat.asgi:application`.

**P4: Realtime.**
`roomchat/realtime.py` mirrors the channels API that the consumers use, so `rooms/consumers.py` only
changes its imports and its ORM (rules 3 and 5):
- Layer:
  - One shared `redis.asyncio` PubSub connection per event loop. Keying per loop is what lets
    `async_to_sync(get_channel_layer().group_send)` in `notify_friend_request` work unchanged from a
    threadpool thread.
  - A reader task fans messages out to per-channel `asyncio.Queue`s.
  - Methods: `new_channel()`, `group_add`, `group_discard`, `group_send`, `send`, `receive`.
  - Same `asgi__group__<name>` keys, msgpack payloads, no persistence.
- `AsyncWebsocketConsumer.as_asgi()` returns an ASGI app object. It handles `websocket.connect` /
  `receive` / `disconnect` exactly like channels does:
  - races socket frames against layer messages;
  - dispatches `type` → method (an unknown type raises at runtime, so CLAUDE.md invariant #2 holds);
  - provides `accept`/`send`/`close(code)`;
  - maps `scope['path_params']` onto `scope['url_route']['kwargs']`.
  - Accept-then-close in `reject()` (`rooms/consumers.py:119`) keeps working because the ASGI semantics
    are identical, so codes 4001/4003/4004/4005 still reach the browser.
- `database_sync_to_async` = asgiref `sync_to_async(thread_sensitive=False)` plus a per-call `db` scope.
  This avoids channels' single-thread serialisation.
- `revoke_room_grant` (`:417`) is unchanged: `settings.SESSION_ENGINE = 'roomchat.sessions'` keeps its
  `import_module(...).SessionStore(session_key)` line valid.
- `rooms/routing.py` defines Starlette `WebSocketRoute`s wrapped in `AllowedHostsOriginValidator`.

**P5: Admin.**
`accounts/admin.py` and `rooms/admin.py` become sqladmin `ModelView`s with the same `list_display` and
filters. The auth backend uses `authenticate()` and requires `is_staff` and `is_active`; its own
itsdangerous session covers the admin only.

**P6: Tests.**
- `pytest.ini` (`python_files = tests.py`, `asyncio_mode = auto`).
- Fixtures at the top of `roomchat/tests.py`:
  - a session-scoped test DB (`test_<DB_NAME>`, `alembic upgrade head`, dropped at the end);
  - `TRUNCATE … RESTART IDENTITY CASCADE` after each test, which covers both TestCase and
    TransactionTestCase cases;
  - a `client` (TestClient) that primes and sends the CSRF cookie/header;
  - `force_login`.
- A `WebsocketCommunicator` with the same method names, built on `asgiref.testing.ApplicationCommunicator`,
  so consumer tests still inject plain-dict `scope['session']`/`scope['user']`.
- The same test names. Channel-layer tests instantiate two `RedisChannelLayer`s, as before.

**P7: Daphne → uvicorn.**
- Remove Django, channels, channels_redis, daphne, whitenoise, sqlparse, and Twisted/autobahn and their
  transitive deps; add `uvicorn[standard]`.
- `render.yaml`:
  - build: `pip install -r requirements.txt && alembic upgrade head`
  - start: `uvicorn roomchat.asgi:application --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips '*'`

**P8: Clean-up.**
- Delete the Django boilerplate listed above; add `roomchat/cli.py`.
- Update README, CLAUDE.md (commands, Stack, Tests sections) and `.env.example`.
- Cross-reference `github-issues/redis-outage-failure-modes-issue.txt` and `deploy-issues.txt`
  (ISSUE 1, orphaned memberships). Both still apply and are **not** fixed here.

## Known consequences (to state in the write-up)

- Every logged-in session is invalidated once at cutover, because the session data encoding changes.
  Accounts and passwords are unaffected.
- CSRF and 404/405 failures now return JSON `{"error"}` instead of Django HTML pages.
- `django_admin_log` rows referencing a user would block deleting that user. The table is kept
  untouched; dropping the Django-only tables is a possible follow-up, not part of this plan.

## Verification

- `pytest`, with Redis up and no dev server sharing it. The whole ported suite must pass.
- `alembic upgrade head` on:
  - an empty DB, where `pg_dump --schema-only` must equal the P0 dump except for the `0002` FK clauses
    and `alembic_version`;
  - a DB already migrated by Django, where the baseline must be skipped.
- Manual check against the built bundle under uvicorn (`yarn start` does not proxy WebSockets reliably):
  1. Register and log in/out; the CSRF cookie is set on the first load.
  2. Send a friend request and see the live toast on the other user's notification socket.
  3. Create a password room; join with the password; open the room in a second tab via pasted link,
     which must prompt for the password.
  4. Chat: send, edit, delete, reply.
  5. Kick, then rejoin, which must give 4005; transfer ownership; delete the room.
  6. Accept an invite into a protected room (admitted exactly once).
  7. The last member leaves and the room plus its messages are gone (DB cascade).
  8. `/admin/` login as a superuser created with `python -m roomchat.cli createsuperuser`.
  9. Hard refresh on `/room/<code>`.
  10. Two uvicorn workers on one Redis: a message crosses workers.
