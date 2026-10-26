# Phase 1: Foundation

**Branch:** `fastapi-migration` (on top of `1e5af45`). **Status:** implemented and verified, **not committed** (your call). Scope is P1 only: deps, `roomchat/db.py`, the settings rewrite, the SQLAlchemy models (rule 4), and Alembic.

## Files

| File | Change |
|---|---|
| `requirements.txt` | +14 exact pins (below). Existing pins unchanged. |
| `roomchat/settings.py` | Rewritten as a plain module (see D1). |
| `roomchat/db.py` | **New.** `engine` (`postgresql+psycopg`, `pool_pre_ping=True`), `SessionLocal` (`expire_on_commit=False`), `Base`, `db_scope` ContextVar, `db = scoped_session(SessionLocal, scopefunc=db_scope.get)`. |
| `accounts/models.py` | `User` (`auth_user`, 11 columns, `Integer` PK, `is_authenticated`/`is_anonymous`, `__str__` → username), `Friendship`, plus the `django_session` `Table`. |
| `rooms/models.py` | `Room`, `RoomMembership`, `RoomBan`, `RoomInvitation`, `Message`, and `generate_room_code()` (query per rule 3). Code generation moved from `save()` to `Room.__init__` under `db.no_autoflush`. `memberships` is `lazy="dynamic"`. Names, docstrings, comments, `STATUS_CHOICES`, properties and `__str__` are kept. |
| `alembic.ini` | **New.** No URL in it; `env.py` builds it from settings. |
| `alembic/env.py` | **New.** Uses the app `engine`. `include_object` excludes the 8 Django-only tables. Supports online and offline modes. |
| `alembic/script.py.mako` | **New.** Alembic's stock template (see D8). |
| `alembic/versions/0001_baseline.py` | Added `upgrade()`/`downgrade()` and `TABLES`. `SCHEMA_SQL` is still byte-identical to the P0 dump (re-checked). |
| `alembic/versions/0002_fk_on_delete.py` | **New.** Recreates the 14 app FKs with `ON DELETE`. |

New pins (the 7 requested packages plus their required transitive deps; `pip check` is clean):

- Requested: `alembic==1.20.1`, `fastapi==0.162.0`, `itsdangerous==2.2.0`, `Jinja2==3.1.6`, `python-multipart==0.0.32`, `sqladmin==0.32.0`, `SQLAlchemy==2.1.6`
- Transitive: `annotated-doc==0.0.5`, `anyio==4.14.2`, `Mako==1.4.3`, `MarkupSafe==3.0.4`, `opentelemetry-api==1.45.1` (required by fastapi), `starlette==1.10.0`, `WTForms==3.2.2`

## Decisions

**Decided by you**

- **DB scope:** fail loudly. `db_scope` has no default, so using `db` outside an opened scope raises `LookupError`. P2's middleware, P4's `database_sync_to_async`, the CLI and the tests must each open a scope.
- **Models mirror the schema fully.** Every unique constraint, the `capacity >= 0` CHECK, every index (including `varchar_pattern_ops` `_like` indexes) and every FK carries Django's exact name. FKs also carry `DEFERRABLE INITIALLY DEFERRED` and their post-0002 `ON DELETE`.
- **`django_session` is defined now**, as a Core `Table` in `accounts/models.py` with its two Django indexes, so `alembic check` is clean. P2's `SessionStore` should use it.
- **`create_user`** is deferred to P3 (see Open items).
- **Verification ran on scratch DBs and on the dev DB.**
- **Pins:** exact, for the required deps only.
- **No commit.**

**Decided by me (delegated to me)**

- **D1, settings.**
  - Kept: `BASE_DIR`, `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, the `RENDER_EXTERNAL_HOSTNAME` block, `REDIS_URL`, `CHANNEL_LAYERS` (value unchanged; its `BACKEND` changes in P4 along with `realtime.py`), `STATIC_URL`, `STATICFILES_DIRS`.
  - `DATABASES['default']` keeps only `NAME/USER/PASSWORD/HOST/PORT`; `ENGINE`, `CONN_MAX_AGE` and `CONN_HEALTH_CHECKS` are replaced by `pool_pre_ping` (rule 1).
  - `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` are now always defined, as `not DEBUG`. The values are the same as before; P2's middleware reads them.
  - Added `SESSION_ENGINE = 'roomchat.sessions'`, which P4 depends on.
  - Dropped (Django machinery the plan replaces): `INSTALLED_APPS`, `MIDDLEWARE` (P2 hard-codes the order), `ROOT_URLCONF`, `TEMPLATES`, `WSGI_APPLICATION`, `ASGI_APPLICATION`, `AUTH_PASSWORD_VALIDATORS` (no app code calls `validate_password`; only Django's admin and createsuperuser did), `LANGUAGE_CODE`, `TIME_ZONE`, `USE_I18N`, `USE_TZ`, `STATIC_ROOT`, `STORAGES`, `LOGIN_URL`, `DEFAULT_AUTO_FIELD`.
  - Also dropped: `SECURE_PROXY_SSL_HEADER`. Proxy headers become the server's job (`--proxy-headers`, as the P7 start command already has).
- **D2, baseline `upgrade()`.**
  - Skips if `rooms_room` exists.
  - Otherwise it strips the `\restrict`/`\unrestrict` lines at runtime, so the constant stays verbatim.
  - Runs the SQL with `exec_driver_sql`, because `text()` would parse the dump's `::` casts as bind params.
  - Saves `search_path` beforehand and restores it afterwards, so the `alembic_version` write works.
- **D3, baseline `downgrade()`** drops all 16 tables in one statement. ⚠ On an adopted (prod) DB, `alembic downgrade base` therefore deletes all data.
- **D4, 0002.**
  - Keeps Django's hashed names (looked up via the inspector) and `DEFERRABLE INITIALLY DEFERRED`, so `ON DELETE` is the only change.
  - SET NULL applies to `rooms_message.reply_to_id` and `rooms_roomban.banned_by_id`; every other FK is CASCADE.
  - `downgrade()` recreates the FKs without `ON DELETE`.
  - FKs on the Django-only tables are untouched, per the plan.
- **D5, relationships.**
  - Reverse accessors are declared with `backref` at the FK side, under Django's `related_name`, so `user.owned_rooms`, `room.messages` and so on keep their names.
  - CASCADE collections use `cascade='save-update, merge, delete'` with `passive_deletes=True`: loaded children are deleted by the ORM, unloaded ones by the DB, and neither is ever nulled.
  - SET NULL collections (`replies`, `bans_issued`) keep the default cascade with `passive_deletes=True`.
- **D6, defaults** are Python-side only (`default=`) and match Django's field defaults. `auto_now_add` and `date_joined` use `_now()` (aware UTC), defined in `accounts/models.py` and imported by `rooms/models.py`.
- **D7:** `Message` has no default ordering (rule 3).
- **D8:** added `alembic/script.py.mako`. It isn't in the plan's file list, but `alembic revision` (autogenerate, which `include_object` exists for) can't run without it.

## Verification

| Check | Result |
|---|---|
| Empty scratch DB → `alembic upgrade head`, then `pg_dump` diffed against P0 (`\restrict` lines ignored) | Only differences: the 14 `ON DELETE` clauses and the `alembic_version` table. |
| `alembic check` (empty DB and dev DB) | "No new upgrade operations detected." |
| `downgrade 0001_baseline` | Schema equals P0, apart from `alembic_version`. |
| `downgrade base` → `upgrade head` | All tables dropped, then rebuilt identically. |
| Scratch DB migrated by Django from `main` (temporary worktree, seeded via the Django ORM) → `upgrade head` | Baseline skipped; schema identical to the empty-DB head. |
| ORM smoke test on that DB | Pass: `LookupError` without a scope; Django-written rows read back (pbkdf2 hash intact); defaults; 6-char room code; dynamic `memberships.count()`/`is_full`; `reply_to` and `banned_by` SET NULL; room delete cascades to memberships/bans/invitations/messages; user delete cascades to friendships and owned rooms. |
| Dev DB `roomchat` | Backed up first, then `upgrade head`: baseline skipped, 0002 applied, schema equals the expected head. Row counts unchanged (1 user, 1 session). |

The scratch DBs and the worktree have been removed. The dev DB backup is at `/tmp/claude-1000/-home-atharva-projects-roomchat/3b2c533a-5778-447c-b0a0-0126277eb221/scratchpad/roomchat_dev_before_p1.dump` (`pg_restore` format). It's session scratch space, so copy it elsewhere if you want to keep it. `alembic downgrade 0001_baseline` alone reverts the FKs.

## Open items (yours to decide)

1. **`User.objects.create_user`** (`accounts/views.py:72` plus 12 calls in tests) has no replacement in the plan yet. Decide before P3.
2. **Defaults apply at flush, not at construction.** For example, `Room(...).capacity` is `None` until the object is added and flushed, whereas Django set it immediately. Worth checking any P3 view that reads a field before saving.
3. **The branch can't serve the app until P3–P6.** Views, consumers, admin and tests still use the Django ORM and `django.contrib.auth.models.User`. `manage.py check` passes only because `INSTALLED_APPS` is gone.
4. **Some Django-only FKs block user deletes.** Besides `django_admin_log` (already in the plan's known consequences), `auth_user_groups` and `auth_user_user_permissions` also reference `auth_user` without `ON DELETE`. Deleting a user who has rows there would fail. Only Django admin's group and permission assignments ever wrote those rows.
5. `.env.example` / README are not updated; that's P8, per the plan.
