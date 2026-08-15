import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { StatusDot } from "@/components/Brand";
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
  ArrowLeft, Copy, Check, Users, Send, Reply, Pencil, Trash2, MoreVertical,
  Crown, UserPlus, UserMinus, Settings, X, Smile, Paperclip, Lock, LogOut,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/App";
import { useSocket } from "@/lib/useSocket";
import { accentFor, clockTime, dayKey, dayLabel, initial } from "@/lib/format";

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
  const [loaded, setLoaded] = useState(false);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  // Set when we are already on our way out, so the socket closing does not also fire a
  // reconnect or a second toast.
  const leavingRef = useRef(false);

  const accent = accentFor(code);
  const amOwner = ownerId != null && ownerId === user?.id;

  // Everyone in active_users_updated is by definition connected, so there is no
  // away/offline state to represent inside a room (features.txt #12).
  const online = members.length;

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
          break;

        case "user_joined":
          setActivity(`${data.username} joined the room`);
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
  const send = useSocket(loaded ? `/ws/chat/${code}/` : null, {
    onMessage: handleEvent,
    onFatal,
  });

  const requireSocket = () => {
    toast.error("Still connecting — try again in a moment.");
    return false;
  };

  const copyCode = () => {
    navigator.clipboard
      ?.writeText(code)
      .then(() => {
        setCopied(true);
        toast.success("Room code copied");
        setTimeout(() => setCopied(false), 1500);
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

  if (!room) {
    return (
      <div className="grid h-screen place-items-center bg-background">
        <p className="font-bold text-slate-400">Opening room…</p>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Header */}
      <header className="z-20 flex items-center justify-between border-b border-border bg-white px-4 py-3 shadow-sm sm:px-6" data-testid="room-header">
        <div className="flex min-w-0 items-center gap-3">
          <Button variant="ghost" size="icon" className="rounded-full text-slate-500" onClick={handleLeaveRoom} data-testid="back-to-dashboard-button">
            <ArrowLeft size={20} />
          </Button>
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl text-lg font-extrabold text-white" style={{ backgroundColor: accent }}>
            {initial(room.name)}
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-lg font-extrabold text-slate-900">{room.name}</h1>
              {room.is_protected && <Lock size={14} className="text-slate-400" />}
            </div>
            <p className="flex items-center gap-1.5 text-xs font-semibold text-green-600">
              <span className="h-1.5 w-1.5 rounded-full bg-green-500" /> {online} online · {members.length}/{room.capacity} members
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={copyCode}
            className="hidden items-center gap-2 rounded-full bg-secondary px-4 py-2 text-sm font-bold text-slate-600 transition-colors hover:bg-accent hover:text-primary sm:flex"
            data-testid="copy-room-code-button"
          >
            <span className="font-mono tracking-widest">{room.room_code}</span>
            {copied ? <Check size={15} className="text-green-600" /> : <Copy size={15} />}
          </button>

          {/* Invite friend */}
          <Dialog>
            <DialogTrigger asChild>
              <Button className="rounded-full font-bold" data-testid="open-invite-dialog-button">
                <UserPlus size={17} className="mr-1.5" /> Invite
              </Button>
            </DialogTrigger>
            <DialogContent className="rounded-3xl sm:max-w-md" data-testid="invite-friend-dialog">
              <DialogHeader>
                <DialogTitle className="text-xl font-extrabold">Invite a friend</DialogTitle>
                <DialogDescription>Pull someone from your friends list into {room.name}.</DialogDescription>
              </DialogHeader>
              <div className="mt-2 max-h-[50vh] space-y-1 overflow-y-auto rc-scroll">
                {invitableFriends.length === 0 && (
                  <p className="py-8 text-center text-sm text-slate-400">No friends left to invite.</p>
                )}
                {invitableFriends.map((f) => (
                  <div key={f.user_id} className="flex items-center gap-3 rounded-2xl p-2 hover:bg-secondary" data-testid={`invite-friend-row-${f.user_id}`}>
                    <div className="relative">
                      <Avatar className="h-10 w-10">
                        <AvatarFallback>{initial(f.username)}</AvatarFallback>
                      </Avatar>
                      <span className="absolute -bottom-0.5 -right-0.5"><StatusDot status="offline" /></span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-bold text-slate-800">{f.username}</p>
                      <p className="text-xs text-slate-400">@{f.username}</p>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="rounded-full border-2 font-bold"
                      onClick={() => handleInviteFriend(f)}
                      disabled={Boolean(invited[f.user_id])}
                      data-testid={`invite-friend-${f.user_id}`}
                    >
                      {invited[f.user_id] ? "Invited" : "Invite"}
                    </Button>
                  </div>
                ))}
              </div>
            </DialogContent>
          </Dialog>

          {/* Room menu (leave / owner controls) */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="rounded-full text-slate-500" data-testid="room-settings-button">
                <Settings size={20} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52 rounded-2xl p-1.5">
              <DropdownMenuItem className="rounded-xl font-semibold" onClick={copyCode}>
                <Copy size={15} className="mr-2" /> Copy room code
              </DropdownMenuItem>
              <DropdownMenuItem className="rounded-xl font-semibold" onClick={handleLeaveRoom} data-testid="leave-room-menu-item">
                <LogOut size={15} className="mr-2" /> Leave room
              </DropdownMenuItem>
              {amOwner && (
                <>
                  <DropdownMenuSeparator />
                  <div className="px-2 py-1.5 text-xs font-extrabold uppercase tracking-wide text-slate-400">Owner controls</div>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <button className="flex w-full items-center rounded-xl px-2 py-1.5 text-sm font-semibold text-destructive hover:bg-destructive/10" data-testid="delete-room-menu-item">
                        <Trash2 size={15} className="mr-2" /> Delete room
                      </button>
                    </AlertDialogTrigger>
                    <AlertDialogContent className="rounded-3xl">
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete this room?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This permanently removes “{room.name}” and its history for all {members.length} members. This can't be undone.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel className="rounded-full font-bold">Cancel</AlertDialogCancel>
                        <AlertDialogAction className="rounded-full bg-destructive font-bold hover:bg-destructive/90" onClick={handleDeleteRoom} data-testid="confirm-delete-room-button">
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

      {/* Body */}
      <div className="flex min-h-0 flex-1">
        {/* Messages */}
        <div className="flex min-w-0 flex-1 flex-col">
          <div ref={scrollRef} className="chat-bg flex-1 overflow-y-auto rc-scroll px-4 py-6 sm:px-8" data-testid="message-list">
            <div className="mx-auto max-w-3xl space-y-1">
              {messages.length === 0 && (
                <p className="py-10 text-center text-sm font-semibold text-slate-400">
                  No messages yet — say hello.
                </p>
              )}
              {messages.map((msg, idx) => {
                const prev = messages[idx - 1];
                const newDay = !prev || dayKey(prev.createdAt) !== dayKey(msg.createdAt);
                const grouped = !newDay && prev && prev.userId === msg.userId && !msg.replyTo;
                return (
                  <div key={msg.id}>
                    {newDay && (
                      <div className="mb-6 mt-2 flex justify-center">
                        <span className="rounded-full bg-white/70 px-4 py-1.5 text-xs font-bold text-slate-500 shadow-sm">
                          {dayLabel(msg.createdAt)}
                        </span>
                      </div>
                    )}
                    <MessageRow
                      msg={msg}
                      grouped={grouped}
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
          <div className="border-t border-border bg-white px-4 py-3 sm:px-8">
            <div className="mx-auto max-w-3xl">
              {(replyTo || editing) && (
                <div className="mb-2 flex items-center gap-2 rounded-2xl bg-accent/60 px-4 py-2 rc-pop" data-testid="composer-context">
                  <div className="h-8 w-1 rounded-full bg-primary" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-extrabold text-primary">
                      {editing ? "Editing message" : `Replying to ${replyTo.author}`}
                    </p>
                    <p className="truncate text-sm text-slate-500">{editing ? draft : replyTo.text}</p>
                  </div>
                  <button
                    onClick={() => { setReplyTo(null); setEditing(null); setDraft(""); }}
                    className="grid h-7 w-7 place-items-center rounded-full text-slate-400 hover:bg-white"
                    data-testid="cancel-context-button"
                  >
                    <X size={16} />
                  </button>
                </div>
              )}
              <form onSubmit={handleSend} className="flex items-end gap-2" data-testid="composer-form">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="rounded-full text-slate-400 shrink-0"
                  title="Attachments aren't available yet"
                  onClick={() => toast("Attachments aren't available yet.")}
                >
                  <Paperclip size={20} />
                </Button>
                <div className="relative flex-1">
                  <Input
                    ref={inputRef}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="Type a message…"
                    className="h-12 rounded-full border-slate-200 bg-secondary/60 pl-5 pr-11 focus-visible:ring-2 focus-visible:ring-primary/30"
                    data-testid="message-input"
                  />
                  <button
                    type="button"
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                    title="Emoji picker isn't available yet"
                    onClick={() => toast("The emoji picker isn't available yet.")}
                  >
                    <Smile size={20} />
                  </button>
                </div>
                <Button type="submit" size="icon" className="h-12 w-12 shrink-0 rounded-full shadow-floating transition-transform hover:scale-105" data-testid="send-message-button">
                  <Send size={20} />
                </Button>
              </form>
            </div>
          </div>
        </div>

        {/* Members sidebar */}
        <aside className="hidden w-72 shrink-0 flex-col border-l border-border bg-white lg:flex" data-testid="members-sidebar">
          <div className="border-b border-border px-5 py-4">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 font-extrabold text-slate-900">
                <Users size={18} /> Members
              </h2>
              <Badge className="rounded-full bg-secondary text-slate-600 hover:bg-secondary" data-testid="member-count-badge">
                {members.length}/{room.capacity}
              </Badge>
            </div>
            <div className="mt-3 flex items-center gap-2 rounded-2xl bg-green-50 px-3 py-2 text-xs font-bold text-green-700 rc-pop" key={activity} data-testid="presence-activity">
              <span className="h-2 w-2 animate-pulse rounded-full bg-green-500" />
              {activity}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto rc-scroll p-2">
            {members.map((m) => {
              const rowOwner = m.is_owner;
              return (
                <div key={m.user_id} className="group flex items-center gap-3 rounded-2xl p-2 transition-colors hover:bg-secondary" data-testid={`member-${m.user_id}`}>
                  <div className="relative">
                    <Avatar className="h-10 w-10">
                      <AvatarFallback>{initial(m.username)}</AvatarFallback>
                    </Avatar>
                    <span className="absolute -bottom-0.5 -right-0.5"><StatusDot status="online" /></span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-1.5 truncate text-sm font-bold text-slate-800">
                      {m.user_id === user?.id ? "You" : m.username}
                      {rowOwner && <Crown size={13} className="text-amber-500" />}
                    </p>
                    <p className="text-xs capitalize text-slate-400">{rowOwner ? "Owner" : "online"}</p>
                  </div>
                  {amOwner && m.user_id !== user?.id && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button className="grid h-8 w-8 place-items-center rounded-full text-slate-400 opacity-0 transition-opacity hover:bg-slate-100 group-hover:opacity-100" data-testid={`member-menu-${m.user_id}`}>
                          <MoreVertical size={16} />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-48 rounded-2xl p-1.5">
                        <DropdownMenuItem className="rounded-xl font-semibold" onClick={() => handleTransfer(m)} data-testid={`transfer-owner-${m.user_id}`}>
                          <Crown size={15} className="mr-2" /> Transfer ownership
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem className="rounded-xl font-semibold text-destructive focus:text-destructive" onClick={() => handleKick(m)} data-testid={`kick-member-${m.user_id}`}>
                          <UserMinus size={15} className="mr-2" /> Kick from room
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </div>
              );
            })}
          </div>
        </aside>
      </div>
    </div>
  );
}

function MessageRow({ msg, grouped, onReply, onEdit, onDelete }) {
  if (msg.self) {
    return (
      <div className={`group flex items-end justify-end gap-2 ${grouped ? "mt-0.5" : "mt-3"}`} data-testid={`message-${msg.id}`}>
        {!msg.deleted && <MsgActions msg={msg} onReply={onReply} onEdit={onEdit} onDelete={onDelete} self />}
        <div className="flex max-w-[75%] flex-col items-end">
          <div className={`rounded-3xl rounded-br-md px-4 py-2.5 shadow-sm ${msg.deleted ? "bg-slate-200 text-slate-500" : "bg-primary text-white"}`}>
            {msg.replyTo && (
              <div className="mb-1.5 rounded-xl bg-white/15 px-3 py-1.5">
                <p className="text-xs font-extrabold text-white/90">{msg.replyTo.author}</p>
                <p className="truncate text-xs text-white/70">{msg.replyTo.text}</p>
              </div>
            )}
            <p className={`whitespace-pre-wrap break-words text-[15px] leading-relaxed ${msg.deleted ? "italic" : ""}`}>{msg.text}</p>
          </div>
          <span className="mr-1 mt-1 text-[11px] font-semibold text-slate-400">
            {clockTime(msg.createdAt)}{msg.edited && " · edited"}
          </span>
        </div>
      </div>
    );
  }
  return (
    <div className={`group flex items-end gap-2 ${grouped ? "mt-0.5" : "mt-3"}`} data-testid={`message-${msg.id}`}>
      <div className="w-9 shrink-0">
        {!grouped && (
          <Avatar className="h-9 w-9">
            <AvatarFallback>{initial(msg.author)}</AvatarFallback>
          </Avatar>
        )}
      </div>
      <div className="flex max-w-[75%] flex-col items-start">
        {!grouped && <span className="mb-0.5 ml-1 text-xs font-extrabold text-slate-500">{msg.author}</span>}
        <div className={`rounded-3xl rounded-bl-md border px-4 py-2.5 shadow-sm ${msg.deleted ? "border-slate-200 bg-slate-100 text-slate-500" : "border-slate-200 bg-white text-slate-800"}`}>
          {msg.replyTo && (
            <div className="mb-1.5 rounded-xl bg-accent/70 px-3 py-1.5">
              <p className="text-xs font-extrabold text-primary">{msg.replyTo.author}</p>
              <p className="truncate text-xs text-slate-500">{msg.replyTo.text}</p>
            </div>
          )}
          <p className={`whitespace-pre-wrap break-words text-[15px] leading-relaxed ${msg.deleted ? "italic" : ""}`}>{msg.text}</p>
        </div>
        <span className="ml-1 mt-1 text-[11px] font-semibold text-slate-400">
          {clockTime(msg.createdAt)}{msg.edited && " · edited"}
        </span>
      </div>
      {!msg.deleted && <MsgActions msg={msg} onReply={onReply} onEdit={onEdit} onDelete={onDelete} />}
    </div>
  );
}

function MsgActions({ msg, onReply, onEdit, onDelete, self }) {
  return (
    <div className={`flex items-center self-center opacity-0 transition-opacity group-hover:opacity-100 ${self ? "order-first" : ""}`}>
      <button onClick={() => onReply(msg)} className="grid h-8 w-8 place-items-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700" title="Reply" data-testid={`reply-message-${msg.id}`}>
        <Reply size={16} />
      </button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="grid h-8 w-8 place-items-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700" data-testid={`message-menu-${msg.id}`}>
            <MoreVertical size={16} />
          </button>
        </DropdownMenuTrigger>
        {/* Edit and delete are sender-only: the consumer filters both on sender=self.user,
            so offering them on someone else's message would only produce an error toast. */}
        <DropdownMenuContent align={self ? "start" : "end"} className="w-40 rounded-2xl p-1.5">
          <DropdownMenuItem className="rounded-xl font-semibold" onClick={() => onReply(msg)}>
            <Reply size={15} className="mr-2" /> Reply
          </DropdownMenuItem>
          {self && (
            <DropdownMenuItem className="rounded-xl font-semibold" onClick={() => onEdit(msg)} data-testid={`edit-message-${msg.id}`}>
              <Pencil size={15} className="mr-2" /> Edit
            </DropdownMenuItem>
          )}
          {self && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="rounded-xl font-semibold text-destructive focus:text-destructive" onClick={() => onDelete(msg)} data-testid={`delete-message-${msg.id}`}>
                <Trash2 size={15} className="mr-2" /> Delete
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
