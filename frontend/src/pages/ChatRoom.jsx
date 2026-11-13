import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import ThemeToggle from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  ArrowLeft, Copy, Check, Send, Reply, Pencil, Trash2, MoreVertical,
  Crown, UserPlus, UserMinus, Settings, X, Lock, LogOut, Search,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/App";
import { useSocket } from "@/lib/useSocket";
import { clockTime, dayKey, dayLabel, initial, paperFor } from "@/lib/format";

const DELETED_TEXT = "This message was deleted.";

export default function ChatRoom() {
  const { code } = useParams();
  const navigate = useNavigate();
  const { user, setUser } = useAuth();

  const [room, setRoom] = useState(null);
  const [messages, setMessages] = useState([]);
  const [members, setMembers] = useState([]);
  const [ownerId, setOwnerId] = useState(null);
  const [friends, setFriends] = useState([]);
  const [invited, setInvited] = useState({});
  const [draft, setDraft] = useState("");
  const [replyTo, setReplyTo] = useState(null);
  const [editing, setEditing] = useState(null);
  const [copied, setCopied] = useState(false);
  const [activity, setActivity] = useState("Connecting…");
  // The member who joined a moment ago, so their row can flash once.
  const [justJoined, setJustJoined] = useState(null);
  const [loaded, setLoaded] = useState(false);
  // This room is already open in another tab or device: ask before the socket takes it over.
  const [askSwitch, setAskSwitch] = useState(false);
  // Another tab or device took this room over; the notice stays until it is answered.
  const [replaced, setReplaced] = useState(false);
  // Search through the loaded history (browser-only: it never asks the server).
  const [query, setQuery] = useState("");
  const [matchIndex, setMatchIndex] = useState(0);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  // Set when we are already on our way out, so the socket closing does not also fire a
  // reconnect or a second toast.
  const leavingRef = useRef(false);

  const amOwner = ownerId != null && ownerId === user?.id;

  // Everyone in active_users_updated is by definition connected, so there is no
  // away/offline state to represent inside a room (features.txt #12): the header shows
  // members/capacity and the list carries no presence dots.

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.room(code);
        if (cancelled) return;
        setRoom(data.room);
        setOwnerId(data.room.owner_id);
        setMessages(
          data.messages.map((m) => ({
            id: m.message_id,
            userId: m.sender_id,
            author: m.sender_username,
            text: m.is_deleted ? DELETED_TEXT : m.content,
            createdAt: m.created_at,
            edited: Boolean(m.edited_at),
            deleted: m.is_deleted,
            self: m.sender_id === user?.id,
            replyTo: m.reply_to
              ? { author: m.reply_to.sender_username, text: m.reply_to.content }
              : undefined,
          }))
        );
        setAskSwitch(Boolean(data.open_elsewhere));
        setLoaded(true);
      } catch (err) {
        if (cancelled) return;
        if (err.status === 401) {
          setUser(null);
          navigate("/login", { replace: true });
          return;
        }
        // 403 (banned / no grant) and 404 (room gone) both mean "you cannot be here".
        leavingRef.current = true;
        toast.error(err.message);
        navigate("/dashboard", { replace: true });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, user?.id, navigate, setUser]);

  useEffect(() => {
    api
      .friends()
      .then((data) => setFriends(data.friends || []))
      .catch(() => {
        /* the invite dialog just stays empty */
      });
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const leave = useCallback(
    (message, tone = "error", delay = 1200) => {
      leavingRef.current = true;
      if (message) toast[tone](message);
      setTimeout(() => navigate("/dashboard", { replace: true }), delay);
    },
    [navigate]
  );

  const handleEvent = useCallback(
    (data) => {
      switch (data.type) {
        case "room_info":
          setRoom((r) => ({
            ...(r || {}),
            name: data.room_name,
            description: data.room_description,
            capacity: data.capacity,
            owner_id: data.owner_id,
            owner_username: data.owner_username,
            room_code: r?.room_code ?? code,
            is_protected: r?.is_protected ?? false,
          }));
          setOwnerId(data.owner_id);
          break;

        case "active_users_updated":
          setMembers(data.users);
          // A takeover or silent reconnect sends no join notice, so clear the first label here.
          setActivity((a) => (a === "Connecting…" ? "Connected" : a));
          break;

        case "user_joined":
          setActivity(`${data.username} joined the room`);
          setJustJoined(data.user_id);
          setTimeout(() => setJustJoined((id) => (id === data.user_id ? null : id)), 1700);
          break;

        case "user_left":
          setActivity(`${data.username} left the room`);
          break;

        case "user_kicked_broadcast":
          setActivity(`${data.username} was removed`);
          break;

        case "message_created":
          setMessages((list) => [
            ...list,
            {
              id: data.message_id,
              userId: data.sender_id,
              author: data.sender_username,
              text: data.content,
              createdAt: data.created_at,
              edited: false,
              deleted: false,
              self: data.sender_id === user?.id,
              replyTo: data.reply_to
                ? { author: data.reply_to.sender_username, text: data.reply_to.content }
                : undefined,
              fresh: true, // arrived live, so it animates in
            },
          ]);
          break;

        case "message_edited":
          setMessages((list) =>
            list.map((m) =>
              m.id === data.message_id ? { ...m, text: data.content, edited: true } : m
            )
          );
          break;

        case "message_deleted":
          // Deletion is soft on the server: the row survives with its content replaced,
          // and replies to it keep resolving. Blank the bubble rather than removing it.
          setMessages((list) =>
            list.map((m) =>
              m.id === data.message_id
                ? { ...m, text: DELETED_TEXT, deleted: true, edited: false, replyTo: undefined }
                : m
            )
          );
          break;

        case "ownership_transferred":
          setOwnerId(data.new_owner_id);
          setRoom((r) => (r ? { ...r, owner_id: data.new_owner_id, owner_username: data.new_owner_username } : r));
          setActivity(`${data.new_owner_username} is now the owner`);
          toast.success(`${data.new_owner_username} is now the owner`);
          break;

        case "user_kicked":
          leave(data.message, "error", 1500);
          break;

        case "room_deleted":
          leave(data.message, "warning", 1800);
          break;

        case "session_replaced":
          // The socket closes with 4006 right after this; the flag keeps onFatal quiet.
          leavingRef.current = true;
          setReplaced(true);
          break;

        case "invite_sent":
          toast.success(data.message);
          break;

        case "error":
          toast.error(data.message);
          break;

        default:
          console.warn("[chat] unhandled message type:", data.type);
      }
    },
    [user?.id, code, leave]
  );

  const onFatal = useCallback(
    (message) => {
      if (leavingRef.current) return;
      leave(message, "error", 1800);
    },
    [leave]
  );

  // Only connect once the HTTP gate has admitted us, so a rejected room never opens a
  // socket that would immediately be closed with 4003.
  const send = useSocket(loaded && !askSwitch ? `/ws/chat/${code}/` : null, {
    onMessage: handleEvent,
    onFatal,
  });

  const requireSocket = () => {
    toast.error("Still connecting. Try again in a moment.");
    return false;
  };

  const copyCode = () => {
    navigator.clipboard
      ?.writeText(code)
      .then(() => {
        // The button's label swaps to "Copied" for 2.5s; that is the feedback, so no toast.
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      })
      .catch(() => toast.error("Couldn't copy the room code"));
  };

  const handleSend = (e) => {
    e.preventDefault();
    const content = draft.trim();
    if (!content) return;

    if (editing) {
      if (!send({ type: "edit_message", message_id: editing, content })) return requireSocket();
      setEditing(null);
      setDraft("");
      return;
    }
    if (replyTo) {
      if (!send({ type: "reply_message", reply_to_id: replyTo.id, content })) return requireSocket();
    } else if (!send({ type: "send_message", content })) {
      return requireSocket();
    }
    setDraft("");
    setReplyTo(null);
  };

  const startEdit = (msg) => {
    setEditing(msg.id);
    setReplyTo(null);
    setDraft(msg.text);
    inputRef.current?.focus();
  };
  const startReply = (msg) => {
    setReplyTo(msg);
    setEditing(null);
    inputRef.current?.focus();
  };
  const handleDelete = (msg) => {
    if (!send({ type: "delete_message", message_id: msg.id })) requireSocket();
  };

  const handleKick = (m) => {
    if (!send({ type: "kick_user", user_id: m.user_id })) return requireSocket();
    toast(`Removing ${m.username}…`);
  };
  const handleTransfer = (m) => {
    if (!send({ type: "transfer_ownership", user_id: m.user_id })) requireSocket();
  };
  const handleDeleteRoom = () => {
    if (!send({ type: "delete_room" })) requireSocket();
  };
  const handleLeaveRoom = () => {
    leavingRef.current = true;
    navigate("/dashboard");
  };
  const handleInviteFriend = (f) => {
    if (!send({ type: "send_room_invite", user_id: f.user_id })) return requireSocket();
    setInvited((s) => ({ ...s, [f.user_id]: true }));
  };

  // Friends already in the room can't be invited again.
  const invitableFriends = useMemo(
    () => friends.filter((f) => !members.some((m) => m.user_id === f.user_id)),
    [friends, members]
  );

  // Search: which loaded messages contain the query (case-insensitive, deleted ones excluded).
  const needle = query.trim().toLowerCase();
  const matchIds = needle ? messages.filter((m) => !m.deleted && m.text.toLowerCase().includes(needle)).map((m) => m.id) : [];

  /** Scrolls the message list to the next match (Enter in the search box), wrapping round. */
  const jumpToMatch = () => {
    if (matchIds.length === 0) return;
    const next = matchIndex % matchIds.length;
    scrollRef.current?.querySelector(`[data-testid="message-${matchIds[next]}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    setMatchIndex(next + 1);
  };

  if (!room) {
    return (
      <div className="fibre grid h-screen place-items-center bg-paper">
        <div className="sheet pin px-8 pb-6 pt-10 text-center" style={{ transform: "rotate(-1deg)" }}>
          <p className="code-figure text-5xl text-ink">{code}</p>
          <p className="mt-2 text-ink-3" role="status">Opening room…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="fibre flex h-dvh flex-col bg-paper">
      {/* Header: a strip of copy paper with the room, its code, search and the room's controls */}
      <div className="px-3 pt-3 sm:px-5">
        <header className="sheet relative z-20 flex items-center justify-between gap-3 px-2.5 py-2 sm:px-4" data-testid="room-header">
          <div className="flex min-w-0 items-center gap-3">
            <Button variant="ghost" size="icon" onClick={handleLeaveRoom} aria-label="Back to dashboard" data-testid="back-to-dashboard-button">
              <ArrowLeft size={20} />
            </Button>
            <span
              className="hidden h-11 w-11 shrink-0 place-items-center font-display text-2xl text-room-ink shadow-card sm:grid"
              style={{ backgroundColor: paperFor(room.room_code) }}
              aria-hidden="true"
            >
              {initial(room.name)}
            </span>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="truncate text-[34px] text-ink">{room.name}</h1>
                {room.is_protected && (
                  <Lock size={14} className="shrink-0 text-ink-3" aria-label="Password protected" />
                )}
              </div>
              <p className="text-xs text-ink-3">
                <span className="measure text-ink-2">{members.length}/{room.capacity}</span> members · <span className="rc-blink mb-px mr-0.5 inline-block h-1.5 w-1.5 rounded-full bg-success align-middle" aria-hidden="true" /> live
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Search the loaded history: matches light up, Enter jumps to the next one */}
            <label className="hidden h-10 w-56 items-center gap-2 border border-rule bg-paper px-2.5 focus-within:border-ink md:flex xl:w-72">
              <Search size={15} className="shrink-0 text-ink-3" aria-hidden="true" />
              <span className="visually-hidden">Search messages</span>
              <input
                value={query}
                onChange={(e) => { setQuery(e.target.value); setMatchIndex(0); }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") { e.preventDefault(); jumpToMatch(); }
                  if (e.key === "Escape") setQuery("");
                }}
                placeholder="Search messages"
                className="h-full min-w-0 flex-1 bg-transparent text-sm text-ink placeholder:text-ink-3 focus-visible:outline-none"
                data-testid="search-messages-input"
              />
              {needle && (
                <span className="measure shrink-0 font-mono text-xs text-ink-3" aria-live="polite" data-testid="search-match-count">
                  {matchIds.length} {matchIds.length === 1 ? "match" : "matches"}
                </span>
              )}
              {query && (
                <button type="button" onClick={() => setQuery("")} aria-label="Clear search" className="grid h-6 w-6 place-items-center text-ink-3 hover:text-ink">
                  <X size={14} />
                </button>
              )}
            </label>

            <button
              onClick={copyCode}
              className="hidden h-10 items-center gap-2 bg-signal px-3 text-sm text-signal-ink shadow-offset-xs transition-transform duration-micro hover:-translate-y-px active:translate-y-0.5 active:shadow-none sm:flex"
              aria-label={`Copy room code ${room.room_code}`}
              data-testid="copy-room-code-button"
            >
              <span className="code-figure text-2xl">{room.room_code}</span>
              {copied ? (
                <span className="rc-pop flex items-center gap-1 text-sm font-medium" aria-live="polite">
                  <Check size={15} /> Copied
                </span>
              ) : (
                <Copy size={15} />
              )}
            </button>

            <ThemeToggle className="hidden lg:inline-flex" />

            {/* Invite friend */}
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="outline" data-testid="open-invite-dialog-button">
                  <UserPlus size={16} /> <span className="hidden sm:inline">Invite</span>
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-md" data-testid="invite-friend-dialog">
                <DialogHeader>
                  <DialogTitle>Invite a friend</DialogTitle>
                  <DialogDescription>Pull someone from your friends list into {room.name}.</DialogDescription>
                </DialogHeader>
                <ul className="rc-scroll mt-2 max-h-[50vh] overflow-y-auto border-t border-rule-2">
                  {invitableFriends.length === 0 && (
                    <li className="py-8 text-sm text-ink-3">No friends left to invite.</li>
                  )}
                  {invitableFriends.map((f) => (
                    <li key={f.user_id} className="flex items-center gap-3 border-b border-rule-2 py-2" data-testid={`invite-friend-row-${f.user_id}`}>
                      <Avatar className="h-9 w-9">
                        <AvatarFallback style={{ backgroundColor: paperFor(f.username) }}>{initial(f.username)}</AvatarFallback>
                      </Avatar>
                      <p className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{f.username}</p>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleInviteFriend(f)}
                        disabled={Boolean(invited[f.user_id])}
                        data-testid={`invite-friend-${f.user_id}`}
                      >
                        {invited[f.user_id] ? "Invited" : "Invite"}
                      </Button>
                    </li>
                  ))}
                </ul>
              </DialogContent>
            </Dialog>

            {/* Room menu (leave / owner controls) */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="Room menu" data-testid="room-settings-button">
                  <Settings size={20} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem onClick={copyCode}>
                  <Copy size={15} className="mr-2" /> Copy room code
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleLeaveRoom} data-testid="leave-room-menu-item">
                  <LogOut size={15} className="mr-2" /> Leave room
                </DropdownMenuItem>
                {amOwner && (
                  <>
                    <DropdownMenuSeparator />
                    <div className="px-2 py-1.5 text-xs text-ink-3">Owner controls</div>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <button className="flex w-full items-center px-2 py-1.5 text-sm text-error transition-colors hover:bg-hover focus-visible:outline-offset-[-2px]" data-testid="delete-room-menu-item">
                          <Trash2 size={15} className="mr-2" /> Delete room
                        </button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Delete this room?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This permanently removes “{room.name}” and its history for all {members.length} members. This can’t be undone.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction className="bg-error text-error-ink hover:bg-error hover:opacity-90" onClick={handleDeleteRoom} data-testid="confirm-delete-room-button">
                            Delete room
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>
      </div>

      {/* Body: the conversation on one large sheet, the members on a pinned sheet beside it */}
      <div className="flex min-h-0 flex-1 gap-5 px-3 pb-3 pt-4 sm:px-5 sm:pb-5">
        {/* Messages */}
        <div className="sheet-raised flex min-w-0 flex-1 flex-col">
          <div ref={scrollRef} className="rc-scroll fibre-bg flex-1 overflow-y-auto bg-paper-2 px-4 py-6 sm:px-8" data-testid="message-list">
            <div className="mx-auto max-w-3xl">
              {messages.length === 0 && (
                <div className="mx-auto mt-10 w-fit px-6 py-5 text-center">
                  <p className="code-figure text-6xl text-ink-3">{room.room_code}</p>
                  <p className="mt-2 text-sm text-ink-3">No messages yet. Say hello.</p>
                </div>
              )}
              {messages.map((msg, idx) => {
                const prev = messages[idx - 1];
                const newDay = !prev || dayKey(prev.createdAt) !== dayKey(msg.createdAt);
                const grouped = !newDay && prev && prev.userId === msg.userId && !msg.replyTo;
                return (
                  <div key={msg.id}>
                    {newDay && (
                      // Day divider: the label on a strip of tape between two hairlines.
                      <div className="mb-4 mt-6 flex items-center gap-3 text-xs text-ink-3 first:mt-0">
                        <span className="h-px flex-1 bg-rule" />
                        <span className="bg-tape px-2.5 py-0.5 font-mono text-ink">{dayLabel(msg.createdAt)}</span>
                        <span className="h-px flex-1 bg-rule" />
                      </div>
                    )}
                    <MessageRow
                      msg={msg}
                      grouped={grouped}
                      needle={needle}
                      onReply={startReply}
                      onEdit={startEdit}
                      onDelete={handleDelete}
                    />
                  </div>
                );
              })}
            </div>
          </div>

          {/* Composer */}
          <div className="border-t border-rule bg-paper-3 px-4 py-3 sm:px-8">
            <div className="mx-auto max-w-3xl">
              {(replyTo || editing) && (
                // Replying or editing is the current state: it sits on the screen's one fluorescent sheet.
                <div className="sheet-fluoro rc-pop mb-3 flex items-center gap-3 px-3 py-2" data-testid="composer-context">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium">
                      {editing ? "Editing message" : `Replying to ${replyTo.author}`}
                    </p>
                    <p className="truncate text-sm">{editing ? draft : replyTo.text}</p>
                  </div>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-8 w-8 text-signal-ink hover:bg-signal-hover hover:shadow-none"
                    onClick={() => { setReplyTo(null); setEditing(null); setDraft(""); }}
                    aria-label={editing ? "Cancel edit" : "Cancel reply"}
                    data-testid="cancel-context-button"
                  >
                    <X size={16} />
                  </Button>
                </div>
              )}
              <form onSubmit={handleSend} className="flex items-center gap-2" data-testid="composer-form">
                <Input
                  ref={inputRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="Type a message…"
                  aria-label="Message"
                  className="h-11 flex-1 bg-paper"
                  data-testid="message-input"
                />
                <Button type="submit" size="icon" className="h-11 w-11 shrink-0" aria-label="Send message" data-testid="send-message-button">
                  <Send size={18} />
                </Button>
              </form>
            </div>
          </div>
        </div>

        {/* Members: a pinned sheet */}
        <aside className="sheet-raised pin hidden w-72 shrink-0 flex-col pt-6 lg:flex" style={{ transform: "rotate(0.4deg)" }} data-testid="members-sidebar">
          <div className="border-b border-rule-2 px-5 pb-4">
            <div className="flex items-center justify-between">
              <h2 className="text-[30px] text-ink">Members</h2>
              <Badge className="measure" data-testid="member-count-badge">
                {members.length}/{room.capacity}
              </Badge>
            </div>
            <p key={activity} className="rc-pop mt-2 truncate text-xs text-ink-3" role="status" aria-live="polite" data-testid="presence-activity">
              {activity}
            </p>
          </div>
          <ul className="rc-scroll flex-1 overflow-y-auto px-2 py-2">
            {members.map((m) => {
              const rowOwner = m.is_owner;
              return (
                <li
                  key={m.user_id}
                  className={`flex items-center gap-3 px-2 py-2 transition-colors hover:bg-hover ${justJoined === m.user_id ? "rc-flash" : ""}`}
                  data-testid={`member-${m.user_id}`}
                >
                  <Avatar className="h-9 w-9">
                    <AvatarFallback style={{ backgroundColor: paperFor(m.username) }}>{initial(m.username)}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-1.5 truncate text-sm font-medium text-ink">
                      {m.user_id === user?.id ? "You" : m.username}
                      {rowOwner && <Crown size={13} className="text-ink" aria-hidden="true" />}
                    </p>
                    <p className="text-xs text-ink-3">{rowOwner ? "Owner" : "Member"}</p>
                  </div>
                  {amOwner && m.user_id !== user?.id && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8 text-ink-3"
                          aria-label={`Moderate ${m.username}`}
                          data-testid={`member-menu-${m.user_id}`}
                        >
                          <MoreVertical size={16} />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-52">
                        <DropdownMenuItem onClick={() => handleTransfer(m)} data-testid={`transfer-owner-${m.user_id}`}>
                          <Crown size={15} className="mr-2" /> Transfer ownership
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem className="text-error focus:text-error" onClick={() => handleKick(m)} data-testid={`kick-member-${m.user_id}`}>
                          <UserMinus size={15} className="mr-2" /> Kick from room
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </li>
              );
            })}
          </ul>
        </aside>
      </div>

      {/* Second tab: connecting here closes the room in the other tab, so ask first. */}
      <AlertDialog open={askSwitch}>
        <AlertDialogContent data-testid="switch-tab-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>This room is already open</AlertDialogTitle>
            <AlertDialogDescription>
              You have “{room.name}” open in another tab or device. Switch to this one? The other will be disconnected.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => leave(null, "error", 0)} data-testid="keep-other-tab-button">
              Keep the other one
            </AlertDialogCancel>
            <AlertDialogAction onClick={() => setAskSwitch(false)} data-testid="switch-to-this-tab-button">
              Switch to this tab
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* First tab: the room was taken over elsewhere. Stays until answered (button or Esc). */}
      <AlertDialog open={replaced} onOpenChange={(open) => !open && navigate("/dashboard", { replace: true })}>
        <AlertDialogContent data-testid="replaced-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Opened somewhere else</AlertDialogTitle>
            <AlertDialogDescription>
              You opened “{room.name}” in another tab or device, so this one was disconnected.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogAction data-testid="replaced-back-button">Back to dashboard</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/** Splits `text` round case-insensitive matches of `needle` and marks them (search highlight). */
function highlight(text, needle) {
  if (!needle) return text;
  const lower = text.toLowerCase();
  const parts = [];
  let from = 0;
  let at = lower.indexOf(needle);
  while (at !== -1) {
    if (at > from) parts.push(text.slice(from, at));
    parts.push(<mark key={at}>{text.slice(at, at + needle.length)}</mark>);
    from = at + needle.length;
    at = lower.indexOf(needle, from);
  }
  parts.push(text.slice(from));
  return parts;
}

/** One chat message as a squared slip of paper: yours on the right on the "own" stock,
 *  everyone else's on the left with their paper-coloured initial tile. Grouped follow-ups
 *  drop the name and tile; messages that arrived live drop in. While searching, matches are
 *  marked and other messages fade back. */
function MessageRow({ msg, grouped, needle, onReply, onEdit, onDelete }) {
  const isMatch = Boolean(needle) && !msg.deleted && msg.text.toLowerCase().includes(needle);
  // Bubble surface: deleted messages become a dashed outline with muted text.
  const surface = msg.deleted
    ? "border-dashed border-ink-3 bg-transparent text-ink-3"
    : msg.self
      ? "own-sheet border-transparent shadow-card"
      : "border-transparent bg-paper-3 text-ink shadow-card";

  const bubble = (
    <div className={`border px-3.5 py-2 ${surface} ${msg.fresh ? "rc-drop" : ""}`}>
      {msg.replyTo && (
        // Quoted preview: a short rule on the left, author over a one-line excerpt.
        <div className="mb-1.5 border-l-2 border-ink-3 pl-2">
          <p className="text-xs font-medium text-ink-2">{msg.replyTo.author}</p>
          <p className="truncate text-xs text-ink-3">{msg.replyTo.text}</p>
        </div>
      )}
      <p className={`whitespace-pre-wrap break-words text-[15px] leading-relaxed ${msg.deleted ? "italic" : ""}`}>{isMatch ? highlight(msg.text, needle) : msg.text}</p>
    </div>
  );

  // Time (local, a measurement) and the edited flag, side by side under the bubble.
  const meta = (
    <span className={`mt-1 flex gap-2 font-mono text-[11px] text-ink-3 ${msg.self ? "mr-0.5" : "ml-0.5"}`}>
      <span className="measure">{clockTime(msg.createdAt)}</span>
      {msg.edited && <span>edited</span>}
    </span>
  );

  // While searching, everything that doesn't match steps back.
  const dim = needle && !isMatch ? "opacity-35" : "";

  if (msg.self) {
    return (
      <div className={`group flex items-end justify-end gap-2 transition-opacity ${grouped ? "mt-1" : "mt-4"} ${dim}`} data-testid={`message-${msg.id}`} data-match={isMatch || undefined}>
        {!msg.deleted && <MsgActions msg={msg} onReply={onReply} onEdit={onEdit} onDelete={onDelete} self />}
        <div className="flex max-w-[75%] flex-col items-end">
          {bubble}
          {meta}
        </div>
      </div>
    );
  }
  return (
    <div className={`group flex items-end gap-2 transition-opacity ${grouped ? "mt-1" : "mt-4"} ${dim}`} data-testid={`message-${msg.id}`} data-match={isMatch || undefined}>
      <div className="w-9 shrink-0 self-start">
        {!grouped && (
          <Avatar className="h-9 w-9">
            <AvatarFallback style={{ backgroundColor: paperFor(msg.author) }}>{initial(msg.author)}</AvatarFallback>
          </Avatar>
        )}
      </div>
      <div className="flex max-w-[75%] flex-col items-start">
        {!grouped && <span className="mb-1 ml-0.5 text-xs font-medium text-ink-2">{msg.author}</span>}
        {bubble}
        {meta}
      </div>
      {!msg.deleted && <MsgActions msg={msg} onReply={onReply} onEdit={onEdit} onDelete={onDelete} />}
    </div>
  );
}

/** Reply and the message menu beside a bubble. Hidden until the row is hovered or anything
 *  in it has keyboard focus, and always shown on touch screens, which cannot hover. */
function MsgActions({ msg, onReply, onEdit, onDelete, self }) {
  return (
    <div className={`flex items-center self-center opacity-0 transition-opacity duration-micro group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100 ${self ? "order-first" : ""}`}>
      <Button size="icon" variant="ghost" className="h-8 w-8 text-ink-3" onClick={() => onReply(msg)} aria-label="Reply" title="Reply" data-testid={`reply-message-${msg.id}`}>
        <Reply size={16} />
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="icon" variant="ghost" className="h-8 w-8 text-ink-3 data-[state=open]:opacity-100" aria-label="Message options" data-testid={`message-menu-${msg.id}`}>
            <MoreVertical size={16} />
          </Button>
        </DropdownMenuTrigger>
        {/* Edit and delete are sender-only: the consumer filters both on sender=self.user,
            so offering them on someone else's message would only produce an error toast. */}
        <DropdownMenuContent align={self ? "start" : "end"} className="w-40">
          <DropdownMenuItem onClick={() => onReply(msg)}>
            <Reply size={15} className="mr-2" /> Reply
          </DropdownMenuItem>
          {self && (
            <DropdownMenuItem onClick={() => onEdit(msg)} data-testid={`edit-message-${msg.id}`}>
              <Pencil size={15} className="mr-2" /> Edit
            </DropdownMenuItem>
          )}
          {self && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="text-error focus:text-error" onClick={() => onDelete(msg)} data-testid={`delete-message-${msg.id}`}>
                <Trash2 size={15} className="mr-2" /> Delete
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
