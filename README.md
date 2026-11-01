# RoomChat

RoomChat is a full-stack real-time communication platform that allows authenticated users to create and join chat rooms using unique room codes. Unlike traditional request-response web applications, RoomChat leverages WebSockets to provide instant message delivery, live presence updates, room invitations, and moderation actions without requiring page refreshes.

The project was built to explore modern real-time web application architecture on ASGI, while implementing features commonly found in collaborative communication platforms. It started on Django and Django Channels and was later migrated to FastAPI, with a small in-house WebSocket and Redis pub/sub layer in place of Channels.


## Key Features

- 🔐 **Authentication System** – User registration, login, and session-based authentication.
- 👥 **Friend Management** – Send, accept, and remove friend requests.
- 🏠 **Room-Based Chat** – Create or join rooms using unique 6-character room codes. Rooms are ephemeral: once in use, a room is deleted as soon as its last member disconnects (see [Room lifecycle](#room-lifecycle)).
- 🔑 **Private Rooms** – Optional password protection and a configurable capacity of 2–100 members [default 10].
- ⚡ **Real-Time Messaging** – Instant message delivery using WebSockets and a Redis pub/sub channel layer.
- 💬 **Message Actions** – Reply to, edit, and delete messages.
- 👤 **Presence Tracking** – Live active-user list with join/leave notifications.
- 📨 **Room Invitations** – Invite friends to rooms with real-time notification delivery.
- 🛡️ **Room Moderation** – Kick users, transfer ownership, and delete rooms. A kick persists for the life of the room: the removed user cannot rejoin it.
- 🔄 **Live Synchronization** – Messages, presence, and room events update without page refreshes.


## Tech Stack
 
| Layer | Technology |
|---|---|
| Backend framework | FastAPI (on Starlette) |
| Data Validation and serialization | Pydantic v2 |
| Database access | SQLAlchemy 2.x, migrations with Alembic |
| Real-time layer | In-house WebSocket consumers (`roomchat/realtime.py`) |
| ASGI server | uvicorn |
| Database | PostgreSQL |
| Channel layer | Redis (`redis.asyncio`, pub/sub) |
| Admin panel | sqladmin |
| Frontend | React 19, react-router, Tailwind CSS, shadcn/ui (Radix) |
| Frontend build | Create React App via craco |
| Protocol | WebSockets (alongside a JSON HTTP API) |

## Architecture Overview

RoomChat is a React single-page app talking to a FastAPI backend that serves both a JSON API and
WebSockets from one ASGI application.

- **HTTP** is a JSON API under `/api/` (authentication, friend management, room creation, room
  history), plus the shell page that boots the SPA. Every non-API path returns that shell, so
  client-side routes survive a refresh or a pasted link.
- **WebSockets** handle real-time messaging, active user updates, room invitations, and moderation
  events.

Both are authenticated by the same server-side session cookie, so signing in over HTTP is what authorises
the WebSocket handshake.

```text
Browser
   │
   ▼
ASGI Application
   │
┌──┴──┐
│     │
▼     ▼
HTTP  WebSocket
│       │
JSON   Consumers
API      │
+ SPA    │
shell    │
│       │
└───┬───┘
    ▼
 Database
```

The application uses room-based channel groups for message broadcasting and a `RoomMembership` model for real-time presence tracking. The channel layer is backed by Redis, so broadcasts cross process boundaries and the application can be run with multiple ASGI workers.

### Room lifecycle

Rooms are throwaway sessions, not persistent channels. `RoomMembership` doubles as the presence table — a row is created when a user's WebSocket connects and deleted when it disconnects — and **when the last member disconnects, the room is deleted along with its entire message history.** Closing the last tab is enough.

Two other ways a room ends: the owner can delete it outright, or transfer ownership to another connected member and leave.

Kick bans hang off the room row and are removed by the same cascade, so a kick lasts exactly as long as the room does and there is no unban flow to build.

One gap worth knowing: that cleanup only runs from the WebSocket disconnect handler. A room is created by an ordinary HTTP request, so a room that is created but never actually entered has no disconnect to trigger on and will sit in the database indefinitely, holding its room code, with zero members and zero messages.

While a room is alive, opening it loads **100 messages** of history; anything beyond that is not
sent to the client. Note this is currently the *oldest* 100 rather than the most recent — a known
bug.

## Feature gaps

The UI is deliberately a little larger than the backend: some affordances are visible but not yet
functional (avatars, friend presence, member counts on invitations, typing indicators, password
reset). They are known gaps rather than bugs, so check this list before assuming something is
broken.

## Prerequisites

Make sure you have the following installed on your machine:
- [Python 3.13+](https://www.python.org/downloads/) (the deployment pins 3.13.5)
- [pip](https://pip.pypa.io/en/stable/installation/) (Python package manager)
- **Node.js 18+ and Yarn** — *only if you intend to change the frontend.* The compiled bundle is
  committed to `static/react/`, so running the app does not require Node at all.
- **PostgreSQL 14+** — the application database
- **Redis 7+** — backs the real-time channel layer. All real-time features (messaging, presence, invitations, moderation) stop working without it.

The quickest way to get both services running, identically on any OS, is Docker:

```bash
docker run -d --name roomchat-postgres --restart unless-stopped \
  -e POSTGRES_DB=roomchat -e POSTGRES_PASSWORD=your_db_password \
  -p 5432:5432 postgres:16-alpine

docker run -d --name roomchat-redis --restart unless-stopped \
  -p 6379:6379 redis:7-alpine
```

Or install them natively — `apt install postgresql redis-server` on Debian/Ubuntu, `brew install postgresql redis` on macOS, or on Windows the PostgreSQL installer plus [Memurai](https://www.memurai.com/) (Redis has no official Windows build).

## Installation & Setup

Follow these steps to get your development environment running:

**1. Clone the repository**
```bash
git clone https://github.com/ath-devx-7/roomchat.git
cd roomchat
```

**2. Create and activate a virtual environment (Recommended)**
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Set up environment variables**
Copy the example environment file to create your own configuration:
```bash
# Windows
copy .env.example .env

# macOS/Linux
cp .env.example .env
```
Next, you need to generate a new `SECRET_KEY`. Run the following command:
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```
Open the `.env` file and replace `your_generated_secret_key_here` with the key that was just printed in your terminal.

Then set the remaining values to match your setup:

| Variable | Notes |
|---|---|
| `SECRET_KEY` | Generated with the command above. |
| `DEBUG` | `True` for local development. |
| `ALLOWED_HOSTS` | Comma-separated list; `*` is fine locally. |
| `CSRF_TRUSTED_ORIGINS` | Optional locally; only needed when the site is served from another origin (e.g. behind a TLS proxy). |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | Must match your PostgreSQL server. |
| `REDIS_URL` | Optional — defaults to `redis://127.0.0.1:6379/0` if left unset. |

**5. Create the database**
```bash
createdb -U postgres roomchat
```
Skip this if you used the Docker command above — `POSTGRES_DB=roomchat` already created it.

**6. Apply database migrations**
```bash
alembic upgrade head
```

**7. Create an admin user (Optional)**
```bash
python -m roomchat.cli createsuperuser
```
It asks for a username, an optional email and a password, and creates a staff user. That gives you the admin panel at `http://127.0.0.1:8000/admin/` (it has its own login), where rooms, memberships, invitations, messages and friendships are all browsable. Handy during development for watching presence rows appear and disappear as users connect.

**8. Build the frontend (only if you changed it)**

The production bundle in `static/react/` is committed, so you can skip this entirely unless you have
edited something under `frontend/src/`:
```bash
cd frontend
yarn install
yarn build          # writes ../static/react/js/main.js and ../static/react/css/main.css
cd ..
```
Commit the rebuilt bundle along with your source change — the deployment has no Node runtime and
builds nothing, so an uncommitted bundle means your change never reaches the browser. Restart the
server after a build: asset URLs carry a content hash that is computed once per server process.

For faster iteration, `yarn start` runs the CRA dev server on `:3000` and proxies HTTP to the backend on
`:8000`. It does not reliably proxy WebSockets, so verify anything real-time against a real build.

**9. Run the development server**

Make sure PostgreSQL and Redis are both running first. The server starts fine without Redis, but every real-time feature will silently fail once you use the app, so it is worth confirming:
```bash
docker exec roomchat-redis redis-cli ping    # -> PONG
```
Then start the server:
```bash
uvicorn roomchat.asgi:application
```
There is deliberately no `--reload`: every restart closes all WebSockets, and a room is deleted when its last member disconnects.

The application will be available at `http://127.0.0.1:8000/`.

## Running the tests

The suite (pytest) covers validation-error formatting, the Pydantic error middleware, Redis channel-layer delivery between independent layer instances, live consumers driven through an in-process `WebsocketCommunicator` (the notification socket, the room password gate, kick-ban enforcement across both entry points), the JSON auth endpoints, and the SPA shell — including that client-side routes survive a hard refresh and that `/api/` paths never fall through to it.

```bash
pip install -r requirements-dev.txt
pytest
```

Two things to know before you run it:

- **PostgreSQL and Redis must both be running.** There is no in-memory channel-layer override in the test settings, so the suite stops before running any test if Redis is unreachable. It creates its own database, `test_<DB_NAME>`, and drops it at the end, so the database user needs permission to create databases (the default `postgres` superuser has it).
- **Don't run the suite while a dev server is live on the same Redis.** The tests use fixed channel-group names, and Redis pub/sub is not scoped by database number — so pointing the suite at a different `/N` will not isolate it from a running server. The suite checks for this and refuses to start.

## Deployment

`render.yaml` is a [Render](https://render.com) Blueprint that provisions all three pieces the app needs — the ASGI web service, PostgreSQL, and a Key Value (Redis) instance for the channel layer — and wires the connection details between them automatically. Point a new Blueprint at the repository and no environment variables need to be entered by hand: `SECRET_KEY` is generated, the five `DB_*` values come from the database, `REDIS_URL` comes from the Key Value instance, and `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` are derived in `settings.py` from the hostname Render injects.

`.env.production.example` documents the same variable set for deploying anywhere else.

A few details specific to this stack:

- **The server must be an ASGI server (uvicorn), not a WSGI one like plain Gunicorn.** WebSockets need ASGI, so the start command is `uvicorn roomchat.asgi:application --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers --forwarded-allow-ips '*'`. A WSGI server would break every real-time feature.
- **Migrations run at build time.** The build command is `pip install -r requirements.txt && alembic upgrade head`.
- **Static files are served by the app itself** from inside the ASGI process, with a content hash in each asset URL (`?v=…`), so there is no build-time static step and no separate static host to configure.
- **The frontend is not built during deployment.** Render's build runs the Python runtime, which has no npm, so `static/react/` is committed and served as-is. Rebuild and commit it locally whenever the frontend changes.

Worth knowing before you deploy on the free tier:

- Free PostgreSQL instances are deleted after 30 days.
- Free web services spin down after ~15 minutes of inactivity, and the first request afterwards takes 30–60 seconds. Because a room is deleted along with its messages when its last member disconnects, a spin-down or a redeploy destroys every live room and its chat history — the intended design, just triggered more often than it is locally.
- A normal redeploy closes every socket cleanly, but a crash or a killed process skips that cleanup and can leave stale presence rows behind, which can make an empty room report itself as full.