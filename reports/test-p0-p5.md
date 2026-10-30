# Test run: every feature from P0–P5

**Branch:** `migration` (P5 still uncommitted). **Date:** 2026-10-31. **Project code changed:** none. `git status` is the same as at the end of P5. All test code was throwaway and lives outside the repo (see "Where things are").

## Summary

| Suite | What it covers | Checks | Passed |
|---|---|---|---|
| A | P0 + P1: schema capture, Alembic migrations, adopting a Django DB, dev DB (read-only), dependencies | 36 | 36 |
| B | P1: models, the scoped `db`, defaults, DB-level cascades, Django rows read back, settings | 31 | 31 |
| C | P2 units: password hashing vs Django's own hasher, `authenticate`, `SessionStore`, login/get_user/logout, CSRF and host helpers; P3 `create_user` | 67 | 67 |
| D | P2 middleware end to end (served by daphne, DEBUG on and off), plus the WebSocket handshake | 38 | 38 |
| E | P3 real app over HTTP: SPA shell, static, routing, auth, friends, rooms, invitations, services, the **Django cutover**, DEBUG=False | 119 | 119 |
| F | P4 realtime over real WebSockets: refusals, close codes, presence, chat, owner controls, notifications, invites, two server processes, hygiene | 70 | 70 |
| G | P5 admin: login rules, separate sessions, all 6 views, create/edit/delete, cascades, CSRF, routing | 107 | 107 |
| H | Chrome with the real React bundle: two users live, plus the admin | 20 | 20 |
| **Total** | | **488** | **488** |

**No new bugs were found in the migrated code.** The known issues re-confirmed along the way are listed under "Things noticed". The one greenlet failure from the P0–P3 run is gone: P5 pinned it.

## How it was run

- **Scratch DBs only.** Every script refused to touch a DB not named `roomchat_t_*`. All were dropped at the end; only `roomchat` remains.
  - `roomchat_t_djfresh`: migrated by Django itself, used only for the schema comparison.
  - `roomchat_t_empty`: built with `alembic upgrade head` (Suites B–D).
  - `roomchat_t_django`: migrated **and filled by Django itself** from `daf5322`, then adopted with `alembic upgrade head` (cutover checks). Django ran from a temporary **git worktree** (a second checkout of an old commit in another folder), which was removed afterwards.
  - `roomchat_t_http` (Suites E–F) and `roomchat_t_admin` (Suites G–H).
- **Dev DB `roomchat`:** only `alembic current` and `alembic check`, which just read the schema.
- **Redis:** checked idle first, and no dev server was running. At the end: no channels and no subscribers.
- **Servers:** always **daphne** (the project's real ASGI server until P7):
  - the real app `roomchat.asgi:application` on :8765 (fresh DB), :8766 (Django-filled DB), :8767 (`DEBUG=False`) and :8768 (a second process on the same DB and Redis);
  - a throwaway app built from the real `MIDDLEWARE` + `exception_handlers` with test-only views, on :8770 (DEBUG on) and :8771 (DEBUG off).
- **HTTP calls** imitate `frontend/src/lib/api.js`: form-urlencoded POSTs, `X-CSRFToken` copied from the cookie, a same-site `Origin` header, and cookies kept between requests.
- **WebSockets:** a small stdlib client (no extra packages) that sends real masked frames, like a browser.
- **DB facts** were always read over a fresh connection, so only committed data counts.

## Results per phase

### P0: schema capture

| Check | Result |
|---|---|
| Django (`daf5322`) migrates a fresh DB; its `pg_dump --schema-only` is **byte-identical** to `SCHEMA_SQL` in `0001_baseline.py` (random `\restrict` lines ignored) | Pass |
| The baseline has 16 tables | Pass |

### P1: foundation

| Check | Result |
|---|---|
| Empty DB → `upgrade head`. The schema equals P0 except for the `ON DELETE` clauses and the `alembic_version` table | Pass |
| Exactly 12 `ON DELETE CASCADE` + 2 `SET NULL` (`reply_to_id`, `banned_by_id`); every FK still `DEFERRABLE INITIALLY DEFERRED` | Pass |
| `alembic check` clean on the empty-built DB, the adopted DB and the dev DB | Pass |
| `downgrade 0001_baseline` = P0; `downgrade base` leaves no tables; `upgrade head` again = identical | Pass |
| **Adopting a DB Django migrated and filled** (6 users including an inactive one, a superuser and an old-iteration hash; friendships; a protected room; a membership; messages with a reply and a deleted one; a ban; an invitation; a Django session): `upgrade head` succeeds, schema = fresh head, **row counts unchanged** | Pass |
| `pip check` clean. alembic, fastapi, itsdangerous, jinja2, multipart, sqlalchemy, **sqladmin, greenlet**, redis, msgpack, psycopg, pydantic and wtforms all import. Importing `roomchat.asgi` loads no django/channels | Pass |
| `db` used outside a scope raises `LookupError`; `db_scope` has no default | Pass |
| Defaults: `Room().capacity` is `None` until flush (defaults apply at flush), then 10/""/""; User, Message, Membership, Friendship and Invitation defaults | Pass |
| `Room()` gets a 6-char `[A-Z0-9]` code in `__init__`; 50 generated codes are all distinct | Pass |
| `memberships` is dynamic: `count()`, `active_user_count`, `is_full` | Pass |
| `__str__` texts and reverse names (`owned_rooms`, `messages`, `replies`, `bans_issued`, `received_invitations`, `room_memberships`) as in Django | Pass |
| **DB cascades:** a deleted message nulls replies' `reply_to`; deleting the banning user keeps the ban with `banned_by` NULL; deleting an owner deletes their room; deleting a user removes their memberships, messages, friendships, bans and invitations; ORM `db.delete(room)` cascades | Pass |
| Django-written rows read back through the new models (user, hashed room password, messages with reply, ban, invitation, membership, 3 friendships) | Pass |
| Settings: Secure cookies = `not DEBUG`; `RENDER_EXTERNAL_HOSTNAME` added to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`; `SESSION_ENGINE`, `STATIC_URL`, the channel-layer backend; engine is psycopg with `pool_pre_ping` | Pass |

### P2: auth, sessions, CSRF, middleware

| Check | Result |
|---|---|
| **Hashes vs Django's own code:** Django verifies ours, we verify Django's, same `pbkdf2_sha256$1200000$` format, byte-identical output for the same salt | Pass |
| Wrong, empty, `None`, unusable `!`, empty-hash, unknown-algorithm and garbage hashes rejected. An old-iteration (870,000) hash is accepted and the upgrade hook called; a current hash doesn't call it | Pass |
| `authenticate`: success, wrong password, missing args, inactive user, unknown user (and **the hasher still runs**, counted, so timing doesn't reveal usernames), old hash upgraded and committed | Pass |
| `SessionStore`: new, save (32-char key, ~2-week expiry), reload, `cycle_key` (old row deleted), `del` + save, `flush`, unknown key, expired row, tampered signature, garbage data | Pass |
| `login`: cycle when anonymous (data kept), key kept for the same user, flush for another user; sets `_auth_user_id`/`_auth_user_hash`, scope user, CSRF rotation flag, `last_login` committed. `get_user`: right user; password change → anonymous + flushed; deactivated → anonymous. `logout` | Pass |
| CSRF/host helpers: Origin exact, trusted, `https://*.` wildcard, wrong scheme, look-alike domains, foreign site; https Referer rules; `.example.com` matching; DEBUG localhost default; token format; cookie flags | Pass |
| `create_user`: `normalize_email` matches Django on 6 tricky inputs; NFKC username like Django; hash format; no password → unusable `!` hash; committed | Pass |
| **Middleware served by daphne:** anonymous visits get no cookies; 4 security headers; gzip only over 500 bytes; bad `Host` → 400 | Pass |
| CSRF end to end: missing/wrong token, foreign Origin, no cookie → JSON 403; matching → 200; an existing token is kept; token-less POST to an unknown URL → 403 (CSRF runs before routing) | Pass |
| Login cookie: HttpOnly, SameSite=Lax, 2 weeks, `Path=/`; CSRF rotated; `Vary: Cookie`; user persists; **503 → session not saved, 400 → saved** | Pass |
| WebSocket handshake loads `scope['user']` and a `SessionStore` from the cookie; unknown key → anonymous; no connection left "idle in transaction" | Pass |
| `require_POST_json` 405, `api_login_required` 401, router 404 and 405 (with `Allow`) as JSON; `@json_validation_errors` → 400 `{"errors"}`; an unmarked ValidationError → 500; DEBUG on → traceback, DEBUG off → JSON 500 | Pass |
| Logout deletes the cookie and the row; an unknown `sessionid` → anonymous and the cookie deleted (as Django does); a password change elsewhere signs the session out | Pass |
| `DEBUG=False`: `csrftoken` and `sessionid` are `Secure` | Pass |

### P3: HTTP controllers, SPA shell

| Check | Result |
|---|---|
| **SPA shell:** 200 HTML; `csrftoken` on a cold load; security headers; bootstrap JSON with `user: null`; `heroImage`, CSS and JS URLs carry `?v=` = the file's md5[:12]; no template tags left; `HEAD /` empty 200; `/dashboard`, `/login`, `/register`, `/room/ABC123` serve the shell | Pass |
| `tojson` escaping: rendered with a hostile `"</script><script>…&'` username, the block has no raw `</script`, `<`, `&` or `'` and decodes back | Pass |
| Static: 3 assets with exact bytes and content types; gzip; **ETag → 304**; `/static/nope.css` → JSON 404 | Pass |
| Catch-all: `/api/nope/`, `/media/x`, HTTP `/ws/notifications/`, `/api/friends/accept/abc/` → JSON 404. `/docs`, `/redoc`, `/openapi.json` 200. `/api/` → 307 `/api` (documented); **`/admin` → 307 `/admin/`** (P5); GET and POST slash redirects 307 | Pass |
| 401 / 403 / 405: anonymous `me` 401; token-less POST 403; `require_POST_json` 405; PUT → 405 with `Allow`; HEAD on API 405; POST to an SPA path → JSON 405 | Pass |
| **Auth:** per-field errors (empty, invalid username, short password, mismatch, bad email); success signs in (sessionid + CSRF rotated), email domain lowercased, 1.2M-iteration hash; "Already signed in." for register and login; bootstrap and `me` show the user; duplicate username → `errors.username`; logout; bad login `{"error"}`; empty login `{"errors"}` | Pass |
| **Friends:** GET send 400; empty, self and unknown refused; a valid send **and a Redis subscriber on `asgi__group__user_<id>` received the msgpack `friend_request_received`**; duplicate; both lists; the sender can't accept (404); GET accept 400; accept; "already friends"; reject (row deleted, repeat 404); remove (repeat 404); non-digit id 404 | Pass |
| **Rooms:** blank name → `errors.name`; capacity clamped (1→2, 500→100, "abc"→10); protected room saved with a hash; owner detail without the password; others get the "protected" 403; unknown → 404; join errors (empty, short, unknown, wrong password); lower-case code + padded password → 200 upper-case; detail after the grant; history oldest-first with the 3-key `reply_to`; "Room is full."; dashboard friend presence and own room | Pass |
| **Services + invitations:** non-friend, unknown, duplicate, already-in-room and banned errors; `get_pending_invitations` is a list; invitations API and dashboard list the invite; accept by the wrong user → None, by the receiver → code; reject unknown → False; reject → `declined`. An accepted invite admits **once** (row consumed), and a new session gets 403 again. A ban beats the grant and the password (403 on detail and join) | Pass |
| `DEBUG=False`: Secure `csrftoken` and `sessionid`; JSON 404 | Pass |
| **Cutover on the Django-filled DB:** a Django-era `sessionid` is signed out; logging in while holding it gives a new key and **deletes the old row**; Django users log in with their old passwords (email returned as stored); dashboard, history (reply preview, deleted flag) and invitations show the Django data; the Django-hashed room password works; the 870,000-iteration hash is upgraded; the Django ban is enforced; the inactive Django user is refused; new users work next to old data; **the Django superuser logs into the new `/admin/` with their old password** | Pass |
| No connection left "idle in transaction" (both DBs) | Pass |

### P4: realtime

| Check | Result |
|---|---|
| Handshake refusals (HTTP 403): anonymous notification socket; foreign, missing and `sub.localhost` Origin; unknown `/ws/` path. A `127.0.0.1` Origin is accepted | Pass |
| Close codes after accept, each after its `{"type":"error"}` frame with the exact text: 4003 anonymous, 4004 unknown room, 4003 protected without a grant, 4001 full, 4005 banned | Pass |
| Presence: `user_joined`, `active_users_updated` (owner flag), `room_info`; the membership row stores `asgispecific.<hex>`; others see the join with 2 users | Pass |
| Messages: send to both sockets + DB row; reply (3-key preview); reply to a missing message → error; edit own (**DB `edited_at` equals the broadcast value**); edit someone else's / a deleted one → error; delete → `message_deleted` + soft delete; delete again → error; reply to a deleted message → "This message was deleted." preview | Pass |
| Error frames: missing field, unknown type, non-JSON, blank content → `WSErrorEvent`; a valid but unregistered type on the chat socket is silently ignored | Pass |
| Owner controls: non-owner kick/transfer/delete → errors; kicking self ignored; kick or transfer of a non-member → error with no ban written; transfer → 3 events, DB owner updated, old owner loses rights; kick → target gets `user_kicked` then **4005**, others get `user_kicked_broadcast` + `active_users_updated` and **no** `user_left`, ban row with `banned_by`; rejoin → 4005; **5 kicks in a row all closed with 4005** (kick race); delete room → every member gets `room_deleted` + close 1000, DB emptied | Pass |
| `user_<id>` group: invite a non-friend → error; invite → `invite_sent` + `room_invitation_received`; duplicate → error; accept → `invite_response` with the code; accept again → "Invitation not found."; detail 200; chat socket admitted; **after leaving, detail 403 (grant revoked)**; reject → `declined`; invalid payloads → error | Pass |
| Last member leaves → room and messages deleted (also the 2-person full room) | Pass |
| **Two daphne processes on one Redis:** chat crosses :8765 ↔ :8768 both ways; a leave on :8768 is seen on :8765; a friend request made on :8765 reaches a notification socket on :8768 | Pass |
| Unknown event type sent through the layer → the consumer raises and the socket closes 1011 (the one intended ERROR in the log) | Pass |
| Hygiene: no membership rows left; no connection "idle in transaction"; Redis has no subscriptions except the crashed socket's room group (as in Channels; see below) | Pass |

### P5: admin

The full P5 admin script, rerun on its own fresh DB: **107/107**. It covers:
- **login:** staff + active in; non-staff, inactive, wrong password and unknown user refused; logout; un-staffing or a password change locks the admin out at once;
- **the admin cookie:** `admin_session`, path `/admin`, HttpOnly, SameSite=lax;
- **separation:** each way, between the admin login and the SPA login;
- **every view:** list columns and filters; create, edit and delete committed; a 6-char code for new rooms; details/edit pages including a reply's; no hash on any page; status dropdowns;
- **cascades:** for Room and User deletes;
- **CSRF:** Origin-only rule; `/api` CSRF unchanged;
- **routing:** shell, `/admin` redirects, static, `/docs`;
- **a WebSocket round trip.**

The server log had 0 ERROR lines.

### Chrome, real React bundle

User A was on `localhost:8765` and user B on `127.0.0.1:8765` (separate cookie jars, like a private window). Every step was confirmed on screen, and the DB steps were also checked in the DB.

1. Register both users through the UI.
2. A friend request arrives **live** (toast, bell badge, list); accept.
3. Protected room created (lock, owner crown, socket live).
4. B's pasted link is refused with "This room is protected…"; a wrong password gives "Incorrect room password."; the right one joins, and A sees B join live.
5. The dashboard shows the friend's current room.
6. Messages both ways; reply with a quoted preview; edit with an "edited" marker (`edited_at` in DB); delete shows "This message was deleted." (soft delete in DB). All live in the other tab.
7. Kick: B sees "You have been kicked from the room."; B's link then says "You have been removed from this room.".
8. Delete room through the in-app confirm dialog; A sees "This room has been deleted by the owner."; room, messages, ban and memberships are gone from the DB.
9. **Admin in B's browser:** log in as staff, open the Users list. The same browser stays `h_bo` in the SPA (`/api/auth/me/` 200), `admin_session` is not readable by JS, and admin logout leaves the SPA signed in.

Server log: 0 ERRORs. Recorded as `p0_p5_full_walkthrough.gif` (see "Where things are").

## Things noticed (not failures)

1. **Chrome screenshots timed out on freshly rendered pages.** The cause is three one-shot `rc-fade-up` CSS animations that never finish in an automation tab, so screen capture keeps waiting for them.
   - Finishing them (or pausing the room page's infinite one) through JS fixed it every time.
   - This is a tooling quirk, not an app bug: the animations are single-iteration and finish in a normal tab.
   - It probably also explains the P0–P3 run's dashboard screenshot timeouts, which that report blamed on the socket retrying.
2. **Known issue re-confirmed: orphaned membership.** When a consumer crashes (the intended unknown-type test), `disconnect()` never runs, so its `RoomMembership` row stays (P8 cross-references it).
3. **A crashed socket's room group stays subscribed in Redis** until the server process stops. This matches Channels' behaviour (P4 decision 7). Its own channel is cleaned up.
4. **The browser console check is weak.** It found no errors, but the extension only records messages from its first read onward, so errors from early page loads would not have been seen.
5. **The GIF hit the recorder's 50-frame cap**, so its last frames may not include the final admin steps. Those steps were still checked on screen and in the DB.

## Mistakes in my test scripts and steps (fixed and rerun; app code not touched)

- **Suite B:**
  - One label was wrong (it said "ban kept" while checking that deleting a room's owner deletes the room), and the "friendships" part of a check was vacuous (`>= 0`). Both were fixed and the suite rerun on a rebuilt DB.
  - On that rerun, my first `alembic upgrade` ran from `/tmp`, where `env.py` can't import the project, so the DB stayed empty. I reran it from the repo.
- **Suite C:** Django's user classes need the app registry. I added `django.setup()` with the two auth apps.
- **Shared HTTP client:** sent `password_confirm` instead of `confirm_password`. Fixed before Suite E ran.
- **Suite E cutover:** I replaced a fragile hand-built cookie-jar entry with an explicit `Cookie` header, before running.
- **Chrome:** my first "edit" attempt typed while a button still had focus. `Return` then pressed the focused **Reply** button, so a reply was posted instead (message 8, `reply_to` = message 6). I redid the edit by clicking into the input first. The accidental reply did confirm the reply feature.

## Not covered (by design or by choice)

- `roomchat/tests.py`: still the Django suite until P6.
- uvicorn, `render.yaml` and a real deploy (P7); `roomchat/cli.py createsuperuser` (P8).
- **Admin CSV/JSON export** was not exercised.
- **In the browser UI:** the invite flow, transfer ownership and the notification-socket buttons. These were tested at the socket level in Suite F, not by clicking.
- The known issues in `CLAUDE.md` §12 that need special conditions: a Redis outage, the capacity race, a same-user double connect.

## Where things are

- **Scripts and results** (temporary; copy the folder if you want to keep it): `/tmp/claude-1000/roomchat-test/`
  - `common.py`, `httpclient.py`, `mw_app.py`, `seed_django.py`, `env.sh`;
  - `suite_a.py` … `suite_g.py` (G is the P5 script from `/tmp/claude-1000/roomchat-p5/`, rewired to the shared recorder);
  - `results/A.json` … `results/H.json` (every check with pass/fail), and the daphne logs `daphne_*.log`.
- **Test accounts:** generated for this run and stored only in `django_seed.json` and `browser_creds.json` in that folder, plus `/tmp/claude-1000/roomchat-p5/creds.json` (admin). They existed only in the dropped scratch DBs.
- **Browser recording:** `/home/atharva/Downloads/p0_p5_full_walkthrough.gif` (50 frames).
