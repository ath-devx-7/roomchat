# Phase 4: Realtime

**Branch:** `migration` (on top of `0dac914`). **Status:** implemented and verified, **not committed** (your call). Scope is P4 only. Admin (P5), `roomchat/tests.py` (P6) and removing Channels/Django/daphne (P7) are untouched.

**What this phase is about.** Until now the WebSockets (live chat, presence, the notification socket) still ran on **Django Channels**. P4 replaces the two pieces of Channels the app uses with our own small module, `roomchat/realtime.py`:

- **The channel layer.** This is a message bus between sockets, built on Redis **pub/sub** (publish/subscribe: a sender publishes to a named channel, and every process subscribed to that name gets a copy; nothing is stored). Each socket has a private **channel** (its mailbox name). A **group** is a named set of channels, e.g. `room_ABC123` or `user_7`. Sending to a group reaches every socket in it, in every server process.
- **The consumer base class** (`AsyncWebsocketConsumer`). It holds one consumer object per open socket. It turns browser frames and layer messages into method calls (`receive()`, `message_created()`, …).

Think of it like a post office. Each socket has a P.O. box (its channel). Redis is the sorting centre between buildings (processes). A reader task in each building takes incoming mail and drops a copy into the right boxes.

`rooms/consumers.py` keeps its names, bodies and conventions. Only its imports, its ORM queries (rule 3) and the rule-5 merge lines changed.

## Files

| File | Change |
|---|---|
| `roomchat/realtime.py` | **New** (about 550 lines, mostly docstrings and comments). It contains:<br>• `RedisChannelLayer` + `get_channel_layer()`<br>• `database_sync_to_async`<br>• `AsyncWebsocketConsumer`<br>• `AllowedHostsOriginValidator`<br>Details below. |
| `rooms/consumers.py` | **Imports:** `realtime` replaces `channels`; `from roomchat import settings`; `User`, `_now` from `accounts.models`; `db`; the sqlalchemy names. `transaction` and `timezone` are gone.<br>**Queries** translated (table below), with `db.commit()` after each write (rule 2).<br>**Merge lines:**<br>• `self.room = db.merge(self.room, load=False)` at the top of the plan's 5 rule-5 helpers;<br>• in 4 helpers, `self.room` *and* `self.user` are merged (D-B below).<br>`get_room`, `is_member`, `revoke_room_grant` and every handler body are otherwise unchanged. |
| `rooms/routing.py` | **Rewritten.** `websocket_urlpatterns` holds two Starlette `WebSocketRoute`s, `/ws/chat/{room_code}/` and `/ws/notifications/`, each wrapped in `AllowedHostsOriginValidator`. |
| `roomchat/urls.py` | `include_urls(app)` adds `websocket_urlpatterns` just before the catch-all, with a comment on why the order is safe. |
| `roomchat/asgi.py` | **Removed** the temporary `DJANGO_SETTINGS_MODULE` bridge, its comment and `import os` (P3 open item 1). |
| `roomchat/settings.py` | `CHANNEL_LAYERS['default']['BACKEND']` → `'roomchat.realtime.RedisChannelLayer'` (P1 D1). CONFIG is unchanged. |
| `accounts/views.py` | One import line: `get_channel_layer` now comes from `roomchat.realtime`. The `async_to_sync(get_channel_layer().group_send)(…)` line is unchanged. |
| `reports/phase-4.md` | **New.** This report. |

Nothing imports `channels`, `channels_redis` or `django` any more, apart from the files P5–P8 own (`admin.py`, `apps.py`, `wsgi.py`, `tests.py`, `manage.py`, migrations). Verified by importing `roomchat.asgi` in a clean process: neither package ends up in `sys.modules`.

### What `roomchat/realtime.py` contains

- **`RedisChannelLayer(hosts, prefix='asgi')`.** Methods: `new_channel`, `send`, `receive`, `group_add`, `group_discard`, `group_send`, `flush`, plus `delete_channel` (D-D).
  - **Same wire format as channels_redis**, so old and new processes can talk during a deploy:
    - channel names `asgispecific.<hex>`;
    - group keys `asgi__group__<name>`;
    - plain `msgpack` payloads.
  - **One state object (`_LoopLayer`) per event loop:**
    - one Redis client (for publishing), one shared PubSub connection, the queues, the groups, a lock and the reader task;
    - **why per loop:** a Redis connection only works on the loop that opened it. daphne serves every socket from one loop, so they all share one connection. But `notify_friend_request` runs `async_to_sync(...)` from a worker thread, and asgiref gives that call its own short-lived loop;
    - the first use on any loop wraps its `close()`, so that loop's connections are closed before the loop is (same trick as channels_redis).
  - **The reader task:**
    - polls the PubSub connection every 0.1 s;
    - puts a copy of the raw bytes into the `asyncio.Queue` of the target channel, or of every local channel in the target group;
    - each socket decodes its own copy.
- **`get_channel_layer(alias)`:** imports the class named by `BACKEND` and creates it once with `CONFIG`. Returns `None` for an unknown alias, as Channels does.
- **`database_sync_to_async`:** a plain decorator. It runs the helper on a worker thread (`thread_sensitive=False`) inside its own `db` scope, using P2's `_in_own_db_scope`. The scope closes when the call returns.
- **`AsyncWebsocketConsumer`:**
  - `as_asgi()` returns a callable object, `_ConsumerApp`;
  - `__call__` copies Starlette's `path_params` to `scope['url_route']['kwargs']` and runs the one-at-a-time race loop;
  - `dispatch` maps `type` to a method name; a missing method raises `ValueError`;
  - `accept`/`send`/`close` work like Channels'.
- **`AllowedHostsOriginValidator`:** checks the Origin's hostname against `ALLOWED_HOSTS` (DEBUG + empty list → `localhost`, `127.0.0.1`, `[::1]`), using P2's `_is_same_domain`. A refusal closes before accepting, so the browser sees a failed handshake (HTTP 403).

### Query translations (rule 3, plus your P4 choices)

| Django (consumers.py) | SQLAlchemy |
|---|---|
| `.get(...)` in `try/except DoesNotExist` | `.one_or_none()` + `if … is None:` (same branch) |
| `.get(pk=self.room.pk)` with no `except` | `.one()`: still raises if the row is gone. The models have no `.pk`, so `Room.id == self.room.id` |
| `.filter(...).exists()` | `db.scalar(select(exists().where(...)))` |
| `.select_related('user'/'sender')` | `.options(joinedload(...))` |
| `.filter(...).delete()` | `db.execute(delete(...).where(...))` + `db.commit()` |
| `update_or_create` / `get_or_create` | select `.first()`, then update or `db.add(...)`, then commit |
| `.filter(room=…).count()` | `self.room.memberships.count()` (the dynamic relationship) |
| `.objects.create(...)` / `.save()` / `.delete()` | construct + `db.add` + `db.commit()` / `db.commit()` / `db.delete` + `db.commit()` |
| `with transaction.atomic():` (`ban_member`) | one block ending in a single `db.commit()`; an early `return` leaves without committing and the closed session rolls back |
| `is_deleted=False` | `Message.is_deleted == False` (same SQL `= false`; `# noqa: E712`) |
| `timezone.now()` | `_now()` |

## Decisions

**Decided by you**

1. **The bridge and the routes.**
   - The `DJANGO_SETTINGS_MODULE` line is removed.
   - The WebSocket routes are attached in `include_urls()`.
   - `accounts/views.py` switches the import (P3 open item 1).
2. **Layer config.** `get_channel_layer()` reads `BACKEND` and imports that class (P1 D1).
3. **DB scope** (P2). `database_sync_to_async` reuses `_in_own_db_scope`.
   - Consumers use the `scope['user']`/`scope['session']` the handshake middleware loaded; there is no second load at connect.
   - Each DB call has its own scope, closed straight away, so no connection is held while a socket is open. Verified: no "idle in transaction".
4. **Race:** one at a time, like Channels' `await_many_dispatch`. Handlers never overlap.
5. **Fan-out:** unbounded queue per socket, own copy of the bytes (rule 7: no backpressure).
6. **Reader lifetime:** stops, and closes the PubSub connection, when nothing is subscribed; restarts on the next subscribe.
7. **Exit cleanup:** like Channels. The socket's queue and its own channel subscription are removed when the consumer exits. Groups are left to `disconnect()`'s `group_discard`.
8. **Bulk delete:** one `DELETE` statement.
9. **`update_or_create`/`get_or_create`:** select, then add. Known edge: two tabs of the same user connecting at the very same instant can hit the unique constraint (Django retried). Same family as the accepted capacity race.
10. **`timezone.now()`** → `_now()`.
11. **Count:** `self.room.memberships.count()`.
12. **Origin check:** host patterns only.
13. **One Redis host.** More than one raises `ValueError`.
14. **Chrome test:** two hostnames instead of a private window.
15. **Kick race** (found in testing, see D-C): the base class drops `send()` after its own `close()`.

**Decided by me** (delegated to me, or small choices inside the plan you approved)

- **D-A, temporary loops** (you said "Let Claude decide"): hook `loop.close()`, as channels_redis does.
- **D-B, owner actions crashed** (you said "Let Claude decide"). The first scripted run failed with `Can't attach instance <User>; another instance with key (User, (1,)) is already present in this session`.
  - **Why:**
    - `self.user` is a **detached** object: it was loaded at the handshake by a scope that has since closed.
    - `get_room_info()` loads `self.room.owner`. For the owner, that's a second copy of the same user.
    - Building a row with both (`Message(room=self.room, sender=self.user)`) makes SQLAlchemy pull both into the new session, and it refuses the duplicate.
  - **Fix:** the 4 helpers that hand `self.room`/`self.user` to a new row (`create_membership`, `save_message`, `ban_member`, `create_room_invitation`) start by merging **both**. `ban_member` already merged `self.room` under rule 5.
  - This widens the plan's exact rule-5 list. The comment in `create_membership` explains it.
- **D-C, kick race** (you chose the fix). After `user_kicked` closes the kicked socket (4005), the same kick's `user_kicked_broadcast` arrives while the close handshake is still in progress. daphne's WebSocket library (autobahn) then raises `Disconnected`, and the consumer crashes before `disconnect()` runs.
  - **The race predates the migration.** Reproduced on the pure-Django commit `daf5322` (temporary worktree): 1 crash in 13 kicks.
  - **The new code hit it in 8 of 13.** Channels' `dispatch` makes a DB-cleanup thread hop (`aclose_old_connections`) before every handler, which happens to give the browser time to answer the close. P4's per-call DB scope made that hop unnecessary.
  - **Fix:** `send()` now does nothing once the consumer has closed. That's what daphne already does a moment later. After the fix: **0 crashes in 10 kicks**, and the kick checks pass.
- **D-D, `delete_channel()`.** channels_redis only cleans a socket's queue when its pending `receive()` is cancelled. A consumer that crashes *inside a layer-event handler* has no pending receive, so its queue and subscription leaked forever. The consumer's `finally` now calls an idempotent `delete_channel()`, the method channels_redis's own comment names as the future fix. This makes decision 7 behave as described in every case.
- `flush()` is kept on the layer because `roomchat/tests.py` (P6) calls it.
- `get_channel_layer()` caches one instance per alias at module level.
- `AllowedHostsOriginValidator` reads the settings when `rooms/routing.py` is imported, as Channels did.

## Verification

All runs used a scratch DB, `roomchat_t_p4`, built with `alembic upgrade head` and dropped afterwards. The dev DB `roomchat` was never connected to.

Setup:
- Redis was checked idle first: no subscribers, no dev server running.
- Two daphne processes ran on :8765 and :8766 (`DEBUG=True`, `ALLOWED_HOSTS=localhost,127.0.0.1`).
- The test client is a small stdlib WebSocket client, so nothing was installed.

**Scripted suite: 65/65.**

| Area | Checks | Result |
|---|---|---|
| Handshake refusals (HTTP 403, as before) | anonymous notification socket; foreign Origin; missing Origin; `sub.localhost` not allowed; unknown `/ws/` path. `127.0.0.1` Origin accepted | Pass |
| Close codes after accept | 4003 anonymous; 4004 unknown room; 4003 protected room without grant; 4001 full room; 4005 kicked user rejoining. Each one arrives after its `{"type":"error"}` frame with the exact text | Pass |
| Presence | `user_joined` → `active_users_updated` → `room_info` on connect; owner flag; membership row stores `channel_name` (`asgispecific.<hex>`); `user_left` + `active_users_updated` on leave | Pass |
| Messages | send; reply (with preview, to a missing message → error, to a deleted message → "This message was deleted." preview); edit own (DB `edited_at`), edit someone else's / a deleted one → error; delete → `message_deleted`, DB soft delete, delete again → error | Pass |
| Errors | missing field, unknown type, non-JSON, blank content → `WSErrorEvent`. A valid but unregistered type (`accept_room_invite` on the chat socket) is silently ignored | Pass |
| Owner controls | non-owner kick/transfer/delete → error; owner kicking self → ignored; kick or transfer of a non-member → error with no ban written; transfer → `ownership_transferred` + `room_info` + `active_users_updated`, DB owner updated, old owner loses rights; kick → `user_kicked` + close 4005 to the target, `user_kicked_broadcast` + `active_users_updated` to the rest, ban row (`banned_by` = owner), no duplicate `user_left`; delete room → every member gets `room_deleted` and close 1000, DB cascade empties messages, memberships, bans, invitations | Pass |
| `user_<id>` group | friend request sent by the **HTTP view** → `friend_request_received` on the socket; invite a non-friend → error; invite → `invite_sent` + `room_invitation_received`; duplicate → error; accept → `invite_response` accepted + code; accept again → "Invitation not found."; reject → declined (row marked `declined`, as Django did); invalid payloads on the notification socket → `WSErrorEvent` | Pass |
| Protected room by invite | accept → room detail 200 → socket admitted; after leaving, detail → 403 (grant revoked, admitted exactly once) | Pass |
| Last member leaves | room and its messages gone (also for the 2-person "full" room) | Pass |
| Two daphne processes, one Redis (plan check 10) | chat messages cross :8765 ↔ :8766 both ways; a friend request made via :8765 reaches a socket on :8766 | Pass |
| Connections | no Postgres connection "idle in transaction"; no membership rows left once every socket closed | Pass |

**Hygiene and internals: 12/12.**

| Check | Result |
|---|---|
| After every socket closed: Redis has no subscribed channels and no subscribing clients | Pass |
| Unknown event type (`group_send({'type': 'nope'})` from a script) → the consumer **raises** `ValueError: No handler for message type nope` (logged by daphne), and the socket closes (1011) | Pass |
| After that crash: its own channel is cleaned up (D-D); only its room group stays subscribed (decision 7, as in Channels); the membership row is orphaned because `disconnect()` never ran (the known issue P8 cross-references) | Pass |
| In-process run of the real app (asgiref `ApplicationCommunicator`): connect events and a message round trip through Redis. While open: 1 queue, 1 group, reader running. After close: **no queues, no groups, reader stopped, PubSub connection closed, no tasks left on the loop**; room deleted | Pass |
| `async_to_sync(group_send)` from a plain thread (how `notify_friend_request` runs): payload published as msgpack, and its temporary loop left nothing behind | Pass |
| No connection "idle in transaction" | Pass |

**Kick race comparison:** pure Django 1/13 crashes; P4 before D-C 8/13; P4 after D-C **0/10**. The daphne log of the final runs has exactly one ERROR: the intended unknown-type test.

**Chrome, real React bundle.** User A was on `localhost:8765` and user B on `127.0.0.1:8765` (separate cookie jars, like a private window). Recorded as `p4_realtime.gif`. Plan checks 2–7 all behaved live, with no refresh:

1. **Check 2:** friend request → bell badge, Activity count and the request appear on B's dashboard live.
2. **Check 3:** password room created. B pasting the room link → "This room is protected. Please join using the password on the dashboard." and back to the dashboard. Joining with the password works, and A's page shows B join live.
3. **Check 4:** send, edit ("edited" marker), reply (quoted preview), delete ("This message was deleted.") all appear live in the other tab.
4. **Check 5:**
   - kick → B sees "You have been kicked from the room." and the dashboard;
   - B's raw `new WebSocket(...)` back into the room → frame "You have been removed from this room." then **close code 4005 in the browser**;
   - transfer → "p4_ben is now the owner" and the crown moves;
   - B deletes the room → A sees "This room has been deleted by the owner.".
5. **Check 6:** an invite to a protected room arrives live; "Join room" admits B with no password.
6. **Check 7:** the last member leaves → the room, its messages and its ban are gone from the DB.
7. No console errors in either tab; 0 ERRORs in the daphne log; after closing both tabs Redis has no subscriptions left.

**Mistakes in my test scripts** (fixed and rerun; the app code was not changed for them):
- I expected `reject_room_invite` to delete the row. It marks it `declined`, exactly as the Django service did.
- The unknown-type check counted the error text twice per crash (the ERROR line plus the traceback).
- In Chrome, a few clicks by screen position missed after the window changed size. I switched to element references.

Cleanup: daphne stopped, both scratch DBs dropped (only `roomchat` remains), the `daf5322` worktree removed, Redis idle, Chrome tabs closed.

## Behaviour differences

- **`send()` after the consumer's own `close()` is dropped** (D-C). Channels would raise in that window. Users see no difference, except that the kick no longer occasionally leaves a crashed consumer behind.
- **DB calls from consumers run in parallel across sockets** (`thread_sensitive=False`, as the plan says). Channels pushed them all through one thread. Within one socket, handlers still run one at a time.
- **The reader task and the PubSub connection stop when nothing is subscribed** (decision 6). channels_redis kept polling forever.
- **One Redis host only; no encryption or serializer options**, and no `groups` class attribute or `AcceptConnection`/`DenyConnection`. Nothing in the project used them.
- **`as_asgi()` returns an object, not a function.** Starlette treats a plain function as `func(websocket)`.
- **Origin is checked per route, after routing.** An unknown `/ws/` path is refused at the handshake by Starlette (silently). Channels raised `ValueError: No route found` (logged). The browser sees a failed handshake either way.
- **Origin patterns:** hostnames only (decision 12). `ALLOWED_HOSTS` never held scheme or port patterns.

## Open items

1. **Orphaned memberships when a consumer crashes** (seen in the unknown-type test). `disconnect()` doesn't run, so the presence row stays. This is the existing `deploy-issues.txt` ISSUE 1; P8 cross-references it, not fixed here.
2. **`update_or_create`/`get_or_create` race** (decision 9). Two simultaneous connects by the same user to the same room can hit the unique constraint and close that socket. It's rare; Django retried.
3. **P5:** `greenlet` is still missing for sqladmin (P3 open item 2).
4. **P7:** `channels`, `channels_redis`, `daphne` and Django are still installed and pinned. Only `roomchat/tests.py` (P6) and the Django leftovers (P8) still import them.
5. **P6:** `roomchat/tests.py` still builds `channels_redis.pubsub.RedisPubSubChannelLayer` and asserts `get_channel_layer()` is one. P6 must switch it to `RedisChannelLayer`, which keeps `new_channel`/`receive`/`group_send`/`flush`.
6. **Still open from P2:** expired session rows are never deleted.
7. **Scripts and recording** (session scratch space, temporary; copy them to keep them): `/tmp/claude-1000/-home-atharva-projects-roomchat/d0813baa-dbbf-4516-ac84-ad92fb6b3963/scratchpad/p4/`
   - `wsclient.py`, `p4_ws.py`, `p4_hygiene.py`, `kick_repro.py`, `setup_db.py`, `start_daphne.sh`
   - The browser accounts are in `browser_creds_p4.json` (they existed only in the dropped DB).
   - `p4_realtime.gif` (50 frames) was exported through Chrome's download. As in the P0–P3 test run, it is **not** in `~/Downloads` on this machine, so check the download folder of the Chrome profile the extension uses.

## Manual browser checklist (for you, P4 surface only)

Start `daphne roomchat.asgi:application` (dev DB, `.env` as usual), with no other server using the same Redis. Open user A at `http://localhost:8000` and user B in a private window (or at `http://127.0.0.1:8000`).

1. A sends B a friend request: B's bell and request list update **without a refresh**. B accepts.
2. A creates a password room. B pastes the room link: B is sent to the dashboard with "This room is protected…". B joins with the password, and A sees B appear in Members live.
3. Chat both ways: send, edit, reply and delete each show up instantly in the other window.
4. A kicks B: B sees "You have been kicked from the room." B tries the link again and is refused. DevTools → Network → WS should show close code 4005, with no reconnect loop.
5. In a new room: A transfers ownership to B (the crown moves in both windows), then B deletes the room and A is sent out with "This room has been deleted by the owner.".
6. A invites B into a protected room from the room's Invite button: the invitation appears on B's dashboard live, and "Join room" admits B without a password.
7. Everyone leaves a room: rejoining its code says it doesn't exist.
8. The terminal running daphne shows no `ERROR` lines during all of the above.
