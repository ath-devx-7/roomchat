# RoomChat

RoomChat is a full-stack real-time communication platform that allows authenticated users to create and join chat rooms using unique room codes. Unlike traditional request-response web applications, RoomChat leverages WebSockets to provide instant message delivery, live presence updates, room invitations, and moderation actions without requiring page refreshes.

The project was built to explore modern real-time web application architecture using Django Channels and ASGI, while implementing features commonly found in collaborative communication platforms.


## Key Features

- 🔐 **Authentication System** – User registration, login, and session-based authentication.
- 👥 **Friend Management** – Send, accept, and remove friend requests.
- 🏠 **Room-Based Chat** – Create or join rooms using unique 6-character room codes. Rooms are ephemeral: once in use, a room is deleted as soon as its last member disconnects (see [Room lifecycle](#room-lifecycle)).
- 🔑 **Private Rooms** – Optional password protection and a configurable capacity of 2–100 members [default 10].
- ⚡ **Real-Time Messaging** – Instant message delivery using WebSockets and Django Channels.
- 💬 **Message Actions** – Reply to, edit, and delete messages.
- 👤 **Presence Tracking** – Live active-user list with join/leave notifications.
- 📨 **Room Invitations** – Invite friends to rooms with real-time notification delivery.
- 🛡️ **Room Moderation** – Kick users, transfer ownership, and delete rooms. A kick persists for the life of the room: the removed user cannot rejoin it.
- 🔄 **Live Synchronization** – Messages, presence, and room events update without page refreshes.


## Tech Stack
 
| Layer | Technology |
|---|---|
| Backend framework | Django 6.0 |
| Data Validation and serialization | Pydantic v2 |
| Real-time layer | Django Channels |
| ASGI server | Daphne |
| Database | PostgreSQL |
| Channel layer | Redis (`channels_redis`, pub/sub) |
| Frontend | HTML, CSS, vanilla JavaScript |
| Protocol | WebSockets (alongside standard HTTP) |

## Architecture Overview

RoomChat combines traditional Django HTTP requests with real-time WebSocket communication using Django Channels.

- **HTTP** handles authentication, friend management, room creation, and page rendering.
- **WebSockets** handle real-time messaging, active user updates, room invitations, and moderation events.

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
Views  Consumers
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

While a room is alive, the room page loads the **most recent 100 messages** on page load; anything older is not sent to the client.

## Prerequisites

Make sure you have the following installed on your machine:
- [Python 3.12+](https://www.python.org/downloads/) (Django 6.0 requires 3.12 or newer)
- [pip](https://pip.pypa.io/en/stable/installation/) (Python package manager)
- **PostgreSQL 14+** — the application database
- **Redis 7+** — backs the Channels channel layer. All real-time features (messaging, presence, invitations, moderation) stop working without it.

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
cp .env.example .env
```
Next, you need to generate a new Django `SECRET_KEY`. Run the following command:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
Open the `.env` file and replace `your_generated_secret_key_here` with the key that was just printed in your terminal.

Then set the remaining values to match your setup:

| Variable | Notes |
|---|---|
| `SECRET_KEY` | Generated with the command above. |
| `DEBUG` | `True` for local development. |
| `ALLOWED_HOSTS` | Comma-separated list; `*` is fine locally. |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | Must match your PostgreSQL server. |
| `REDIS_URL` | Optional — defaults to `redis://127.0.0.1:6379/0` if left unset. |

**5. Create the database**
```bash
createdb -U postgres roomchat
```
Skip this if you used the Docker command above — `POSTGRES_DB=roomchat` already created it.

**6. Apply database migrations**
```bash
python manage.py migrate
```

**7. Create an admin user (Optional)**
```bash
python manage.py createsuperuser
```
Gives you the Django admin at `http://127.0.0.1:8000/admin/`, where rooms, memberships, invitations, messages and friendships are all browsable. Handy during development for watching presence rows appear and disappear as users connect.

**8. Run the development server**

Make sure PostgreSQL and Redis are both running first. The server starts fine without Redis, but every real-time feature will silently fail once you use the app, so it is worth confirming:
```bash
docker exec roomchat-redis redis-cli ping    # -> PONG
```
Then start the server:
```bash
python manage.py runserver
```

The application will be available at `http://127.0.0.1:8000/`.

## Running the tests

The suite covers validation-error formatting, the Pydantic error middleware, Redis channel-layer delivery between independent layer instances, and live consumers driven through `WebsocketCommunicator` — the notification socket, the room password gate, and kick-ban enforcement across both entry points.

```bash
python manage.py test
```

Two things to know before you run it:

- **PostgreSQL and Redis must both be running.** There is no in-memory channel-layer override in the test settings, so a Redis connection failure fails the suite rather than skipping it. The database user also needs permission to create the test database (the default `postgres` superuser has it).
- **Don't run the suite while a dev server is live on the same Redis.** The tests use fixed channel-group names, and Redis pub/sub is not scoped by database number — so pointing the suite at a different `/N` will not isolate it from a running server.

## Deployment

`render.yaml` is a [Render](https://render.com) Blueprint that provisions all three pieces the app needs — the ASGI web service, PostgreSQL, and a Key Value (Redis) instance for the channel layer — and wires the connection details between them automatically. Point a new Blueprint at the repository and no environment variables need to be entered by hand: `SECRET_KEY` is generated, the five `DB_*` values come from the database, `REDIS_URL` comes from the Key Value instance, and `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` are derived in `settings.py` from the hostname Render injects.

`.env.production.example` documents the same variable set for deploying anywhere else.

Two details specific to this stack:

- **The server must be Daphne, not Gunicorn.** WebSockets need ASGI, so the start command is `daphne -b 0.0.0.0 -p $PORT --proxy-headers roomchat.asgi:application`. A WSGI server will serve the pages fine and then break every real-time feature.
- **Static files are served by WhiteNoise** from inside the ASGI process, so `collectstatic` runs at build time and there is no separate static host to configure.

Worth knowing before you deploy on the free tier:

- Free PostgreSQL instances are deleted after 30 days.
- Free web services spin down after ~15 minutes of inactivity, and the first request afterwards takes 30–60 seconds. Because a room is deleted along with its messages when its last member disconnects, a spin-down or a redeploy destroys every live room and its chat history — the intended design, just triggered more often than it is locally.
- The same restarts leave stale presence rows behind, which can make an empty room report itself as full. See `github-issues/deploy-issues.txt`.