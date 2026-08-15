import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Logo, StatusDot } from "@/components/Brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Plus, LogIn, Lock, Users, Bell, UserPlus, Check, X,
  MoreVertical, LogOut, Search, Hash, ArrowRight, UserMinus, MessageSquare,
  MailOpen, Info, ChevronDown, Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/App";
import { useSocket } from "@/lib/useSocket";
import { accentFor, fromNow, initial } from "@/lib/format";

let activitySeq = 0;
const nextActivityId = () => `a_${++activitySeq}`;

export default function Dashboard() {
  const navigate = useNavigate();
  const { user, setUser } = useAuth();

  const [friends, setFriends] = useState([]);
  const [requests, setRequests] = useState([]);
  const [invites, setInvites] = useState([]);
  // There is no notification model or read state on the backend (features.txt #8), so
  // this feed is seeded from whatever is still pending and then grown from live socket
  // events for the life of the page.
  const [notifs, setNotifs] = useState([]);
  const [busyInvite, setBusyInvite] = useState(null);

  // create room dialog
  const [createOpen, setCreateOpen] = useState(false);
  const [roomName, setRoomName] = useState("");
  const [roomProtected, setRoomProtected] = useState(false);
  const [roomPassword, setRoomPassword] = useState("");
  const [capacity, setCapacity] = useState(10);
  const [creating, setCreating] = useState(false);

  // join
  const [joinCode, setJoinCode] = useState("");
  const [joinProtected, setJoinProtected] = useState(false);
  const [joinPassword, setJoinPassword] = useState("");
  const [joining, setJoining] = useState(false);

  // add friend
  const [friendQuery, setFriendQuery] = useState("");

  const unreadNotifs = notifs.filter((n) => n.unread).length;

  const load = useCallback(async () => {
    try {
      const data = await api.dashboard();
      setFriends(data.friends);
      setRequests(data.pending_requests);
      setInvites(data.pending_invitations);
      setNotifs([
        ...data.pending_invitations.map((inv) => ({
          id: `inv_${inv.id}`,
          type: "room_invite",
          from: inv.sender_username,
          room: inv.room_name,
          roomCode: inv.room_code,
          invitationId: inv.id,
          time: fromNow(inv.created_at),
          unread: true,
        })),
        ...data.pending_requests.map((req) => ({
          id: `req_${req.id}`,
          type: "friend_request",
          from: req.sender_username,
          friendshipId: req.id,
          time: fromNow(req.created_at),
          unread: true,
        })),
      ]);
    } catch (err) {
      if (err.status === 401) {
        setUser(null);
        navigate("/login", { replace: true });
        return;
      }
      toast.error(err.message);
    }
  }, [navigate, setUser]);

  useEffect(() => {
    load();
  }, [load]);

  const pushActivity = (entry) =>
    setNotifs((list) => [{ id: nextActivityId(), unread: true, ...entry }, ...list]);

  const handleNotification = useCallback(
    (data) => {
      switch (data.type) {
        case "room_invitation_received": {
          const invite = {
            id: data.invitation_id,
            room_code: data.room_code,
            room_name: data.room_name,
            sender_username: data.sender_username,
            created_at: new Date().toISOString(),
          };
          setInvites((list) =>
            list.some((i) => i.id === invite.id) ? list : [invite, ...list]
          );
          setNotifs((list) => [
            {
              id: `inv_${data.invitation_id}`,
              type: "room_invite",
              from: data.sender_username,
              room: data.room_name,
              roomCode: data.room_code,
              invitationId: data.invitation_id,
              time: "just now",
              unread: true,
            },
            ...list,
          ]);
          toast.info(`${data.sender_username} invited you to ${data.room_name}`);
          break;
        }
        case "friend_request_received": {
          const req = {
            id: data.friendship_id,
            sender_id: data.sender_id,
            sender_username: data.sender_username,
            created_at: new Date().toISOString(),
          };
          setRequests((list) => (list.some((r) => r.id === req.id) ? list : [req, ...list]));
          setNotifs((list) => [
            {
              id: `req_${data.friendship_id}`,
              type: "friend_request",
              from: data.sender_username,
              friendshipId: data.friendship_id,
              time: "just now",
              unread: true,
            },
            ...list,
          ]);
          toast.info(`${data.sender_username} sent you a friend request`);
          break;
        }
        case "invite_response": {
          setBusyInvite(null);
          if (data.status === "accepted" && data.room_code) {
            // room_detail_api is what actually consumes the accepted invitation and
            // mints the session grant, so navigating there is a required step, not a
            // convenience.
            navigate(`/room/${data.room_code}`);
          } else if (data.status === "declined") {
            toast(data.message || "Invitation declined.");
          } else {
            toast.error(data.message || "Invitation not found.");
            load();
          }
          break;
        }
        case "error":
          setBusyInvite(null);
          toast.error(data.message);
          break;
        default:
          console.warn("[notifications] unhandled type:", data.type);
      }
    },
    [navigate, load]
  );

  const sendNotification = useSocket("/ws/notifications/", {
    onMessage: handleNotification,
  });

  const handleCreate = async () => {
    if (!roomName.trim()) return toast.error("Give your room a name");
    setCreating(true);
    try {
      const { room_code } = await api.createRoom({
        name: roomName,
        // The UI has no description field; the backend accepts one (features.txt #20).
        description: "",
        capacity,
        password: roomProtected ? roomPassword : "",
      });
      setCreateOpen(false);
      toast.success(`Room "${roomName}" created · code ${room_code}`);
      setRoomName(""); setRoomPassword(""); setRoomProtected(false); setCapacity(10);
      navigate(`/room/${room_code}`);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setCreating(false);
    }
  };

  const handleJoin = async (e) => {
    e.preventDefault();
    if (joinCode.trim().length !== 6) return toast.error("Room codes are 6 characters");
    setJoining(true);
    try {
      const { room_code } = await api.joinRoom({
        room_code: joinCode,
        password: joinProtected ? joinPassword : "",
      });
      navigate(`/room/${room_code}`);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setJoining(false);
    }
  };

  const handleAcceptReq = async (req) => {
    try {
      const res = await api.acceptFriendRequest(req.id);
      setRequests((r) => r.filter((x) => x.id !== req.id));
      setNotifs((list) => list.filter((n) => n.friendshipId !== req.id));
      toast.success(res.message);
      load();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleDeclineReq = async (req) => {
    try {
      await api.rejectFriendRequest(req.id);
      setRequests((r) => r.filter((x) => x.id !== req.id));
      setNotifs((list) => list.filter((n) => n.friendshipId !== req.id));
      toast("Request declined");
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleRemoveFriend = async (f) => {
    try {
      await api.removeFriend(f.friendship_id);
      setFriends((list) => list.filter((x) => x.friendship_id !== f.friendship_id));
      toast(`Removed ${f.username}`);
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleAddFriend = async () => {
    if (!friendQuery.trim()) return;
    try {
      const res = await api.sendFriendRequest(friendQuery.trim());
      toast.success(res.message);
      setFriendQuery("");
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleAcceptRoomInvite = (inv) => {
    setBusyInvite(inv.id);
    if (!sendNotification({ type: "accept_room_invite", invitation_id: inv.id })) {
      setBusyInvite(null);
      toast.error("Still connecting — try again in a moment.");
    }
  };

  const handleDeclineRoomInvite = (inv) => {
    if (!sendNotification({ type: "reject_room_invite", invitation_id: inv.id })) {
      toast.error("Still connecting — try again in a moment.");
      return;
    }
    setInvites((list) => list.filter((x) => x.id !== inv.id));
    setNotifs((list) => list.filter((n) => n.invitationId !== inv.id));
  };

  const handleNotifAction = (n, accept) => {
    if (n.type === "room_invite") {
      const inv = { id: n.invitationId };
      if (accept) handleAcceptRoomInvite(inv);
      else handleDeclineRoomInvite(inv);
      return;
    }
    const req = { id: n.friendshipId };
    if (accept) handleAcceptReq(req);
    else handleDeclineReq(req);
  };

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch {
      // Signing out locally is the right outcome even if the request failed.
    }
    setUser(null);
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Top bar */}
      <header className="sticky top-0 z-30 border-b border-border bg-white/80 backdrop-blur-xl" data-testid="dashboard-header">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3.5">
          <Logo size="sm" />
          <div className="flex items-center gap-2">
            <div className="relative">
              <Button variant="ghost" size="icon" className="rounded-full text-slate-500" data-testid="notifications-bell">
                <Bell size={20} />
              </Button>
              {unreadNotifs > 0 && (
                <span className="absolute -right-0.5 -top-0.5 grid h-5 w-5 place-items-center rounded-full bg-destructive text-[10px] font-extrabold text-white">
                  {unreadNotifs}
                </span>
              )}
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-2 rounded-full bg-secondary px-4 py-2 transition-colors hover:bg-accent" data-testid="user-menu-trigger">
                  <span className="text-sm font-bold text-slate-700">{user?.username}</span>
                  <ChevronDown size={16} className="text-slate-400" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52 rounded-2xl p-1.5">
                <div className="px-2 py-2">
                  <p className="text-sm font-bold text-slate-900">{user?.username}</p>
                  <p className="text-xs text-slate-400">{user?.email}</p>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="rounded-xl font-semibold text-destructive focus:text-destructive"
                  onClick={handleLogout}
                  data-testid="logout-button"
                >
                  <LogOut size={16} className="mr-2" /> Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-6 px-6 py-8 lg:grid-cols-[1fr_360px]">
        {/* Main column */}
        <div className="space-y-6">
          <div className="rc-fade-up">
            <h1 className="text-3xl font-extrabold text-slate-900">
              Hi, {user?.username} 👋
            </h1>
            <p className="mt-1 text-slate-500">Create a room or hop into one with a code.</p>
          </div>

          {/* Create + Join */}
          <div className="grid gap-4 sm:grid-cols-2">
            {/* Create card */}
            <Dialog open={createOpen} onOpenChange={setCreateOpen}>
              <DialogTrigger asChild>
                <button
                  className="group flex h-full flex-col justify-between rounded-3xl bg-primary p-6 text-left text-white shadow-floating transition-all hover:-translate-y-1"
                  data-testid="open-create-room-button"
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="grid h-12 w-12 place-items-center rounded-2xl bg-white/20">
                        <Plus size={24} />
                      </span>
                      <Sparkles size={20} className="text-white/50" />
                    </div>
                    <h3 className="mt-4 text-xl font-extrabold">Create a room</h3>
                    <p className="mt-1 text-sm text-white/80">Spin up a space and invite people with a code.</p>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs font-bold">
                        <Users size={13} /> 2–100 members
                      </span>
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs font-bold">
                        <Lock size={13} /> Optional password
                      </span>
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs font-bold">
                        <Hash size={13} /> Shareable code
                      </span>
                    </div>
                  </div>
                  <span className="mt-6 inline-flex w-full items-center justify-center gap-1.5 rounded-full bg-white py-3 text-sm font-extrabold text-primary transition-transform group-hover:scale-[1.02]">
                    Create new room <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
                  </span>
                </button>
              </DialogTrigger>
              <DialogContent className="rounded-3xl sm:max-w-md" data-testid="create-room-dialog">
                <DialogHeader>
                  <DialogTitle className="text-2xl font-extrabold">Create a room</DialogTitle>
                  <DialogDescription>Set up your space and invite people with a code.</DialogDescription>
                </DialogHeader>
                <div className="space-y-5 py-2">
                  <div className="space-y-2">
                    <Label className="font-bold text-slate-700">Room name</Label>
                    <Input
                      value={roomName}
                      onChange={(e) => setRoomName(e.target.value)}
                      placeholder="e.g. Design Guild"
                      maxLength={100}
                      className="h-12 rounded-2xl focus-visible:ring-2 focus-visible:ring-primary/30"
                      data-testid="create-room-name-input"
                    />
                  </div>
                  <div className="flex items-center justify-between rounded-2xl bg-secondary/60 p-4">
                    <div className="flex items-center gap-3">
                      <Lock size={18} className="text-slate-500" />
                      <div>
                        <p className="font-bold text-slate-700">Password protect</p>
                        <p className="text-xs text-slate-400">Require a password to join</p>
                      </div>
                    </div>
                    <Switch checked={roomProtected} onCheckedChange={setRoomProtected} data-testid="create-room-protect-switch" />
                  </div>
                  {roomProtected && (
                    <div className="space-y-2 rc-pop">
                      <Label className="font-bold text-slate-700">Room password</Label>
                      <Input
                        type="password"
                        value={roomPassword}
                        onChange={(e) => setRoomPassword(e.target.value)}
                        placeholder="••••••••"
                        className="h-12 rounded-2xl focus-visible:ring-2 focus-visible:ring-primary/30"
                        data-testid="create-room-password-input"
                      />
                    </div>
                  )}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Label className="font-bold text-slate-700">Capacity</Label>
                      <Badge className="rounded-full bg-accent text-accent-foreground hover:bg-accent" data-testid="capacity-value">
                        {capacity} members
                      </Badge>
                    </div>
                    <Slider
                      value={[capacity]}
                      min={2}
                      max={100}
                      step={1}
                      onValueChange={(v) => setCapacity(v[0])}
                      data-testid="create-room-capacity-slider"
                    />
                    <div className="flex justify-between text-xs font-semibold text-slate-400">
                      <span>2</span><span>100</span>
                    </div>
                  </div>
                </div>
                <DialogFooter>
                  <Button
                    className="h-11 w-full rounded-full font-bold"
                    onClick={handleCreate}
                    disabled={creating}
                    data-testid="confirm-create-room-button"
                  >
                    {creating ? "Creating…" : "Create room"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>

            {/* Join card */}
            <div className="rounded-3xl bg-card p-6 shadow-soft">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-accent text-primary">
                <LogIn size={22} />
              </span>
              <h3 className="mt-4 text-xl font-extrabold text-slate-900">Join a room</h3>
              <p className="mt-1 text-sm text-slate-400">Enter a 6-character room code.</p>
              <form onSubmit={handleJoin} className="mt-4 space-y-3" data-testid="join-room-form">
                <div className="relative">
                  <Hash size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                  <Input
                    value={joinCode}
                    onChange={(e) => setJoinCode(e.target.value.toUpperCase().slice(0, 6))}
                    placeholder="DSN9Q2"
                    maxLength={6}
                    className="h-12 rounded-2xl pl-11 font-mono text-lg font-bold tracking-widest uppercase focus-visible:ring-2 focus-visible:ring-primary/30"
                    data-testid="join-code-input"
                  />
                </div>
                <label className="flex items-center gap-2 text-sm font-semibold text-slate-500">
                  <Switch checked={joinProtected} onCheckedChange={setJoinProtected} data-testid="join-protected-switch" />
                  This room has a password
                </label>
                {joinProtected && (
                  <Input
                    type="password"
                    value={joinPassword}
                    onChange={(e) => setJoinPassword(e.target.value)}
                    placeholder="Room password"
                    className="h-12 rounded-2xl rc-pop focus-visible:ring-2 focus-visible:ring-primary/30"
                    data-testid="join-password-input"
                  />
                )}
                <Button
                  type="submit"
                  variant="outline"
                  disabled={joining}
                  className="h-11 w-full rounded-full border-2 font-bold"
                  data-testid="join-room-button"
                >
                  {joining ? "Joining…" : "Join room"}
                </Button>
              </form>
            </div>
          </div>

          {/* Room invitations */}
          <div className="rc-fade-up">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-xl font-extrabold text-slate-900">
                <MailOpen size={20} className="text-primary" /> Room invitations
              </h2>
              <span className="text-sm font-bold text-slate-400">{invites.length} pending</span>
            </div>

            <div className="mt-3 flex items-center gap-2 rounded-2xl bg-accent/60 px-4 py-2.5 text-sm font-semibold text-accent-foreground">
              <Info size={16} className="shrink-0" />
              You can be in one room at a time — joining a room leaves your current one.
            </div>

            {invites.length === 0 ? (
              <div className="mt-4 flex flex-col items-center rounded-3xl bg-card py-14 text-center shadow-soft" data-testid="no-invitations">
                <span className="grid h-14 w-14 place-items-center rounded-2xl bg-secondary text-slate-400">
                  <MailOpen size={26} />
                </span>
                <p className="mt-4 font-extrabold text-slate-700">No invitations right now</p>
                <p className="mt-1 text-sm text-slate-400">When a friend invites you to their room, it shows up here.</p>
              </div>
            ) : (
              <div className="mt-4 space-y-4">
                {invites.map((inv) => (
                  <InvitationCard
                    key={inv.id}
                    inv={inv}
                    busy={busyInvite === inv.id}
                    onAccept={handleAcceptRoomInvite}
                    onDecline={handleDeclineRoomInvite}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <aside className="rc-fade-up" style={{ animationDelay: "80ms" }}>
          <div className="sticky top-[76px] rounded-3xl bg-card p-2 shadow-soft">
            <Tabs defaultValue="friends">
              <TabsList className="grid w-full grid-cols-2 rounded-2xl bg-secondary p-1">
                <TabsTrigger value="friends" className="rounded-xl font-bold data-[state=active]:bg-white data-[state=active]:shadow-sm" data-testid="tab-friends">
                  Friends
                </TabsTrigger>
                <TabsTrigger value="notifs" className="rounded-xl font-bold data-[state=active]:bg-white data-[state=active]:shadow-sm" data-testid="tab-notifications">
                  Activity
                  {unreadNotifs > 0 && (
                    <span className="ml-1.5 grid h-5 min-w-5 place-items-center rounded-full bg-primary px-1 text-[10px] font-extrabold text-white">
                      {unreadNotifs}
                    </span>
                  )}
                </TabsTrigger>
              </TabsList>

              {/* Friends */}
              <TabsContent value="friends" className="p-2">
                <div className="relative">
                  <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                  <Input
                    value={friendQuery}
                    onChange={(e) => setFriendQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleAddFriend()}
                    placeholder="Add friend by username"
                    className="h-11 rounded-2xl border-slate-200 pl-10 pr-11 focus-visible:ring-2 focus-visible:ring-primary/30"
                    data-testid="add-friend-input"
                  />
                  <button
                    onClick={handleAddFriend}
                    className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full bg-primary text-white transition-colors hover:bg-primary/90"
                    data-testid="add-friend-button"
                  >
                    <UserPlus size={15} />
                  </button>
                </div>

                {requests.length > 0 && (
                  <div className="mt-4">
                    <p className="px-1 text-xs font-extrabold uppercase tracking-wide text-slate-400">
                      Requests · {requests.length}
                    </p>
                    <div className="mt-2 space-y-2">
                      {requests.map((u) => (
                        <div key={u.id} className="flex items-center gap-3 rounded-2xl bg-accent/60 p-2.5" data-testid={`friend-request-${u.id}`}>
                          <Avatar className="h-10 w-10">
                            <AvatarFallback>{initial(u.sender_username)}</AvatarFallback>
                          </Avatar>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-bold text-slate-800">{u.sender_username}</p>
                            <p className="text-xs text-slate-400">{fromNow(u.created_at)}</p>
                          </div>
                          <button
                            onClick={() => handleAcceptReq(u)}
                            className="grid h-8 w-8 place-items-center rounded-full bg-primary text-white hover:bg-primary/90"
                            data-testid={`accept-request-${u.id}`}
                          >
                            <Check size={16} />
                          </button>
                          <button
                            onClick={() => handleDeclineReq(u)}
                            className="grid h-8 w-8 place-items-center rounded-full bg-white text-slate-500 hover:bg-slate-100"
                            data-testid={`decline-request-${u.id}`}
                          >
                            <X size={16} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mt-4">
                  <p className="px-1 text-xs font-extrabold uppercase tracking-wide text-slate-400">
                    Friends · {friends.length}
                  </p>
                  <div className="mt-2 max-h-[42vh] space-y-1 overflow-y-auto rc-scroll pr-1">
                    {friends.length === 0 && (
                      <p className="px-1 py-6 text-center text-sm text-slate-400">
                        No friends yet — add someone by username above.
                      </p>
                    )}
                    {friends.map((u) => {
                      // The backend's only presence signal is which room a friend is
                      // connected to right now (features.txt #4): "in a room" is the one
                      // thing we can state truthfully, so anything else reads as offline.
                      const inRoom = Boolean(u.current_room_code);
                      return (
                        <div key={u.friendship_id} className="group flex items-center gap-3 rounded-2xl p-2 transition-colors hover:bg-secondary" data-testid={`friend-${u.friendship_id}`}>
                          <div className="relative">
                            <Avatar className="h-10 w-10">
                              <AvatarFallback>{initial(u.username)}</AvatarFallback>
                            </Avatar>
                            <span className="absolute -bottom-0.5 -right-0.5">
                              <StatusDot status={inRoom ? "online" : "offline"} />
                            </span>
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-bold text-slate-800">{u.username}</p>
                            <p className="truncate text-xs text-slate-400">
                              {inRoom ? `In ${u.current_room_name}` : "Offline"}
                            </p>
                          </div>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <button className="grid h-8 w-8 place-items-center rounded-full text-slate-400 opacity-0 transition-opacity hover:bg-slate-100 group-hover:opacity-100" data-testid={`friend-menu-${u.friendship_id}`}>
                                <MoreVertical size={16} />
                              </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-44 rounded-2xl p-1.5">
                              <DropdownMenuItem
                                className="rounded-xl font-semibold"
                                onClick={() => toast("Direct messages aren't available yet.")}
                              >
                                <MessageSquare size={15} className="mr-2" /> Message
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                className="rounded-xl font-semibold text-destructive focus:text-destructive"
                                onClick={() => handleRemoveFriend(u)}
                                data-testid={`remove-friend-${u.friendship_id}`}
                              >
                                <UserMinus size={15} className="mr-2" /> Remove friend
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </TabsContent>

              {/* Notifications */}
              <TabsContent value="notifs" className="p-2" data-testid="notifications-panel">
                {notifs.length === 0 ? (
                  <div className="flex flex-col items-center py-12 text-center text-slate-400">
                    <Bell size={32} />
                    <p className="mt-3 font-bold">You're all caught up</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {notifs.map((n) => (
                      <div
                        key={n.id}
                        className={`rounded-2xl p-3 ${n.unread ? "bg-accent/60" : "bg-secondary/40"}`}
                        data-testid={`notification-${n.id}`}
                      >
                        {n.type === "system" ? (
                          <p className="text-sm text-slate-600">{n.text}</p>
                        ) : (
                          <div className="flex gap-3">
                            <Avatar className="h-10 w-10">
                              <AvatarFallback>{initial(n.from)}</AvatarFallback>
                            </Avatar>
                            <div className="min-w-0 flex-1">
                              <p className="text-sm leading-snug text-slate-700">
                                <span className="font-bold">{n.from}</span>{" "}
                                {n.type === "room_invite" ? (
                                  <>invited you to <span className="font-bold">{n.room}</span></>
                                ) : (
                                  "sent you a friend request"
                                )}
                              </p>
                              <p className="mt-0.5 text-xs text-slate-400">{n.time}</p>
                              <div className="mt-2 flex gap-2">
                                <Button
                                  size="sm"
                                  className="h-8 rounded-full px-4 text-xs font-bold"
                                  onClick={() => handleNotifAction(n, true)}
                                  data-testid={`accept-notification-${n.id}`}
                                >
                                  Accept
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-8 rounded-full px-4 text-xs font-bold text-slate-500"
                                  onClick={() => handleNotifAction(n, false)}
                                  data-testid={`decline-notification-${n.id}`}
                                >
                                  Decline
                                </Button>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </div>
        </aside>
      </main>
    </div>
  );
}

function InvitationCard({ inv, busy, onAccept, onDecline }) {
  const accent = accentFor(inv.room_code);
  // members / capacity / online are not in any invitation payload yet — see
  // features.txt #1. The chips and the fill bar stay so the layout is ready for them.
  const members = inv.members;
  const capacity = inv.capacity;
  const online = inv.online;
  const known = Number.isFinite(members) && Number.isFinite(capacity);
  const fill = known ? Math.round((members / capacity) * 100) : 0;

  return (
    <div className="rounded-3xl bg-card p-5 shadow-soft transition-all hover:shadow-floating" data-testid={`room-invite-${inv.id}`}>
      <div className="flex items-start gap-4">
        <span
          className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl text-xl font-extrabold text-white"
          style={{ backgroundColor: accent }}
        >
          {initial(inv.room_name)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-extrabold text-slate-900">{inv.room_name}</h3>
            {inv.is_protected && (
              <Badge className="rounded-full bg-secondary text-slate-600 hover:bg-secondary">
                <Lock size={12} className="mr-1" /> Protected
              </Badge>
            )}
          </div>
          <div className="mt-1 flex items-center gap-2 text-sm text-slate-500">
            <Avatar className="h-5 w-5">
              <AvatarFallback className="text-[10px]">{initial(inv.sender_username)}</AvatarFallback>
            </Avatar>
            <span>
              <span className="font-bold text-slate-700">{inv.sender_username}</span> invited you · {fromNow(inv.created_at)}
            </span>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <span
              className="flex items-center gap-1.5 font-bold text-slate-500"
              title={known ? undefined : "Member counts aren't published for invitations yet."}
            >
              <Users size={15} /> {known ? `${members}/${capacity}` : "—"}
            </span>
            <span
              className={`flex items-center gap-1.5 font-bold ${
                Number.isFinite(online) ? "text-green-600" : "text-slate-400"
              }`}
              title={Number.isFinite(online) ? undefined : "Online counts aren't published for invitations yet."}
            >
              <span className={`h-2 w-2 rounded-full ${Number.isFinite(online) ? "bg-green-500" : "bg-slate-300"}`} />
              {Number.isFinite(online) ? `${online} online` : "— online"}
            </span>
            <span className="font-mono text-xs font-bold text-slate-400">{inv.room_code}</span>
          </div>
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-secondary">
            <div className="h-full rounded-full" style={{ width: `${fill}%`, backgroundColor: accent }} />
          </div>
        </div>
      </div>

      {/* No password field: an accepted invitation IS the key. room_detail_api consumes
          the invitation row and mints the session grant, which is exactly what a correct
          password would have done. See features.txt "Deliberate deviations". */}

      <div className="mt-4 flex gap-2">
        <Button
          className="h-11 flex-1 rounded-full font-bold shadow-floating transition-transform hover:-translate-y-0.5"
          onClick={() => onAccept(inv)}
          disabled={busy}
          data-testid={`accept-invite-${inv.id}`}
        >
          <LogIn size={17} className="mr-1.5" /> {busy ? "Joining…" : "Join room"}
        </Button>
        <Button
          variant="ghost"
          className="h-11 rounded-full px-6 font-bold text-slate-500"
          onClick={() => onDecline(inv)}
          disabled={busy}
          data-testid={`decline-invite-${inv.id}`}
        >
          Decline
        </Button>
      </div>
    </div>
  );
}
