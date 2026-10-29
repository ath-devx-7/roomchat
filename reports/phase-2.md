# Phase 2: Auth, sessions, CSRF, middleware

**Branch:** `migration` (on top of `5a055b8`). **Status:** implemented and verified, **not committed** (your call). Scope is P2 only. No views, routes, consumers or `asgi.py` were touched.

**What this phase is about.** Django gave us four things for free that FastAPI doesn't have, so this phase rebuilds them by hand:

- **Auth** (authentication: checking who a user is): password hashing, login, logout.
- **Sessions** (the server remembering a visitor between requests). Think of a coat check: the browser only keeps the ticket (the `sessionid` cookie), and the server keeps the coat (the data, in the `django_session` table).
- **CSRF protection** (Cross-Site Request Forgery: stopping some other website from making your browser send requests to us with your cookies attached).
- **Middleware** (code that wraps every request and response). It's like a row of airport checkpoints: every request passes through them in a fixed order on the way in, and the response passes back through them on the way out.

## Files

| File | Change |
|---|---|
| `roomchat/auth.py` | **New.** Password and login logic. `make_password` and `check_password` create and verify password **hashes** (a hash is a one-way scrambled version of the password, so the real password is never stored). They use Django's exact format, `pbkdf2_sha256$…`, with 1,200,000 **iterations** like Django 6.0 (iterations = how many times the hashing is repeated; more makes guessing passwords slower). Also `authenticate` (check a username + password), `login`, `logout`, `get_user` (find the logged-in user from the session) and `AnonymousUser` (a stand-in object meaning "nobody is logged in", so code can ask `user.is_authenticated` instead of checking for `None`). Plus two small helpers that `sessions.py` and `middleware.py` reuse: `get_random_string` (secure random tokens) and `salted_hmac`. An **HMAC** is a tamper-proof stamp computed from some data plus a secret; if anyone edits the data, the stamp no longer matches. Ours is keyed by `SECRET_KEY` + a purpose string, so a stamp made for one purpose can't be passed off as another. |
| `roomchat/sessions.py` | **New.** `SessionStore`, which reads and writes sessions in the existing `django_session` table (the `Table` defined in P1). Each row stores its data as `base64(json):signature`: the session dict turned into JSON, encoded as base64 text, then followed by an HMAC signature so any edit to the row is detected. Sessions expire after 2 weeks. The session key is 32 random characters, sent to the browser in the `sessionid` cookie. It works like a dict (`[]`, `get`, `pop`, `in`, `del`, `clear`) and also has `.session_key`, `.save()` (write to the DB), `.cycle_key()` (move the same data to a new key and delete the old row), `.flush()` (empty the session and delete its row) and `.delete()` (delete a row). |
| `roomchat/middleware.py` | **Rewritten.** 8 **pure-ASGI** layers, in the plan's order. ASGI is the standard way an async Python server (daphne, uvicorn) hands requests to an app. "Pure ASGI" means each layer is just a class with `async __call__(scope, receive, send)`: `scope` is a dict describing the request, `receive` reads incoming messages, `send` sends the response out piece by piece. No framework base class is used. The file also has `ensure_csrf_cookie` (a decorator that makes sure that view's response sets the CSRF cookie), `json_validation_errors` (the opt-in marker for layer 8; it now sets `request.state._json_validation_errors`), and an ordered `MIDDLEWARE` list. |
| `roomchat/errors.py` | `api_login_required`, `require_POST_json` and `format_pydantic_errors` are **unchanged**; only the `JsonResponse` import changed. Added: `JsonResponse` (accepts Django's `status=` keyword, so view code doesn't change), `form_data` (the replacement for `request.POST`; a FastAPI dependency that returns the parsed form body), the 404/405/500 handlers (`{"error": "Not found." / "Method not allowed." / "Server error."}`) and an `exception_handlers` dict (maps a status code to its handler, for the app to use). |
| `reports/phase-2.md` | **New.** This report. |

### The middleware chain (outermost first)

"Outermost" = the first layer a request hits and the last one the response leaves through.

1. **Starlette's `TrustedHostMiddleware`**, fed by `trusted_hosts()`. It rejects any request whose `Host` header (the domain name the browser asked for) isn't one of ours. `www_redirect` is off. That option would redirect `example.com` to `www.example.com`, and Django never did that.
2. **`SecurityHeadersMiddleware`** adds four security headers to every response. A header is only added if the response hasn't already set it.
   - `X-Content-Type-Options: nosniff`: the browser must trust our declared content type and not guess.
   - `X-Frame-Options: DENY`: no other site may show our pages inside an `<iframe>`.
   - `Referrer-Policy: same-origin`: the `Referer` header (the URL you came from) is only sent to our own site.
   - `Cross-Origin-Opener-Policy: same-origin`: windows from other sites can't get a handle to our window.
3. **Starlette's `GZipMiddleware`**, with defaults: it compresses responses over 500 bytes (for browsers that accept gzip).
4. **`DBSessionMiddleware`**: one `db` (a SQLAlchemy session, i.e. one "conversation" with the database that holds a connection) per HTTP request, closed at the end. WebSockets are skipped.
5. **`SessionMiddleware`**: loads the session into `scope['session']` (`scope` is the per-request dict; views see it as `request.session`). On HTTP it saves the session and sets the cookie when the response starts, i.e. at the moment the headers go out, which is the last chance to add a cookie. On a WebSocket it only loads.
6. **`AuthenticationMiddleware`**: sets `scope['user']` (seen as `request.user`).
7. **`CsrfViewMiddleware`**: runs on **unsafe methods** (POST, PUT, PATCH, DELETE: the ones that change data). It first checks `Origin` (a header the browser adds naming the site that sent the request), or `Referer` if needed. Then it compares the `X-CSRFToken` header with the `csrftoken` cookie in **constant time** (the comparison takes the same time no matter where the strings differ, so an attacker can't guess the token one character at a time by measuring response times). Why this works: another site can make the browser *send* our cookie, but it can't *read* it, so it can't copy it into the header. A failure returns JSON 403 `{"error": "CSRF verification failed."}`.
8. **`PydanticValidationErrorMiddleware`**: opt-in (only for views marked with `@json_validation_errors`), same contract as before. When Pydantic rejects the request body, it returns `{"errors": …}` 400 instead of a crash.

## Decisions

**Decided by you**

- **WebSocket DB scope: short.** Layer 4 is HTTP-only (plan rule 1: one `db` per HTTP request). At a WebSocket **handshake** (the opening HTTP request that turns into a long-lived socket), layers 5 and 6 each open a tiny `db` scope for their single query and close it straight away. So no database connection is held while the socket stays open, which can be hours. Like borrowing a library book to check one page and returning it right away, instead of keeping it for the whole visit.
- **DB calls run on a thread pool.** The middleware's database queries are **sync** (blocking: the thread waits until Postgres answers). They go through `run_db()` → Starlette's `run_in_threadpool` (runs the function on a separate worker thread and waits for it without blocking). That way the **event loop** (the one thread that serves every connection in turn) never freezes while waiting on the DB.
- **Wiring is left to P3.** P2 only provides `MIDDLEWARE` and `exception_handlers`; P3 passes them to the app it builds.
- **Signing uses the stdlib.** Session data is signed with Python's built-in `hmac` + `hashlib`, no extra library. Any row with a bad signature, including old Django-format rows, loads as an empty session. That's the expected one-time logout at **cutover** (the moment production switches from Django to FastAPI).
- **All four auth extras from Django are ported:**
  - every request re-checks a password fingerprint (`_auth_user_hash`, an HMAC of the user's password hash, stored in the session at login). If the password changed, the fingerprint no longer matches, so old sessions get logged out;
  - an unknown username still runs the hasher, so response time doesn't reveal which usernames exist (a **timing attack** would otherwise spot that "no such user" answers faster);
  - a hash with an outdated iteration count is upgraded on the next successful login (the only moment we have the plain password to re-hash);
  - login issues a fresh CSRF token.
- **All four middleware extras from Django are ported:**
  - `Vary: Cookie` (tells caches the response differs per user, so one user's response is never served to another);
  - no session save on a 5xx response (server error), so a crashed request doesn't store half-finished session changes;
  - over HTTPS, the `Referer` is checked when `Origin` is missing;
  - Django-style patterns: `.example.com` in ALLOWED_HOSTS (matches the domain and all its subdomains), and `https://*.example.com` in CSRF_TRUSTED_ORIGINS (any subdomain, over https).
- **Error handlers cover 404/405/500 only**, exactly as the plan says.

**Decided by me (delegated to me)**

- `ensure_csrf_cookie` lives in `middleware.py`. It sets `request.state.csrf_cookie_needed`; login sets `request.state.csrf_rotate`. (`request.state` is a per-request scratchpad that views and middleware can both read and write.) Layer 7 reads both flags from `scope['state']`, which is where Starlette keeps `request.state`.
- `SessionStore` is a small class with explicit methods, not a `dict` subclass. With a `dict` subclass, some built-in methods can change the data without going through our code. With explicit methods, every change sets `modified`, so none slips past unsaved. It loads its row as soon as it is created. An unknown or expired key is dropped, so `save()` makes a fresh key rather than reusing one the browser sent.
- Saving uses a Postgres **upsert** ("insert, or update if the key already exists", in one statement: `INSERT … ON CONFLICT DO UPDATE`), followed by `db.commit()` (plan rule 2: commit right after every write, like Django's autocommit).
- **Cookies match Django's defaults:**
  - `sessionid`: 2 weeks, **HttpOnly** (JavaScript can't read it, so injected scripts can't steal it), **SameSite=Lax** (the browser won't attach it to cross-site POSTs or background requests, only to normal link clicks), `Secure` (sent over HTTPS only) = `SESSION_COOKIE_SECURE`.
  - `csrftoken`: 1 year, readable by JS (the SPA has to read it to copy it into the header), SameSite=Lax, `Secure` = `CSRF_COOKIE_SECURE`.
- CSRF tokens are 32 letters/digits and are **not masked**. Masking is Django's trick of scrambling the token with fresh random data on every response, so it looks different each time while meaning the same thing. The SPA just copies the cookie value into the header, so a plain comparison is enough. Old Django cookies already have this format, so they keep working.
- `login()` follows Django exactly:

  | Situation before login | What happens to the session |
  |---|---|
  | It belongs to another user, or is a stale one | **flush** (wiped, new key) |
  | Nobody was logged in | **cycle_key** (data kept, new key) |
  | The same user logs in again | key left alone |

  It then updates `last_login` and commits.
- The `salted_hmac` purpose strings are roomchat's own (`roomchat.sessions`, `roomchat.auth.get_session_auth_hash`). Matching Django's strings would gain nothing, because sessions reset at cutover anyway.
- The 405 handler keeps Starlette's `Allow` header (lists the methods the URL does accept, e.g. `Allow: GET`).

## Verification

Everything ran on a scratch DB (a throwaway database built with `alembic upgrade head`, i.e. all migrations applied), which was dropped afterwards. The dev DB was not touched.

| Check | Result |
|---|---|
| **Django ↔ ours compatibility:** each side's `check_password` accepts the other's hash; same iteration count; wrong, empty, unusable (`!`, Django's marker for "no usable password") and unknown-algorithm hashes give False | Pass |
| **`authenticate`:** success, wrong password, unknown user, inactive user, old-iteration hash upgraded | Pass |
| **`SessionStore`:** save/reload; `cycle_key` (data moves, old row deleted); `del` + `save` (the pattern `revoke_room_grant` uses); `flush`; unknown key; tampered or garbage data → `{}` | Pass |
| **`get_user`:** returns the right user; a password change flushes the session and returns AnonymousUser | Pass |
| **End-to-end over a real server:** a throwaway FastAPI app using `MIDDLEWARE` + `exception_handlers`, **served by daphne** (the real ASGI server the project uses until P7 swaps in uvicorn, not a test shortcut), driven the way the SPA does it (25 checks): csrftoken cookie from `@ensure_csrf_cookie`; security headers; gzip; no cookie for anonymous visits; 403 JSON for a missing token, wrong token or foreign Origin; login sets `sessionid` (flags checked), rotates CSRF and adds `Vary: Cookie`; `request.user` and `request.session` persist across requests; `require_POST_json` 405 unchanged; router 404/405 and crash 500 return JSON; `@json_validation_errors` → 400 `{"errors"}`, while an unmarked view → 500; a bad Host → 400; logout deletes the cookie and is followed by a 401 | Pass |
| **WebSocket handshake** (via asgiref's `ApplicationCommunicator`, a test helper that talks to an ASGI app directly without a server): `scope['user']` and `scope['session']` loaded; an unknown key gives an anonymous user; no `db` scope leaks; **no connection left "idle in transaction"** (a Postgres connection that started a transaction and is just sitting there, holding resources) | Pass |
| **HTTPS-only rules** (tested at unit level, i.e. by calling the functions directly): Referer required and matching; wildcard and exact trusted origins with matching scheme; `.example.com` host pattern; DEBUG localhost default; `Secure` flag | Pass |
| **5xx rule:** a view returning 503 after changing the session → nothing saved; a 400 → saved as usual | Pass |

## Behaviour differences to know

- **CSRF failures are now JSON 403s**, as the plan says. The SPA's `api.js` shows `data.error`, so users see "CSRF verification failed." instead of "Server error (403)".
- **CSRF is checked before routing** (routing = matching the URL to a view), not per view as in Django. So a POST without a token to a URL that doesn't exist now gets 403 instead of 404. This is harmless.
- **GZip is new.** Django never compressed API responses; whitenoise (the static-file server used with Django) only served pre-compressed static files.
- **The 500 JSON handler only applies when the app runs with `debug=False`.** In debug mode, Starlette shows a traceback page instead (P3 sets the app's debug flag).

## Open items (yours to decide, later phases)

1. **P5 admin vs CSRF:** sqladmin (the admin-panel library planned to replace Django admin) has login and edit forms that POST without an `X-CSRFToken` header, so layer 7 will reject them with 403. P5 needs an exemption for `/admin/` (sqladmin has its own login session) or another approach.
2. **Expired session rows are never deleted.** Django's `clearsessions` command used to do it. The plan has no replacement, so rows will pile up slowly.
3. **P3:** FastAPI decides what to pass into a view by reading its **type hints** (e.g. `request: Request`, `websocket: WebSocket`). It can still read them through our decorators thanks to `@wraps` (which copies the original function's signature onto the wrapper). But `spa(request, *args, **kwargs)` will need a real signature, because FastAPI can't work out what `*args, **kwargs` should be.
4. **Carried over from P1, still open:** `User.objects.create_user` (Django's helper that hashes the password and saves a new user) has no replacement, and `make_password(None)` (Django's way to create an "unusable password") isn't ported because nothing calls it yet.
