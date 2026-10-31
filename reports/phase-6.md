# Phase 6: Tests

**Branch:** `migration` (on top of `b13f870`, "phase 05 completed"). **Status:** implemented and verified, **not committed** (your call). Scope is P6 only. No app code changed. Removing Django/Channels/daphne (P7) and the Django leftovers, README, `.env.example` and `roomchat/cli.py` (P8) are untouched.

**What this phase is about.** `roomchat/tests.py` was still the Django + Channels suite (55 tests), so it couldn't run any more. P6 ports it to:
- **pytest**: a test runner that finds `test_*` functions and runs them;
- **pytest-asyncio**: a plugin that lets pytest run `async def` tests.

Every test keeps its class, its name and what it checks. Only the parts tied to Django changed: DB setup, HTTP calls, socket driving and the assertion syntax. Think of it as moving house: same furniture (the tests), new building (pytest), so only the plugs changed.

## Files

| File | Change |
|---|---|
| `roomchat/tests.py` | **Rewritten in place.** The top sets the test env, then defines the fixtures and helpers (below); the 12 classes and 55 tests follow with their old names. Nothing in it imports `django`, `channels` or `channels_redis` (checked with grep). |
| `pytest.ini` | **New.** `testpaths = roomchat`, `python_files = tests.py`, `python_classes = *Tests`, `asyncio_mode = auto`, and both asyncio loop scopes set to `function`. |
| `requirements-dev.txt` | **New.** `-r requirements.txt` plus 9 exact pins: `pytest==9.2.0`, `pytest-asyncio==1.4.1`, `httpx2==2.16.0`, and what they pull in: `httpcore2==2.16.0`, `h11==0.16.0`, `truststore==0.10.5`, `iniconfig==2.3.1`, `pluggy==1.7.0`, `Pygments==2.21.0`. Render installs only `requirements.txt`, so it never gets these. |
| `CLAUDE.md` | Lines P6 made false were fixed (listed below). |
| `reports/phase-6.md` | **New.** This report. |

**`CLAUDE.md` lines fixed:**
- §2: tests moved from "still legacy" to "already on the new stack".
- §4: the "still installed" reason no longer names `tests.py`; new bullet for the test tools.
- §5: the `tests.py` entry.
- §8: the Tests command.
- §10: the P6 summary says `httpx2`; the "P6 tests" to-do block is removed (all done).

### What's at the top of `roomchat/tests.py`

A **fixture** is like a `setUp()` that pytest hands to any test (or other fixture) that names it as an argument. The code after its `yield` is its tearDown. `autouse=True` means pytest runs it for every test without being asked.

- **Env lines, before any project import.** `DB_NAME` becomes `test_<DB_NAME>` (from env or `.env`), plus `DEBUG=True`, `ALLOWED_HOSTS=127.0.0.1` and `CSRF_TRUSTED_ORIGINS=''`.
  - Why first: `roomchat/db.py` builds the engine at import time.
  - A guard then refuses to run unless the engine really points at a `test_` DB.
- **`_test_database`** (session scope = once per whole run, autouse).
  - First, a Redis preflight: it stops the run if Redis is unreachable or anything is subscribed to `asgi*` (a dev server is listening).
  - Then it drops a stale `test_roomchat`, creates it fresh, and runs `alembic upgrade head`, so the real migrations (including the `0002` cascades) build the schema.
  - At the end: `engine.dispose()`, then a plain `DROP DATABASE` without FORCE, so a leaked connection would make it fail loudly.
- **`_db_scope`** (per test, autouse).
  - It opens a `db` scope for the test and its setUp.
  - Afterwards it closes the test's session first, then runs `TRUNCATE <every table in Base.metadata> RESTART IDENTITY CASCADE`. That one statement empties every app table plus `django_session`, resets the id counters to 1, and follows FKs.
  - `alembic_version` isn't in the metadata, so it's never touched.
  - Why not roll back instead: the app and the consumers commit over their own connections.
- **`RoomChatClient`** + the **`client`** fixture. `TestClient` is Starlette's fake browser: it calls the app in-process, with no server. Ours adds:
  - `base_url = http://127.0.0.1`;
  - one `GET /` to prime the `csrftoken` cookie;
  - before every unsafe request, the **current** cookie copied into `X-CSRFToken`, plus `Origin: http://127.0.0.1`, exactly like `api.js`;
  - `.session`: a `SessionStore` for the `sessionid` cookie, like Django's `client.session`;
  - `force_login(user)`: writes a logged-in session row and puts its key in the cookie.
- **`WebsocketCommunicator`**. It has the same method names as Channels' version: `connect`, `send_json_to`, `receive_json_from`, `receive_output`, `disconnect`.
  - It's built on asgiref's `ApplicationCommunicator`, a tool that runs an ASGI app in-process and lets the test push messages in and read what the app sends out.
  - The app it drives is `starlette.routing.Router(websocket_urlpatterns)`, the equivalent of Channels' `URLRouter`.
  - The scope carries `Origin: http://127.0.0.1` by default, so `AllowedHostsOriginValidator` lets it through.
  - Tests still put plain dicts into `scope['user']` / `scope['session']`.
- **`create(Model, **fields)`**: add + commit + return, the stand-in for `Model.objects.create()`.

## Decisions

**Decided by you**

1. **Dev deps** live in `requirements-dev.txt`, so Render doesn't install them.
2. **`httpx2`**, not `httpx`. Starlette 1.10's TestClient looks for `httpx2` first and warns that plain `httpx` is deprecated. I found this while researching.
3. **Latest pins:** pytest 9.2.0, pytest-asyncio 1.4.1.
4. **Setup lives at the top of `tests.py`** (plan + your file list), not in a `conftest.py`, with the `test_` guard.
5. **Layer config tests** (Let Claude decide): a 1:1 port.
   - `test_configured_backend_is_redis_pubsub` asserts the BACKEND string is `roomchat.realtime.RedisChannelLayer` and that `get_channel_layer()` is one.
   - `test_config_omits_options_the_pubsub_layer_ignores` asserts `hosts == [REDIS_URL]` and that none of `capacity` / `expiry` / `group_expiry` are in CONFIG.
   - This closes P4 open item 5.
6. **Middleware + decorator tests** (Let Claude decide): the middleware is driven as an ASGI app around a fake inner app that raises.
   - "Ignores" now means the exception passes straight through (`pytest.raises`). That's the same meaning as Django's `process_exception` returning None.
   - "Opted in" means a 400 start message and a body containing `"errors"`.
   - The decorator test uses a real Starlette `Request` and checks `request.state`.
7. **No CSRF rejection test**; every request sends a valid token, so the count stays 55.
8. **Event loops** (Let Claude decide): function scope. Each async test gets a fresh loop, and P4's close hook flushes that loop's Redis connections.
9. **Plain pytest classes + `assert`.**
10. **Test DB:** recreate a stale one at start; plain drop at the end.
11. **Test settings pinned:** DEBUG, hosts and trusted origins (decided by you). Credentials and REDIS_URL still come from `.env`.
12. **Redis guard** (Let Claude decide): the preflight check.
13. **setUp** (Let Claude decide): each class's `setUp` is now an autouse fixture method, `setUp(self, client)`, which stores `self.client`. All `self.client...` lines are unchanged.
14. **ORM lines:** the `create()` helper. Exists checks are inline as `db.scalar(select(exists().where(...)))`, and users come from `roomchat.auth.create_user`.
15. **Django async ORM** (Let Claude decide): plain sync calls inside the async tests. The consumer is idle at those moments.
16. **`force_login`** (Let Claude decide): writes `_auth_user_id` / `_auth_user_hash` (the constants from `roomchat/auth.py`) into a `SessionStore` and saves it.
17. **Merge crash found while porting** (Let Claude decide → fix the test, log the trap). See "Found during verification" below.

**Decided by me** (forced by the decisions above)

- `python_classes = *Tests`: pytest only collects `Test*` classes by default, and the old names end in `Tests`.
- `test_client_routes_serve_the_shell` keeps its 4-path loop in one test (Django's `subTest`), so the count stays 55. Each assert message names the path. `parametrize` would have made it 4 tests.
- `assertContains(r, text)` → `assert r.status_code == 200` + `assert text in r.text`, because Django checked the status too. `assertNotContains(..., status_code=403)` → a status assert + `not in`.
- **Host `127.0.0.1`, not `localhost`:** Python's cookie jar files `localhost` cookies under `localhost.local` (checked). A cookie set by hand in `force_login` would then sit next to the server's copy instead of replacing it.
- `client.post(url, {...})` → `client.post(url, data={...})`. httpx's `post` takes `data` only as a keyword argument. Sending it this way gives a form-urlencoded body, like `api.js` (Django's client sent multipart).
- `connect()` / `receive_*()` keep Channels' default 1 s timeouts.
- The anyio warning (below) is **not** filtered in `pytest.ini`.

**Found during verification**

- **Merge trap (latent; the app doesn't hit it today).** The first run had 53 passed and 2 failed (`RoomBanTests::test_owner_cannot_be_banned`, `::test_ban_member_removes_presence_and_records_the_issuer`).
  - Error: `AttributeError: '_DynamicCollectionAdapter' object has no attribute 'append_without_event'`, raised by `db.merge(self.room, load=False)` in `ban_member`.
  - Cause: the port created the membership with `room=self.room`. SQLAlchemy then also marks the room's `lazy="dynamic"` `memberships` collection as changed (checked: `'memberships' in room.__dict__` flips to True), and `merge(load=False)` can't copy a dynamic collection. Django's `acreate` never touched `self.room`.
  - In the app, `create_membership` marks `self.room` the same way, but inside `connect()` `get_room_info` swaps in a freshly loaded room before any other merge runs. So nothing reachable crashes today.
  - Fix (your call): those 2 setup lines now create the membership with FK ids (`room_id=…, user_id=…`), with a comment. No app change. The trap is in Open items.

## Verification

Preconditions: no daphne running, Redis had no `asgi*` subscriptions, and P5 was committed (`b13f870`).

| Check | Result |
|---|---|
| `pip install -r requirements-dev.txt`: `pip freeze` diff shows exactly the 9 new packages; `pip check` clean | Pass |
| Collected tests: **55**. Names diffed against `git show HEAD:roomchat/tests.py` (class::test, parsed with `ast`) | **Identical** |
| Full suite, 3 runs in a row | Run 1: **55 passed**, 13.54 s. Run 2: **55 passed**, 13.58 s. Run 3: **55 passed**, 13.87 s. Each with 1 warning (anyio, below) |
| Test DB: a watcher saw `test_roomchat` exist during each run; after each run it was gone | Pass (3/3) |
| Final DROP is a plain `DROP DATABASE` (no FORCE), and it succeeded every time, so no connection of any state was left open at the end. `pg_stat_activity` "idle in transaction" after each run: 0 | Pass |
| Redis after each run: no `asgi*` channels, 0 pattern subscriptions | Pass |
| **Dev DB `roomchat` never touched.** During a full run I polled `pg_stat_activity` every ~50 ms: 0 connections to `roomchat`, and its `xact_commit` counter was unchanged (250 → 250). Row counts before/after the whole session were identical (auth_user 1, django_session 1, rest 0) | Pass |
| Redis guard: with `REDIS_URL` on a closed port → stops before any test with "Redis is not reachable … Start Redis first." (exit code 1). With a fake listener on `asgi__group__user_1` → "already has 1 asgi* subscriptions: a dev server seems to be using it." No test DB was created in either case | Pass |
| `import roomchat.asgi` loads no `django`/`channels`/`channels_redis`; `tests.py` imports none of them (grep) | Pass |
| After the mutations were reverted: full suite **55 passed**; `git status` shows only `roomchat/tests.py`, `pytest.ini`, `requirements-dev.txt` (plus this report and the local CLAUDE.md) | Pass |

One honest caveat: a coarse before/after of the dev DB's commit counter over the *whole session* showed +10. My own read-only `psql` connections add 2 each, and I couldn't attribute the rest exactly (Postgres also counts autovacuum work). The per-run measurement above is the conclusive one: 0 connections, +0 commits.

### Mutation checks (do the tests really test something?)

For each check, I copied the file to `/tmp/claude-1000/roomchat-p6/mut/`, made one exact change, ran the full suite, then copied the original back and compared sha256. All 5 were restored byte-identical.

| # | What I broke | File | Result | Tests that failed |
|---|---|---|---|---|
| 1 | Ban gate: the ban check in `room_detail_api` turned off (`if False and …`) | `rooms/views.py` | 1 failed, 54 passed | `RoomBanHTTPGateTests::test_accepted_invitation_does_not_override_a_ban` |
| 2 | Accept-before-close: `reject()` closes first, then accepts | `rooms/consumers.py` | 4 failed | `ChatConsumerPasswordGateTests`: `test_user_without_grant_is_rejected`, `test_accepted_invite_alone_is_rejected`, `test_grant_for_another_room_is_rejected`, `test_banned_user_is_refused_despite_a_valid_grant` |
| 3 | CSRF: the token comparison refuses correct tokens | `roomchat/middleware.py` | 7 failed | `RoomDetailGateTests`: `test_correct_password_mints_grant_and_admits`, `test_bare_code_with_empty_password_is_rejected`; `ApiAuthTests`: `test_register_signs_the_user_in`, `test_register_reports_field_errors`, `test_duplicate_username_is_a_field_error`, `test_login_and_logout_round_trip`, `test_bad_credentials_do_not_say_which_half_was_wrong` |
| 4 | Room cascade: no `ON DELETE CASCADE` on `rooms_roomban.room_id` | `alembic/versions/0002_fk_on_delete.py` | 1 failed | `RoomBanHTTPGateTests::test_deleting_the_room_cascades_the_ban` |
| 5 | Layer `group_send` publishes to the wrong Redis key | `roomchat/realtime.py` | 6 failed | `RedisChannelLayerTests`: `test_group_send_crosses_layer_instances`, `test_group_send_reaches_every_subscriber`, `test_pydantic_event_survives_the_round_trip`; `NotificationConsumerCrossProcessTests::test_friend_request_reaches_socket_from_another_layer_instance`; `ChatConsumerPasswordGateTests`: `test_owner_bypasses_password`, `test_matching_grant_is_admitted` |

**Correction to my plan:** I predicted that mutation 1 would also fail `test_banned_user_is_refused_and_leaks_no_history`. It doesn't.
- The test room is password-protected, so the password gate returns the same 403 even without the ban check.
- The `join_room` test has its own, separate ban check.
- Only the invitation-path test catches a missing `room_detail_api` ban check (see Open items).

Mutation 3 only shows that the client really sends tokens and that the check runs. Breaking CSRF the *other* way (accepting everything) would go unnoticed; that's decision 7's known gap.

## Behaviour differences (test suite vs the Django one)

App behaviour is unchanged; these differences are in how the tests run.

- **Isolation by TRUNCATE**, not per-test transactions. Ids restart at 1 in every test (`RESTART IDENTITY`); Django's TestCase didn't reset them. No test depends on specific ids.
- **CSRF is enforced in every test.** Django's test client skipped it. Ours sends a real token, like the SPA.
- **Form bodies are urlencoded** (like `api.js`); Django's client sent multipart.
- **Test settings are pinned** (DEBUG, hosts, trusted origins), whatever `.env` says. The test DB is `test_<DB_NAME>`, i.e. `test_roomchat`, as you specified; that differs from CLAUDE.md's `roomchat_t_*` naming for scratch DBs.
- **Each async test gets its own event loop.** Channels' tests shared Django's async test machinery.
- **The suite refuses to start** if Redis is down or a dev server is listening on it. Before, a busy Redis gave confusing cross-talk.

## Open items

1. **Merge trap** (found above). `db.merge(room, load=False)` crashes on a room whose dynamic `memberships` collection was changed in memory (e.g. by `RoomMembership(room=room)`). The app is safe today only because `get_room_info` replaces `self.room` right after `create_membership`. Fixing it is an app change; if you want one, possible fixes include taking `merge` out of that relationship's cascade or reloading instead of merging. Optional: add it to CLAUDE.md §12. Tell me if you want either.
2. **Ban gate covered by only one HTTP test** (mutation 1). A test on an *open* room would also catch a missing ban check. I didn't add one, because you asked for the same 55 tests.
3. **No test proves a missing or wrong CSRF token is refused** (decision 7). P2–P5's scripts checked it; the suite doesn't.
4. **anyio warning:** `PytestRemovedIn10Warning: _pytest.python.CallSpec2 has been renamed to CallSpec`. It comes from anyio 4.14.2's own pytest plugin, which loads automatically, not from our code. It's harmless until pytest 10. A later anyio release should fix it; I didn't filter or upgrade anything.
5. **P7:** the tests no longer import Django or Channels, so P7 can uninstall them. `requirements-dev.txt` starts with `-r requirements.txt`, so it follows P7's changes automatically.
6. **Still open from earlier phases:** expired sessions are never deleted; the capacity race; orphaned memberships; Redis-outage behaviour; the never-entered-rooms issue.
7. **Scripts** (temporary, outside the repo; copy them if you want to keep them), in `/tmp/claude-1000/roomchat-p6/`:
   - `pgenv.sh`: loads the DB credentials from `.env` without printing them;
   - `devdb_snapshot.sh`, `devdb_before.txt`, `devdb_after.txt`: the dev DB checks;
   - `redis_subs.py`: the Redis subscription check;
   - `mutate.py` and `mut/`: the mutation checks and their backups;
   - `old_names.txt`, `new_names.txt`: the name diff;
   - `freeze_before.txt`, `freeze_after.txt`: the package diff.

## How to run the tests yourself

1. **Once:** `.venv/bin/pip install -r requirements-dev.txt`
2. Make sure Postgres and Redis are up, and **stop daphne** if it's running, because the suite refuses to share Redis with it.
3. From the repo root, run `.venv/bin/pytest`. Useful variants:
   - `.venv/bin/pytest -q`: compact output;
   - `.venv/bin/pytest -k RoomBan`: only tests whose names match;
   - `.venv/bin/pytest roomchat/tests.py::ApiAuthTests::test_login_and_logout_round_trip`: one test.

**What passing looks like** (about 14 s):
```
============================= test session starts ==============================
configfile: pytest.ini
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, ...
collected 55 items

roomchat/tests.py .......................................................  [100%]

=============================== warnings summary ===============================
.venv/lib64/python3.14/site-packages/anyio/pytest_plugin.py:14
  ... PytestRemovedIn10Warning: _pytest.python.CallSpec2 has been renamed to CallSpec.
======================== 55 passed, 1 warning in 13.68s ========================
```
The one warning is the anyio one (Open item 4). A failure shows an `F` in the dots, and a "FAILED roomchat/tests.py::Class::test - reason" line at the end.

**If something is wrong before any test runs:**
- **Redis not running:** `Exit: Redis is not reachable at redis://127.0.0.1:6379/0 (… Connection refused.). Start Redis first.` Start Redis (e.g. `sudo systemctl start redis` / `valkey`) and rerun.
- **A dev server is using Redis:** `Exit: Redis at … already has N asgi* subscriptions: a dev server seems to be using it.` Stop daphne and rerun.
- **Postgres errors** (e.g. "role does not exist" or "permission denied to create database"): the user in `.env` must be able to connect to the `postgres` database and run `CREATE DATABASE`.
- **"database test_roomchat is being accessed by other users" at the end:** something kept a connection open, e.g. a `psql` you left connected to `test_roomchat`. Close it. The next run drops and recreates the DB anyway.
