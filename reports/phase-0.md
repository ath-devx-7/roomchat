# Phase 0: Capture the schema

**Branch:** `fastapi-migration` (created from `main` @ `daf5322`). **Scope:** P0 only. No application code, dependencies or Django migrations were touched.

## What was done

1. Created a throwaway database `roomchat_p0_capture` on the local Postgres 18.6.
2. Ran `DB_NAME=roomchat_p0_capture python manage.py migrate --noinput` while Django was still the framework. Every migration applied cleanly: `contenttypes`, `auth` (0001–0012), `accounts.0001`, `admin` (0001–0003), `rooms` (0001, 0002_roomban), `sessions.0001`.
3. Ran `pg_dump --schema-only --no-owner -d roomchat_p0_capture` (pg_dump 18.6). The output is 1048 lines.
4. Put the dump, **unmodified**, into `alembic/versions/0001_baseline.py` as the raw-SQL constant `SCHEMA_SQL`. A check confirmed that the embedded string is byte-identical to the dump.
5. Dropped `roomchat_p0_capture`. The dev DB `roomchat` was not touched.

## Files

| File | Change |
|---|---|
| `alembic/versions/0001_baseline.py` | **New.** Docstring, Alembic revision IDs (`0001_baseline`, `down_revision = None`) and `SCHEMA_SQL = r"""<dump>"""`. |
| `reports/phase-0.md` | **New.** This report. |

The pre-existing local changes to `.env.example` and `changes.md` were left as they were and are not part of the P0 commit.

## What the baseline contains

- **16 tables.**
  - App tables: `auth_user`, `accounts_friendship`, `rooms_room`, `rooms_message`, `rooms_roommembership`, `rooms_roominvitation`, `rooms_roomban`, `django_session`.
  - Django-only tables (kept so the structure is identical): `auth_group`, `auth_group_permissions`, `auth_permission`, `auth_user_groups`, `auth_user_user_permissions`, `django_admin_log`, `django_content_type`, `django_migrations`.
- Sequences/identity columns, PK and unique constraints, 28 indexes, and 23 FKs.
  - All FKs are `DEFERRABLE INITIALLY DEFERRED`.
  - No FK has an `ON DELETE` clause; Django emulates it in Python.
- App-table FKs that `0002_fk_on_delete` (P1) will rewrite: 14 in total.
  - `accounts_friendship`: `sender_id`, `receiver_id`
  - `rooms_room`: `owner_id`
  - `rooms_message`: `room_id`, `sender_id`, `reply_to_id` (→ SET NULL)
  - `rooms_roommembership`: `room_id`, `user_id`
  - `rooms_roominvitation`: `room_id`, `sender_id`, `receiver_id`
  - `rooms_roomban`: `room_id`, `user_id`, `banned_by_id` (→ SET NULL)

  The constraint names carry Django hashes (e.g. `rooms_roommembership_user_id_22caa5ba_fk_auth_user_id`), so the plan's inspector lookup is needed.

## Left for P1 (as the plan assigns)

- `upgrade()` / `downgrade()`, including the **skip-if-`rooms_room`-exists** guard. P0 only captures the SQL body; `alembic.ini`/`env.py` and the alembic dependency arrive in P1.
- **The raw dump can't be passed straight to `op.execute()`.** P1 must handle these two points without changing the resulting structure:
  - `\restrict <key>` / `\unrestrict <key>` (lines 5 and 1047) are psql meta-commands that pg_dump ≥ 17.6/18.0 emits. They aren't SQL, so they must be filtered out before execution.
  - `SELECT pg_catalog.set_config('search_path', '', false);` clears `search_path` for the rest of the connection. Unless it's reset afterwards, Alembic's own `alembic_version` insert would fail.
- **Verification note:** the `\restrict` key is random on every dump. Comparing a future `pg_dump --schema-only` against this baseline must ignore those two lines, as well as the expected `0002` FK clauses and `alembic_version`.
