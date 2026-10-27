# Phase 2: Auth, sessions, CSRF, middleware

**Branch:** `migration` (on top of `5a055b8`). **Status:** implemented and verified, **not committed** (your call). Scope is P2 only. No views, routes, consumers or `asgi.py` were touched.

## Files

| File | Change |
|---|---|
| `roomchat/auth.py` | **New.** `make_password`, `check_password` (Django's `pbkdf2_sha256$…` format, 1,200,000 iterations like Django 6.0), `authenticate`, `login`, `logout`, `get_user`, `AnonymousUser`. Also two small helpers that `sessions.py` and `middleware.py` reuse: `get_random_string` and `salted_hmac` (an HMAC, i.e. a tamper-proof stamp, keyed by SECRET_KEY + a purpose string). |
| `roomchat/sessions.py` | **New.** `SessionStore` on the existing `django_session` table (the P1 `Table`). Session data is stored as `base64(json):signature`, with a 2-week expiry and a 32-character key in the `sessionid` cookie. API: dict access (`[]`, `get`, `pop`, `in`, `del`, `clear`) plus `.session_key`, `.save()`, `.cycle_key()`, `.flush()`, `.delete()`. |
| `roomchat/middleware.py` | **Rewritten.** 8 pure-ASGI layers in the plan's order (pure ASGI = a plain `async __call__(scope, receive, send)`, with no framework base class), `ensure_csrf_cookie`, `json_validation_errors` (now sets `request.state._json_validation_errors`), and an ordered `MIDDLEWARE` list. |
| `roomchat/errors.py` | `api_login_required`, `require_POST_json` and `format_pydantic_errors` are **unchanged**; only the `JsonResponse` import changed. Added `JsonResponse` (accepts Django's `status=`), `form_data` (the replacement for `request.POST`), the 404/405/500 handlers (`{"error": "Not found." / "Method not allowed." / "Server error."}`) and an `exception_handlers` dict. |
| `reports/phase-2.md` | **New.** This report. |

### The middleware chain (outermost first)

1. Starlette's `TrustedHostMiddleware`, fed by `trusted_hosts()`. `www_redirect` is off, because Django never redirected to `www.`.
2. `SecurityHeadersMiddleware`: nosniff, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin`. A header is only added if the response hasn't already set it.
3. Starlette's `GZipMiddleware`, with defaults: it compresses responses over 500 bytes.
4. `DBSessionMiddleware`: one `db` per HTTP request, closed at the end. WebSockets are skipped.
5. `SessionMiddleware`: loads `scope['session']`. On HTTP it saves the session and sets the cookie when the response starts. On a WebSocket it only loads.
6. `AuthenticationMiddleware`: sets `scope['user']`.
7. `CsrfViewMiddleware`: on unsafe methods it checks Origin (or Referer), then compares the header token to the cookie in constant time. A failure returns JSON 403 `{"error": "CSRF verification failed."}`.
8. `PydanticValidationErrorMiddleware`: opt-in, same contract as before. It returns `{"errors": …}` 400.

## Decisions

**Decided by you**

- **WebSocket DB scope: short.** Layer 4 is HTTP-only (rule 1). At a WebSocket handshake, layers 5 and 6 each open a tiny `db` scope for their single query and close it straight away, so no connection is held while the socket is open.
- **DB calls run on a thread pool.** The middleware's sync queries go through `run_db()` → `run_in_threadpool`, so the event loop (the one thread serving every connection) never freezes.
- **Wiring is left to P3.** P2 only provides `MIDDLEWARE` and `exception_handlers`; P3 passes them to the app it builds.
- **Signing uses the stdlib.** Session data is signed with `hmac` + `hashlib`. Any row with a bad signature, including old Django-format rows, loads as an empty session. That's the expected one-time logout at cutover.
- **All four auth extras from Django are ported:**
  - every request re-checks a password fingerprint (`_auth_user_hash`), so a password change logs out old sessions;
  - an unknown username still runs the hasher, so response time doesn't reveal which usernames exist;
  - a hash with an outdated iteration count is upgraded on the next successful login;
  - login issues a fresh CSRF token.
- **All four middleware extras from Django are ported:**
  - `Vary: Cookie` (tells caches the response differs per user);
  - no session save on a 5xx response;
  - over HTTPS, the Referer is checked when Origin is missing;
  - Django-style patterns: `.example.com` in ALLOWED_HOSTS, and `https://*.example.com` in CSRF_TRUSTED_ORIGINS.
- **Error handlers cover 404/405/500 only**, exactly as the plan says.

**Decided by me (delegated to me)**

- `ensure_csrf_cookie` lives in `middleware.py`. It sets `request.state.csrf_cookie_needed`; login sets `request.state.csrf_rotate`. Layer 7 reads both from `scope['state']`, which is where Starlette keeps `request.state`.
- `SessionStore` is a small class with explicit methods, not a `dict` subclass, so every change sets `modified` and none slips past unsaved. It loads its row as soon as it is created. An unknown or expired key is dropped, so `save()` makes a fresh key rather than reusing one the browser sent.
- Saving uses a Postgres upsert ("insert, or update if the key exists"), followed by `db.commit()` (rule 2).
- **Cookies match Django's defaults:**
  - `sessionid`: 2 weeks, HttpOnly, SameSite=Lax, `Secure` = `SESSION_COOKIE_SECURE`.
  - `csrftoken`: 1 year, readable by JS, SameSite=Lax, `Secure` = `CSRF_COOKIE_SECURE`.
- CSRF tokens are 32 letters/digits and are not masked. The SPA echoes the cookie value into the header, so a plain comparison is enough. Old Django cookies already have this format, so they keep working.
- `login()` follows Django exactly: it flushes when the session belongs to another user or a stale one, cycles the key when nobody was logged in, and leaves the key alone when the same user logs in again. It then updates `last_login` and commits.
- The `salted_hmac` purpose strings are roomchat's own (`roomchat.sessions`, `roomchat.auth.get_session_auth_hash`). Matching Django's strings would gain nothing, because sessions reset at cutover anyway.
- The 405 handler keeps Starlette's `Allow` header.

## Verification

Everything ran on a scratch DB (`alembic upgrade head`), which was dropped afterwards. The dev DB was not touched.

| Check | Result |
|---|---|
| Django ↔ ours: each side's `check_password` accepts the other's hash; same iteration count; wrong, empty, unusable (`!`) and unknown-algorithm hashes give False | Pass |
| `authenticate`: success, wrong password, unknown user, inactive user, old-iteration hash upgraded | Pass |
| `SessionStore`: save/reload, `cycle_key` (data moves, old row deleted), `del` + `save` (the `revoke_room_grant` pattern), `flush`, unknown key, tampered/garbage data → `{}` | Pass |
| `get_user`: the right user; a password change flushes the session and returns AnonymousUser | Pass |
| Throwaway FastAPI app using `MIDDLEWARE` + `exception_handlers`, **served by daphne**, driven like the SPA (25 checks): csrftoken cookie from `@ensure_csrf_cookie`; security headers; gzip; no cookie for anonymous visits; 403 JSON for a missing token, wrong token or foreign Origin; login sets `sessionid` (flags checked), rotates CSRF and adds `Vary: Cookie`; `request.user` and `request.session` persist across requests; `require_POST_json` 405 unchanged; router 404/405 and crash 500 return JSON; `@json_validation_errors` → 400 `{"errors"}`, while an unmarked view → 500; a bad Host → 400; logout deletes the cookie and is followed by a 401 | Pass |
| WebSocket handshake (via asgiref's ApplicationCommunicator): `scope['user']` and `scope['session']` loaded; an unknown key gives an anonymous user; no `db` scope leaks; **no connection left "idle in transaction"** | Pass |
| HTTPS-only rules (unit level): Referer required/matching, wildcard and exact trusted origins with matching scheme, `.example.com` host pattern, DEBUG localhost default, `Secure` flag | Pass |
| A view returning 503 after changing the session → nothing saved; a 400 → saved as usual | Pass |

## Behaviour differences to know

- CSRF failures are now JSON 403s, as the plan says. The SPA's `api.js` shows `data.error`, so users see "CSRF verification failed." instead of "Server error (403)".
- CSRF is checked before routing, not per view as in Django. A POST to a URL that doesn't exist, sent without a token, now gets 403 instead of 404. This is harmless.
- GZip is new. Django never compressed API responses; whitenoise only served pre-compressed static files.
- The 500 JSON handler only applies when the app runs with `debug=False`. In debug mode, Starlette shows a traceback page instead (P3 sets the app's debug flag).

## Open items (yours to decide, later phases)

1. **P5 admin vs CSRF:** sqladmin's login and edit forms POST without an `X-CSRFToken` header, so layer 7 will reject them with 403. P5 needs an exemption for `/admin/` (sqladmin has its own login session) or another approach.
2. **Expired session rows are never deleted.** Django's `clearsessions` command used to do it. The plan has no replacement, so rows will pile up slowly.
3. **P3:** FastAPI needs type hints to inject arguments (`request: Request`, `websocket: WebSocket`). It reads them through the decorators thanks to `@wraps`, but `spa(request, *args, **kwargs)` will need a real signature.
4. Carried over from P1, still open: `User.objects.create_user` has no replacement, and `make_password(None)` (Django's "unusable password") isn't ported because nothing calls it yet.
