# RoomChat

RoomChat is a full-stack real-time communication platform that allows authenticated users to create and join chat rooms using unique room codes. Unlike traditional request-response web applications, RoomChat leverages WebSockets to provide instant message delivery, live presence updates, room invitations, and moderation actions without requiring page refreshes.

The project was built to explore modern real-time web application architecture using Django Channels and ASGI, while implementing features commonly found in collaborative communication platforms.


## Key Features

- 🔐 **Authentication System** – User registration, login, and session-based authentication.
- 👥 **Friend Management** – Send, accept, and remove friend requests.
- 🏠 **Room-Based Chat** – Create or join rooms using unique 6-character room codes.
- 🔑 **Private Rooms** – Optional password protection and configurable room capacity.
- ⚡ **Real-Time Messaging** – Instant message delivery using WebSockets and Django Channels.
- 💬 **Message Actions** – Reply to, edit, and delete messages.
- 👤 **Presence Tracking** – Live active-user list with join/leave notifications.
- 📨 **Room Invitations** – Invite friends to rooms with real-time notification delivery.
- 🛡️ **Room Moderation** – Kick users, transfer ownership, and delete rooms.
- 🔄 **Live Synchronization** – Messages, presence, and room events update without page refreshes.


## Tech Stack
 
| Layer | Technology |
|---|---|
| Backend framework | Django |
| Real-time layer | Django Channels |
| ASGI server | Daphne |
| Database | SQLite |
| Channel layer | In-memory (development) |
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

The application uses room-based channel groups for message broadcasting and a `RoomMembership` model for real-time presence tracking.

## Prerequisites

Make sure you have the following installed on your machine:
- [Python 3.10+](https://www.python.org/downloads/)
- [pip](https://pip.pypa.io/en/stable/installation/) (Python package manager)

## Installation & Setup

Follow these steps to get your development environment running:

**1. Clone the repository**
```bash
git clone https://github.com/yourusername/roomchat.git
cd roomchat
```

**2. Create and activate a virtual environment (Recommended)**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
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

**5. Apply database migrations**
```bash
python manage.py migrate
```

**6. Run the development server**
```bash
python manage.py runserver
```

The application will be available at `http://127.0.0.1:8000/`.

