// The landing page's technical content. Every line here is true of the backend in this repo
// (roomchat/, rooms/, accounts/): keep it in sync when the backend changes, and never add claims
// that the code does not back.

/** The six features, each with how it actually works. */
export const FEATURES = [
  {
    key: "code",
    title: "Rooms by code",
    text: "Create a room with a name, a capacity of 2–100 and an optional password. Its six-character code is the whole address.",
    tech: "room_code: 6 × [A-Z0-9] · password hashed with PBKDF2-SHA256 · ephemeral: deleted with its messages when the last member leaves (DB cascade)",
  },
  {
    key: "chat",
    title: "Live chat",
    text: "Send, reply with a quoted preview, edit and delete. Opening a room loads its last 100 messages.",
    tech: "WebSocket /ws/chat/{code}/ · incoming frames are a Pydantic discriminated union on type · edits and soft deletes broadcast to the room",
  },
  {
    key: "presence",
    title: "Presence",
    text: "A live member list with join and leave notices. Your friends can see which room you are in.",
    tech: "one RoomMembership row per socket is the presence table · broadcasts go to the Redis group room_<code>",
  },
  {
    key: "friends",
    title: "Friends",
    text: "Send, accept, reject and remove friend requests. The receiver is notified instantly.",
    tech: "/ws/notifications/ · group user_<id> · the request is committed before it is published",
  },
  {
    key: "invite",
    title: "Invitations",
    text: "Invite a friend into your room. An accepted invite admits them once, even into a password room.",
    tech: "accepting consumes the RoomInvitation row and sets session['room_grant'] = code",
  },
  {
    key: "mod",
    title: "Moderation",
    text: "Owners can kick (a ban for the life of the room), transfer ownership, or delete the room.",
    tech: "kick → RoomBan + close 4005 · delete → room_deleted + close 1000",
  },
];

/** True numbers only. `count` is what the counter animates to; `prefix` is kept in front. */
export const STATS = [
  { count: 6, label: "characters per room code" },
  { count: 100, prefix: "2–", label: "members per room" },
  { count: 100, label: "messages of history" },
  { count: 4, label: "fatal close codes" },
  { count: 8, label: "ASGI middleware layers" },
  { count: 55, label: "backend tests" },
];

export const STACK = [
  ["FastAPI", "HTTP API and WebSockets, one ASGI app"],
  ["uvicorn", "ASGI server with uvloop and httptools"],
  ["PostgreSQL", "SQLAlchemy 2 + Alembic, psycopg 3"],
  ["Redis", "pub/sub channel layer, msgpack frames"],
  ["Pydantic v2", "every HTTP and WebSocket payload"],
  ["React 19", "react-router 7, Tailwind, shadcn/ui"],
  ["pytest", "55 tests against real Postgres and Redis"],
  ["Sessions", "one cookie authorises HTTP and sockets"],
];

/** The path of one message, in order (the order is the point, so it is numbered). */
export const FLOW = [
  ["Browser", 'sends {type: "send_message"} on the open socket'],
  ["uvicorn · ChatConsumer", "validates the frame with Pydantic"],
  ["PostgreSQL", "INSERT INTO rooms_message, then commit"],
  ["Redis", "PUBLISH to the group room_82S0OT"],
  ["Every member's socket", "receives message_created and renders it"],
];

/** roomchat/middleware.py MIDDLEWARE, outermost first. */
export const MIDDLEWARE = [
  ["TrustedHost", "rejects requests whose Host isn't allowed"],
  ["SecurityHeaders", "nosniff · X-Frame-Options: DENY · COOP"],
  ["GZip", "compresses responses over 500 bytes"],
  ["DBSession", "one SQLAlchemy session per request"],
  ["Session", "loads the signed sessionid cookie (2 weeks)"],
  ["Authentication", "request.user from the session"],
  ["CsrfView", "X-CSRFToken must match the csrftoken cookie"],
  ["PydanticValidationError", 'turns validation errors into {"errors"}'],
];

/** rooms/consumers.py CLOSE_* codes, plus the two non-fatal closes the client sees. */
export const CLOSE_CODES = [
  ["4001", "Room is full", "fatal · no reconnect"],
  ["4003", "Not signed in, or no grant", "fatal · no reconnect"],
  ["4004", "Room no longer exists", "fatal · no reconnect"],
  ["4005", "Kicked: banned for the room's life", "fatal · no reconnect"],
  ["1000", "The owner deleted the room", "normal close"],
  ["1012", "Server restarting", "retries every 3 s"],
];

/** room_detail_api's check order: reordering it would leak history or bypass a ban. */
export const GATE = [
  ["Room exists", "else 404"],
  ["Not banned", "else 403 (the owner is exempt)"],
  ["Password gate", "owner, grant, or an accepted invite (used once)"],
  ["History", "the last 100 messages → 200"],
];

export const LIFECYCLE = [
  ["Create", "POST /api/rooms/create/ → room_code"],
  ["Join", "session['room_grant'] = code"],
  ["Connect", "a RoomMembership row with its channel_name"],
  ["Last one leaves", "check_and_delete_room_if_empty"],
  ["Deleted", "CASCADE: messages, bans, invitations"],
];

/** The main tables, laid out as index cards (x/y are % of the schema area). */
export const TABLES = [
  { id: "user", name: "auth_user", x: 1, y: 4, rows: ["id", "username", "email", "password · pbkdf2"] },
  { id: "friend", name: "accounts_friendship", x: 1, y: 56, rows: ["sender_id", "receiver_id", "status"], fk: ["user"] },
  { id: "room", name: "rooms_room", x: 38, y: 4, rows: ["id", "room_code · 6 chars", "capacity · 2–100", "password · hash or ''", "owner_id"], fk: ["user"] },
  { id: "member", name: "rooms_roommembership", x: 76, y: 4, rows: ["user_id", "room_id", "channel_name"], fk: ["room"] },
  { id: "msg", name: "rooms_message", x: 38, y: 56, rows: ["room_id", "sender_id", "content", "reply_to_id", "edited_at · is_deleted"], fk: ["room", "user"] },
  { id: "ban", name: "rooms_roomban", x: 76, y: 56, rows: ["room_id", "user_id", "banned_by_id"], fk: ["room"] },
];

/** Scrolling ticker on the landing. */
export const TICKER = [
  "FastAPI 0.162", "uvicorn + uvloop", "Redis pub/sub", "PostgreSQL · psycopg 3", "Pydantic v2 discriminated unions",
  "8 ASGI middleware layers", "one sessionid authorises HTTP and sockets", "close 4001 · 4003 · 4004 · 4005",
  "rooms delete themselves when empty", "55 pytest tests",
];
