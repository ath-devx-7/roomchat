# Phase 5: Admin

**Branch:** `migration` (on top of `85dc858`). **Status:** implemented and verified, **not committed** (your call). Scope is P5 only. `roomchat/cli.py` (P8), `roomchat/tests.py` (P6), removing Django packages (P7) and the Django-only tables are untouched.

**What this phase is about.** Nothing had been mounted at `/admin` since P3, and `accounts/admin.py` / `rooms/admin.py` still imported Django. P5 moves the admin panel to **sqladmin** (an admin-panel library for SQLAlchemy models, served as a small Starlette app mounted at `/admin`). Each model gets a `ModelView`, sqladmin's equivalent of Django's `ModelAdmin`.

The admin has **its own login**:
- It uses the same password check as the SPA (`roomchat/auth.py`), but only **active staff** users get in.
- The login is kept in a separate signed cookie, so logging into the admin never logs you into the SPA, and the other way round.

## Files

| File | Change |
|---|---|
| `requirements.txt` | `+ greenlet==3.5.6`. sqladmin imports SQLAlchemy's asyncio module, which needs greenlet (a library that lets sync and async code hand control to each other). Without it, `import sqladmin` failed. |
| `accounts/admin.py` | **Rewritten** (Django imports gone).<br>• **`AdminAuth`** (sqladmin's `AuthenticationBackend`) has three methods:<br>  – `login` runs our `authenticate()`, refuses non-staff, and stores `user_id` + `auth_hash` (the password fingerprint from `get_session_auth_hash`);<br>  – `logout` clears the admin session;<br>  – `authenticate` runs on every admin page. It re-loads the user, who must still exist, be active and be staff, with an unchanged fingerprint; otherwise it clears the admin login.<br>• **`UserAdmin`** (new; Django's admin listed Users automatically).<br>• **`FriendshipAdmin`** (same class name and columns as before). |
| `rooms/admin.py` | **Rewritten.** Same four class names: `RoomAdmin`, `RoomMembershipAdmin`, `RoomInvitationAdmin`, `MessageAdmin`. RoomBan stays unregistered, as before. `MessageAdmin.details_query` preloads the replied-to message's sender (D-B below). |
| `roomchat/urls.py` | New `include_admin(app)`:<br>• builds `Admin(app, engine=engine, base_url='/admin', title='RoomChat admin', debug=settings.DEBUG, authentication_backend=AdminAuth(...))`;<br>• registers the 6 views;<br>• is called in `include_urls()` right **before** the catch-all, with a comment on why.<br>The catch-all regex changes from `admin/` to `admin(?:/|$)`, so bare `/admin` redirects instead of serving the shell. |
| `roomchat/middleware.py` | New `ADMIN_PATH_PREFIX = '/admin/'`. In `CsrfViewMiddleware.request_ok`, a branch for that prefix skips the token check and **requires** a matching `Origin` (or an https `Referer`). The class docstring gains one line saying so. |
| `CLAUDE.md` | Lines P5 made false were fixed (listed below). |
| `reports/phase-5.md` | **New.** This report. |

**`CLAUDE.md` lines fixed:**
- §2: the admin moved from "still legacy" to "already on the new stack".
- §4: "sqladmin/itsdangerous unused, greenlet missing" now says what they do.
- §5: both `admin.py` entries, plus `include_admin` in the `urls.py` entry.
- §7: new `/admin/...` URL bullet.
- §9 CSRF: the `/admin/` rule.
- §9 Routing: the order now includes the admin mount, and the new regex.
- §10: the "P5 admin" to-do list removed.
- §12: the "greenlet is missing" known issue removed.

### The views

The old `list_display` becomes `column_list` and `list_filter` becomes `column_filters`; the columns themselves are unchanged. sqladmin needs filter **objects**:
- a status column → `StaticValuesFilter(col, values=STATUS_CHOICES)`, which shows the choices like Django did;
- a boolean → `BooleanFilter`.

| View | List columns | Filters | Form fields |
|---|---|---|---|
| `UserAdmin` | username, email, first_name, last_name, is_staff (Django's UserAdmin) | is_staff, is_superuser, is_active (no Groups) | username, first/last name, email, is_active, is_staff, is_superuser, last_login, date_joined. **No password; create is off.** Search: username, names, email |
| `FriendshipAdmin` | sender, receiver, status, created_at | status | sender, receiver, status (dropdown) |
| `RoomAdmin` | name, room_code, owner, capacity, created_at | n/a | name, description, capacity, owner. **No room_code, no password** |
| `RoomMembershipAdmin` | user, room, joined_at | n/a | user, room, channel_name |
| `RoomInvitationAdmin` | sender, receiver, room, status, created_at | status | room, sender, receiver, status (dropdown) |
| `MessageAdmin` | sender, room, content, created_at, is_deleted | is_deleted | room, sender, content, reply_to, edited_at, is_deleted |

- **Details pages** show the model's own columns plus its forward FKs (FKs this model holds, like `Message.room`). Neither password hash is ever shown.
- **Form fields** follow what Django's form showed: no `id`, and no auto timestamps except User's `last_login`/`date_joined`, which Django's user form also had.

### Admin URLs after P5

| URL | What it does |
|---|---|
| `/admin` | 307 → `/admin/` |
| `/admin/` | Admin index. Signed out → 302 to `/admin/login` |
| `/admin/login` (GET, POST) | Login form |
| `/admin/logout` (GET) | Logs out, then → `/admin/login` |
| `/admin/<model>/list` | List page. `<model>` is `user`, `friendship`, `room`, `room-membership`, `room-invitation` or `message` |
| `/admin/<model>/create`, `/edit/<id>` | Create and edit forms (no create for `user`) |
| `/admin/<model>/details/<id>` | Details page |
| `/admin/<model>/delete?pks=<id>` (DELETE) | Delete (sent by sqladmin's JS) |
| `/admin/<model>/export/csv\|json` | Export of the list columns |
| `/admin/statics/*` | sqladmin's CSS/JS |

A trailing-slash form like `/admin/login/` gets 307 to `/admin/login`.

## Risks checked before designing

1. **Session collision: none.**
   - sqladmin adds Starlette's `SessionMiddleware` to **its own sub-app only**. Inside `/admin` that middleware replaces `scope['session']` with its own dict.
   - Our layer 5 keeps its own `SessionStore` reference and never re-reads `scope['session']` on the way out, so `sessionid` is never overwritten.
   - Verified: an admin login sets no `sessionid`, and an SPA login sets no `admin_session`.
2. **DB scope: works, and nothing leaks.**
   - sqladmin opens its own sessions and runs each create, edit or delete on a worker thread, ending in `commit()`.
   - Its create calls `Room()` there, so `Room.__init__` → `generate_room_code()` uses our `db`. anyio copies the request's context into that thread, so `db` is the request's session from layer 4. That request briefly uses one extra pooled connection, which `db.remove()` rolls back at the end.
   - Verified: 6-char codes, every write committed, no connection "idle in transaction".
3. **Mount order:** `Admin(...)` mounts itself as soon as it is built, so `include_admin()` runs before the catch-all is added. Route order is now `… /ws/…, /admin, /{path:spa}`.

## Decisions

**Decided by you**

1. **greenlet:** one exact pin, `greenlet==3.5.6`.
2. **CSRF** (you said "Let Claude decide"; I chose Origin-only on `/admin/`):
   - For `/admin/`, layer 7 skips the token check but requires a matching `Origin`, or a matching `Referer` over https. Neither → JSON 403.
   - **Why this is safe:** browsers always send `Origin` on form POSTs and on JS `DELETE` requests, and another site can't fake it. The admin cookie is also SameSite=Lax.
   - **What it leaves open:** only XSS (cross-site scripting: someone else's script running on our own pages). A token wouldn't stop that either.
   - **Side effect:** a tool that sends no `Origin` (e.g. plain `curl`) gets 403 on admin POSTs.
   - `/api/...` CSRF is unchanged.
3. **User view** (Let Claude decide): added, with **no password field** and create turned off.
   - **Why:** a raw password can't be saved because the field never exists.
   - **Side effect:** no password reset from the admin. Users come from sign-up, or from P8's `createsuperuser`.
4. **Permissions:** active + staff → full access to every view. A non-superuser staff user can do more than in Django, where they needed per-model permissions; nothing can assign those any more.
5. **Room form:** `room_code` and `password` both left out.
   - `Room()` generates the code.
   - A read-only widget was rejected: the browser still sends the field, and on create an empty box would overwrite the generated code.
6. **Form and details fields:** Django's editable fields, listed explicitly. sqladmin's defaults would also show reverse relations, and would crash on the dynamic `Room.memberships`.
7. **`/admin` → 307 → `/admin/`**, via the regex change.
8. **Admin session** (Let Claude decide): user id **plus password fingerprint**, re-checked on every request. Deactivating, un-staffing or changing the password locks the admin out at once.
9. **D-B, reply_to crash** (found during verification, your choice): preload the sender in `MessageAdmin.details_query`. Details below.

**Decided by me** (from the approved plan)

- **No new file.** `AdminAuth` lives in `accounts/admin.py`, and the `Admin(...)` wiring in `roomchat/urls.py`.
- **sqladmin gets `engine`, not `SessionLocal`.** sqladmin calls `.configure(autoflush=False)` on whatever sessionmaker it receives, which would change the app's own sessionmaker.
- **Admin cookie:**
  - named `admin_session`, with `path=/admin`, so the SPA's requests never carry it;
  - HttpOnly, SameSite=Lax, Secure when `SESSION_COOKIE_SECURE`;
  - 2 weeks, like `sessionid`;
  - signed with `SECRET_KEY`.
- **Status dropdowns:** the `status` form fields are dropdowns of `STATUS_CHOICES`, as in Django.
- **`title='RoomChat admin'`, `debug=settings.DEBUG`.**

**Found during verification and fixed** (the app code changed for these):

- **D-A: User details page returned 500.** My first `UserAdmin` excluded only the password from the details page, so the page still listed the user's reverse relations (friendships, rooms, …). sqladmin renders those with `str()` after its DB session has closed. `Friendship.__str__` reads `self.sender`, which can no longer load, so it raised `DetachedInstanceError` ("this object isn't connected to a DB session any more"). **Fix:** an explicit `column_details_list`, own columns only, matching decision 6.
- **D-B: Message details page of a reply returned 500.** It shows `reply_to` as `str(message)`, and `Message.__str__` reads `self.sender` (same detached problem). **Fix (your choice):** `MessageAdmin.details_query` adds `selectinload(Message.reply_to).selectinload(Message.sender)`. The page now shows "p5_staff: hello from admin" as Django did.

## Verification

Everything ran against a scratch DB, `roomchat_t_p5`, built with `alembic upgrade head` (`alembic check`: "No new upgrade operations detected.") and dropped afterwards.
- The dev DB `roomchat` was never connected to.
- Redis was checked idle first, and no dev server was running.
- Test users were made with `create_user` plus a direct `UPDATE` of `is_staff`/`is_active`.
- The app was served by `daphne -b 127.0.0.1 -p 8765 roomchat.asgi:application` (DEBUG on).
- The script imitates a browser: cookies kept, same-site `Origin`, and `X-CSRFToken` from the cookie for `/api` POSTs.
- **Every DB fact was checked over a fresh connection**, because sqladmin's delete endpoint swallows errors and still answers 200.

**Scripted suite: 107/107** on the final run (the first runs found D-A and D-B). The daphne log had 0 ERROR lines.

| Area | What was checked | Result |
|---|---|---|
| Install | `pip check` clean; `import sqladmin`; `import roomchat.asgi` loads no `django`/`channels` | Pass |
| Login | Signed out `/admin/` → 302 login. Staff + active → 302 `/admin/`, index 200. Non-staff, inactive staff, wrong password, unknown user → 400 "Invalid credentials." with no cookie | Pass |
| Admin cookie | `admin_session`: path `/admin`, HttpOnly, SameSite=lax, not Secure under DEBUG | Pass |
| Separation | Admin login → no `sessionid`, and `/api/auth/me/` → 401. SPA login → `/api/auth/me/` 200 but `/admin/` → 302 login, and no `admin_session` | Pass |
| Session checks | Un-staffing a logged-in user → locked out on the next request. Changing the password → both open admin sessions refused. Re-login with the new password works. Logout clears the cookie, and `/admin/` → login | Pass |
| Lists | Each of the 6 views is in the menu. Header columns exactly match the table above. Filter links present (is_staff/is_superuser/is_active, status ×2, is_deleted). `?is_deleted=true` and `?status=pending` really filter | Pass |
| Create | Room, Friendship, RoomMembership, RoomInvitation and Message (one with `reply_to` + `is_deleted`) all committed. **New Room: 6-char `[A-Z0-9]` code**, capacity and description saved, password `''`. User create page absent | Pass |
| Pages | Details and edit pages 200 for all 6 views, including a reply message. No `pbkdf2_sha256` hash on any details page. Room/User forms have no `password` or `room_code` field. Status is a `<select>` | Pass |
| Edit | Every view's edit committed. Room code unchanged after an edit. User edit leaves the password hash untouched | Pass |
| Delete | Friendship, Message, RoomMembership, RoomInvitation, Room and User deletes committed | Pass |
| DB cascades | **Room delete** removed its messages, memberships, bans and invitations. **User delete** removed their owned rooms, messages, friendships and memberships | Pass |
| CSRF | Admin POST and DELETE with the same Origin work. Foreign Origin → JSON 403 (POST and DELETE). No Origin → JSON 403. `/api/rooms/create/` without a token → JSON 403 `{"error": "CSRF verification failed."}`; with a token → 200 | Pass |
| Routing | `/admin` → 307 `/admin/`; `/admin/login/` → 307 `/admin/login`. `/`, `/dashboard`, `/room/ABC123`, `/adminx` → SPA shell. `/api/nope/` → JSON 404. `/api/auth/me` → 307. `/static/react/js/main.js` 200. `/admin/statics/*` 200. `/docs` 200 | Pass |
| WebSocket | `/ws/chat/<code>/` handshake 101; join events, then `send_message` → `message_created` | Pass |
| Hygiene | No Postgres connection "idle in transaction" (only idle pooled ones). Redis: no channels or subscribers left | Pass |

**Chrome, real browser** (recorded as `p5_admin.gif`, 34 frames, saved to `/home/atharva/Downloads/p5_admin.gif`):
1. `/admin` → login page.
2. Logged in as `p5_staff` → index with 6 models.
3. Browsed every list:
   - Users: no "New" button, 3 filters;
   - Friendships and Invitations: Status filter;
   - Messages: Is Deleted filter;
   - Rooms: shows the code.
4. Created "Chrome P5 Room". The form had no code or password field. The DB confirmed the row: code `YH48GL`, capacity 10, owner p5_staff, no password.
5. Deleted it through the in-page confirm box; it disappeared from the list and the DB.
6. Logged out → login page.

No ERRORs in the daphne log, and no connection "idle in transaction".

**Mistakes in my test script** (fixed and rerun; no app change for them):
- `pkill -f "daphne …"` matched my own shell command and killed it. I switched to a bracketed pattern.
- The socket check first ran *after* the script had changed `p5_staff`'s password. That correctly logged out the SPA session, so the socket was refused with 4003. The script now logs in again first.

Cleanup: daphne stopped, `roomchat_t_p5` dropped (only `roomchat` remains), Redis idle, the Chrome tab closed.

## Behaviour differences

- **Two separate logins.** In Django, the admin and the site shared one session: logging in at `/admin/` also logged you into the site, and vice versa. Now they are separate (the plan's "admin-only session").
- **The admin login doesn't update `last_login`.** Django's admin login called `login()`, which did. A hash with old iterations is still upgraded, since `authenticate()` does that.
- **`django_admin_log` is not written.** Django recorded every admin add/change/delete there ("Recent actions"). The table stays untouched, as the plan says.
- **Admin errors inside `/admin` are sqladmin's HTML pages** (e.g. its 404). CSRF failures there are still our JSON 403. The SPA's two JSON error shapes are unaffected.
- **New in the admin:** CSV/JSON export on every list, search on Users only, and "Save and continue editing / Save and add another" buttons.
- **Room code** is shown on the list and details pages, not on the edit form (Django showed it read-only on the edit form).
- **A failed admin delete still answers 200.** sqladmin puts the error in the redirect URL (`?error=…`) rather than the status code. Deleting a user who has rows in a Django-only table (`django_admin_log`, `auth_user_groups`, `auth_user_user_permissions`) would fail that way (already a known issue).
- **`/admin` (no slash)** now redirects to `/admin/`. Before P5 it served the SPA shell.

## Open items

1. **No way to create the first staff user yet.** User creation is off in the admin. Until P8's `roomchat/cli.py createsuperuser`, promote an existing user directly in the DB: `UPDATE auth_user SET is_staff = true WHERE username = '…'`.
2. **Same detached-`__str__` risk for future admin fields.** Any relationship added to a details page later must not rely on a `__str__` that reads another relationship, unless it is preloaded the way `MessageAdmin.details_query` does it.
3. **Optional CLAUDE.md additions** (not made, because P5 only fixes lines it made false):
   - the admin cookie and session rules;
   - "pass `engine`, never `SessionLocal`, to sqladmin";
   - the explicit-fields rule for admin views.
   Tell me if you want them in §9.
4. **Never-entered rooms:** a room created in the admin that nobody enters is never deleted. This is the existing known issue; cleanup only runs on socket disconnect.
5. **Still open from earlier phases:** expired sessions are never deleted; the capacity race; orphaned memberships; Redis-outage behaviour (P8 cross-references).
6. **Scripts** (temporary; copy them if you want to keep them), in `/tmp/claude-1000/roomchat-p5/`:
   - `env.sh`, `seed.py`, `p5_check.py`, `run3.txt` (final output), `daphne.log`;
   - the test accounts' passwords are in `creds.json` there (they existed only in the dropped DB).

## Manual browser checklist (for you, P5 surface only)

Make a staff user first: log in to the SPA once as a user, then `UPDATE auth_user SET is_staff = true WHERE username = '<you>';` on the DB you're using. Start `daphne roomchat.asgi:application` and open `http://localhost:8000`.

1. Visit `/admin`: you land on `/admin/login` with "Login to RoomChat admin".
2. Log in as a **non-staff** user: "Invalid credentials.". Log in as your staff user: the index shows Users, Friendships, Rooms, Room Memberships, Room Invitations and Messages.
3. In another tab, open `/dashboard` while signed out of the SPA: you're **not** signed in there. DevTools → Application → Cookies: `admin_session` has path `/admin`, and no new `sessionid` appeared.
4. **Users:** no "+ New" button; filters Is Staff / Is Superuser / Is Active; the details page shows no password.
5. **Rooms → + New Room:** the form has Name, Description, Capacity and Owner only. Save: the new room has a 6-character code in the list. Delete it with the trash icon; it's gone.
6. **Messages:** open a reply's details page. "Reply To" shows "sender: text", with no error page.
7. Click **Logout**: back to the login page. `/admin/` sends you to login again.
8. The daphne terminal shows no `ERROR` lines during all of the above.
