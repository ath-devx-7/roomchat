# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primary audience of the public pages: recruiters and interviewers** evaluating the author's
  work (confirmed 2026-11-01). They arrive from a CV, portfolio or GitHub link, usually on a
  laptop, and spend a minute or two deciding whether the project is real engineering.
- People who sign up to try it are mostly the same evaluators, plus the author and friends
  testing with two browser windows. The app screens are used **mostly on desktop** (confirmed);
  phones must work but are not the design target.

## Product Purpose

RoomChat is real-time, room-based chat: sign up, add friends, create or join a room by a
6-character code, and chat live. It exists to show modern real-time web architecture working
end to end. Success is an evaluator understanding within seconds that it is live, and then
seeing it work (instant messages, presence, invitations, moderation).

## Positioning

A room is a code, not a channel list: 6 characters (`[A-Z0-9]`) is the whole address, and a
room is ephemeral: it is deleted with all its messages when the last member leaves. Everything
is pushed live over WebSockets (messages, presence, invites, kicks), with no page refreshes.

## Operating Context

- One ASGI app (FastAPI + uvicorn) serves the JSON API, two WebSocket endpoints and the React SPA
  shell. Session cookie auth covers both HTTP and sockets.
- Evaluators often test with two users side by side (two browsers or a private window).

## Capabilities and Constraints

- Accounts: register (with password confirmation), log in, log out. Login is username-only.
- Friends: send, accept, reject, remove; live notification of a new request.
- Rooms: name, capacity 2–100 (default 10), optional password; the API accepts a description
  but the UI has no field for it. One room at a time per user.
- Chat: send, reply (quoted preview), edit, soft delete; live presence list with join/leave
  notices; 100 messages of history (currently the oldest 100).
- Moderation (owner only): kick (a ban for the life of the room), transfer ownership, delete room.
- Invitations: invite a friend into a room; an accepted invite admits once, even past a password.
- No avatars, typing indicators, read state, notification history, or password reset on the
  backend. In a room, everyone listed is connected; friends show only "in a room" or not.
- Frontend: React 19, react-router 7, Tailwind 3, shadcn/ui (Radix), sonner, lucide icons,
  framer-motion available; CRA via craco. The built bundle in `static/react/` is committed.
  Asset URLs reach the bundle only through the server bootstrap (`window.__ROOMCHAT__`).
- Every page must have light and dark modes. No functionality may break in a redesign, and
  every change to what controls or pages exist is the owner's decision.

## Brand Commitments

- Name: RoomChat. The 6-character room code is the product's identifying object.
- Owner explicitly allows the whole visual theme (palette, type, shapes) to be replaced.

## Evidence on Hand

- The working app itself, which can be recorded or captured; nothing else.
- There are no users, testimonials, metrics, customers or press. Never invent them.
- Real numbers that are true: 6-character codes, 2–100 capacity, 100 messages of history,
  4 fatal close codes, 55 backend tests.

## Product Principles

1. Show it working: the live behaviour is the proof, not adjectives.
2. The code is the room: joining should feel like typing an address.
3. Honest state: show only presence and data the backend actually has.
4. Nothing breaks: a redesign changes how things look, never what they do.
