# Test run: every feature from P0–P3

**Branch:** `migration` (P3 uncommitted). **Date:** 2026-10-29. **Project code changed:** none. `git status` is the same as at the end of P3, apart from this report. All test code was throwaway and lives in the session scratchpad.

## Summary

| Suite | What it covers | Checks | Passed |
|---|---|---|---|
| A | P0 + P1: schema, Alembic migrations, adopting a Django DB, dev DB (read-only), dependencies | 28 | 27 |
| B | P1: models, `db` layer, DB-level cascades, settings | 20 | 20 |
| C | P2 units (hashing vs Django, auth, sessions, CSRF/host helpers) + P3 `create_user` | 66 | 66 |
| D | P2 middleware end to end (served by daphne) + WebSocket handshake | 36 | 36 |
| E | P3 real app over HTTP: 104-check smoke test + 26 cutover / DEBUG=False checks | 130 | 130 |
| F | P3 in real Chrome with the real React bundle | 19 | 19 |
| **Total** | | **299** | **298** |

**The one failure is already known:** `import sqladmin` fails because `greenlet` is missing from `requirements.txt` (P3 open item 2; due in P5). **No new bugs were found in the migrated code.**

## How it was run

- **Scratch DBs only:**
  - `roomchat_t_empty`: built with `alembic upgrade head`.
  - `roomchat_t_django`: migrated **and filled by Django itself** from commit `daf5322`, the last pure-Django commit, checked out as a temporary **git worktree** (a second checkout of an old commit in another folder).
  - `roomchat_t_http`: used by the HTTP and browser suites.
  - Every script refused to touch any DB not named `roomchat_t_*`. All three DBs and the worktree were removed at the end; only `roomchat` remains.
- **Dev DB `roomchat`:** only `alembic current` and `alembic check`, which both just read the schema.
- **Servers:**
  - the real app: `daphne roomchat.asgi:application`, three times: fresh DB, Django DB, and `DEBUG=False`;
  - a throwaway app built from the real `MIDDLEWARE` + `exception_handlers` plus test-only views (a crash, a 503, validation errors), with DEBUG on and off.
- **HTTP calls** imitate `frontend/src/lib/api.js`: form-urlencoded POSTs, `X-CSRFToken` copied from the cookie, a same-site `Origin` header, cookies kept between requests.

## Results per phase

### P0: schema capture

| Check | Result |
|---|---|
| Fresh `manage.py migrate` (Django, `daf5322`) → `pg_dump` is **byte-identical** to `SCHEMA_SQL` in `0001_baseline.py` (random `\restrict` lines ignored) | Pass |
| Baseline has 16 tables | Pass |

### P1: foundation

| Check | Result |
|---|---|
| Empty DB → `upgrade head`. Schema = P0 except exactly 12 `ON DELETE CASCADE` + 2 `SET NULL` (`reply_to_id`, `banned_by_id`) and the `alembic_version` table. FKs still `DEFERRABLE INITIALLY DEFERRED` | Pass |
| `alembic check`: models match the schema (empty DB and adopted DB) | Pass |
| `downgrade 0001_baseline` = P0. `downgrade base` leaves no tables. `upgrade head` again = identical | Pass |
| **Adopting a DB Django migrated and filled** (users, friendships, protected room, membership, messages with a reply, ban, invitation, session): `upgrade head` succeeds, schema = fresh head, **row counts unchanged** | Pass |
| Dev DB: at `0002_fk_on_delete (head)`, `alembic check` clean | Pass |
| `pip check` clean. alembic, fastapi, itsdangerous, jinja2, multipart, sqlalchemy all import | Pass |
| `import sqladmin` | **Fail (known: needs greenlet)** |
| `db` used outside a scope raises `LookupError` | Pass |
| Python-side defaults after flush (User, Room, Message, Ban, Invitation, Friendship) | Pass |
| `Room()` gets a 6-char `[A-Z0-9]` code; 50 generated codes are all distinct | Pass |
| `memberships.count()` / `is_full` (dynamic relationship) | Pass |
| `__str__` texts and reverse names (`owned_rooms`, `messages`, `replies`, `bans_issued`, `received_invitations`) as in Django | Pass |
| **DB cascades:** deleting a message nulls replies' `reply_to`; deleting the banning user keeps the ban with `banned_by` NULL; deleting a user removes their memberships, messages, friendships and owned rooms; deleting a room removes its memberships, bans, invitations and messages; ORM `db.delete(room)` works | Pass |
| Django-written rows read back correctly through the new models | Pass |
| Settings: Secure cookies = `not DEBUG`; `RENDER_EXTERNAL_HOSTNAME` added to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`; `SESSION_ENGINE`; `STATIC_URL` | Pass |

### P2: auth, sessions, CSRF, middleware

| Check | Result |
|---|---|
| **Password hashes vs Django's own code:** Django verifies ours, we verify Django's, same `pbkdf2_sha256$1200000$` format, byte-identical output for the same salt | Pass |
| Wrong / empty / `None` / unusable `!` / unknown-algorithm hashes rejected | Pass |
| Old-iteration hash (870,000) accepted and upgraded on login | Pass |
| `authenticate`: success, wrong password, unknown user (the hasher still runs, so timing doesn't leak), missing args, inactive user | Pass |
| `SessionStore`: new, save (32-char key, 2-week expiry), reload, `cycle_key`, `del` + save, `flush`, unknown key, expired row, tampered or garbage data → `{}`. Django-format data → `{}` (the planned one-time logout) | Pass |
| `login` (cycle / same-user / other-user flush, CSRF rotate, `last_login`), `get_user` (password change → logged out, deactivated → anonymous), `logout`, `AnonymousUser` | Pass |
| CSRF helpers: Origin exact / trusted / `https://*.example.com` wildcard / wrong scheme / look-alike domain; https Referer rules; `.example.com` host expansion; DEBUG localhost default; cookie flags; token format | Pass |
| **Middleware served by daphne:** 4 security headers; gzip over 500 bytes only; no cookies for anonymous visitors; bad `Host` → 400 | Pass |
| JSON 404 / 405 (+ `Allow`) / 500 (`debug=False`); `require_POST_json` 405; `@json_validation_errors` → 400 `{"errors"}`, an unmarked view → 500 | Pass |
| CSRF: missing / wrong token, foreign Origin, no cookie → JSON 403; `@ensure_csrf_cookie`; an existing token is kept | Pass |
| Login cookie: HttpOnly, SameSite=Lax, 2 weeks, `Vary: Cookie`, CSRF rotated; `request.user` persists; **503 → session not saved, 400 → saved**; logout deletes the cookie and the DB row | Pass |
| An unknown `sessionid` → anonymous, and the cookie is deleted. **Same as Django's SessionMiddleware** (checked in Django's source) | Pass |
| `DEBUG=False`: `sessionid` and `csrftoken` cookies are `Secure` | Pass |
| WebSocket handshake: `scope['user']` / `scope['session']` loaded from the cookie, unknown key → anonymous, no `db` scope leaked, no connection left "idle in transaction" | Pass |

### P3: HTTP controllers, SPA shell

| Check | Result |
|---|---|
| Full P3 smoke test (104 checks: SPA shell, `?v=` hashes, `tojson` escaping, static + gzip + ETag 304, catch-all exclusions, `/docs`, slash redirects, 404/405/403/401, auth, friends + Redis publish, rooms, joins, bans, invitations, history, services, no leaked transactions) | Pass (104/104) |
| `create_user` matches Django's `normalize_email` for 6 tricky inputs and its NFKC username normalisation; no password → unusable `!` hash; committed | Pass |
| **Cutover on the Django-filled DB:** Django-era `sessionid` → signed out, and logging in from there gives a new key and deletes the old row. Django-created users log in with their old passwords. Stored email returned as stored. Dashboard / friends / room history / invitations show the Django data. Django-hashed room password works for join. Django ban enforced on detail and join. Inactive user refused. 870,000-iteration hash upgraded. New users and friend requests work alongside the old data | Pass (26/26) |
| Real app with `DEBUG=False`: Secure cookies; JSON 404 | Pass |
| **Chrome, real React bundle:** landing renders; 3 assets load with `?v=`; 32-char `csrftoken` on first load; register (field errors, then success); hard refresh keeps you signed in; `sessionid` invisible to JS (HttpOnly); logout → `/login` + 401; bad login → 400 + toast "Invalid username or password."; login; friend requests from 2 other users appear; accept → 200, reject → 200, refresh confirms; create a protected room → room page; hard refresh on `/room/<code>` and `/dashboard`; another user gets the "protected" 403, then the wrong password → toast "Incorrect room password.", the right one → joins the room; `/api/nope/` shows JSON; `/docs` shows Swagger UI | Pass (19/19) |

## Things noticed (not failures)

1. **Emails on reserved domains are rejected at sign-up.** For example, `alice@browser.test` gets "Enter a valid email address.".
   - **Cause:** the pydantic `EmailStr` check in `accounts/schemas.py`, whose email-validator refuses reserved domains like `.test`.
   - **Not a migration change:** that file is identical to `daf5322`, so this behaviour predates the migration.
2. **Django-era session rows stay in `django_session` until they expire** (up to 2 weeks after cutover). Their cookies stay in browsers, but the users are signed out, which is the planned one-time logout. Nothing deletes expired rows (P2 open item 2).
3. **WebSocket errors in the browser console** (`[ws] socket error /ws/notifications/` every few seconds), and the room page shows "Connecting…". This is expected until P4.
4. **Tooling only:** Chrome's screenshot command timed out twice on the dashboard (probably while the page was busy retrying the socket). Text and DOM checks were used there instead. The page itself worked.

## Mistakes in my test scripts (fixed and rerun; the app code was not touched)

- **Suite B** read a user's ID after the row was deleted. It now saves the IDs first.
- **Suite C** asked Django for an md5 hasher that isn't enabled; it now uses a hand-written unknown-algorithm hash. Two weak checks were also made real: a placeholder that always passed, and an operator-precedence slip.
- **Suites D and E** expected a stale or Django-era session cookie to be handled differently. I checked Django's own source: the app matches Django, so I corrected my expectations.
- **Suite E** reused a username on a second run. It now makes a unique one.

## Not covered (by design)

- WebSockets and consumers (P4).
- The admin panel (P5).
- `roomchat/tests.py`, which is still the Django test suite and is rewritten in P6.

## Where things are

- **Scripts** (session scratchpad, temporary): `/tmp/claude-1000/-home-atharva-projects-roomchat/d0813baa-dbbf-4516-ac84-ad92fb6b3963/scratchpad/tests/`
  - `common.py`, `httpclient.py`
  - `suite_a.py` … `suite_e_extra.py`, `suite_e_smoke.py`
  - `mw_app.py`, `seed_django.py`, `rebuild_django_db.py`
  - Copy the folder if you want to keep it.
- **Browser test accounts:** generated for this run and stored only in `browser_creds.json` in that folder. They existed only in the dropped scratch DB.
- **Browser recording:** `p3_browser_walkthrough.gif` (50 frames) was exported through Chrome's download. It is **not** in `~/Downloads` on this machine, so check the download location of the Chrome profile the extension is connected to.
