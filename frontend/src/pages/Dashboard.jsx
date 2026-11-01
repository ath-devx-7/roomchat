import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Logo, StatusDot } from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";
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
  Plus, LogIn, Lock, Users, UserPlus, Check, X,
  MoreVertical, LogOut, Hash, UserMinus, Info, ChevronDown,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/App";
import { useSocket } from "@/lib/useSocket";
import { fromNow, initial, paperFor } from "@/lib/format";

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

  // sidebar tab, controlled so the marker under it can slide
  const [tab, setTab] = useState("friends");

  // A code typed on the landing page arrives as ?code=XXXXXX (via Login/Register): put it in
  // the join box, cleaned the same way the input cleans typing. The user still presses Join.
  const [params] = useSearchParams();
  useEffect(() => {
    const preset = params.get("code");
    if (preset) setJoinCode(preset.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6));
  }, [params]);

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
      toast.error("Still connecting. Try again in a moment.");
    }
  };

  const handleDeclineRoomInvite = (inv) => {
    if (!sendNotification({ type: "reject_room_invite", invitation_id: inv.id })) {
      toast.error("Still connecting. Try again in a moment.");
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
    <div className="min-h-screen bg-paper">
      {/* Top bar: solid paper under a hairline, no glass */}
      <header className="sticky top-0 z-30 border-b border-rule bg-paper" data-testid="dashboard-header">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between px-4 py-3 sm:px-6 lg:px-16">
          <Logo size="sm" />
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  className="flex h-10 items-center gap-2 bg-paper-3 px-3 text-sm font-medium text-ink shadow-card transition-colors hover:bg-hover"
                  data-testid="user-menu-trigger"
                >
                  {user?.username}
                  <ChevronDown size={16} className="text-ink-3" aria-hidden="true" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <div className="px-2 py-2">
                  <p className="text-sm font-medium text-ink">{user?.username}</p>
                  <p className="text-xs text-ink-3">{user?.email}</p>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="text-error focus:text-error"
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

      <main className="mx-auto grid max-w-[1440px] gap-8 px-4 py-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:px-16 lg:py-12">
        {/* Main column */}
        <div className="min-w-0 space-y-12">
          <div>
            <h1 className="text-[56px] text-ink">Hi, {user?.username}</h1>
            <p className="mt-2 text-ink-3">Create a room or hop into one with a code.</p>
          </div>

          {/* Join + Create: joining by code leads on a copy sheet; creating is the screen's one
              fluorescent sheet, pasted on at a slight tilt. */}
          <section className="grid items-start gap-8 md:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
            {/* Join */}
            <div className="sheet p-6 lg:p-8">
              <h2 className="text-[40px] text-ink">Join a room</h2>
              <p className="mt-1 text-sm text-ink-3">Enter a 6-character room code.</p>
              <form onSubmit={handleJoin} className="mt-6 space-y-4" data-testid="join-room-form">
                <label htmlFor="join-code" className="visually-hidden">Room code</label>
                <Input
                  id="join-code"
                  value={joinCode}
                  onChange={(e) => setJoinCode(e.target.value.toUpperCase().slice(0, 6))}
                  placeholder="DSN9Q2"
                  maxLength={6}
                  autoComplete="off"
                  spellCheck={false}
                  className="code-figure h-20 max-w-[18rem] px-4 text-[56px]"
                  data-testid="join-code-input"
                />
                <label className="flex items-center gap-3 text-sm text-ink-2">
                  <Switch checked={joinProtected} onCheckedChange={setJoinProtected} data-testid="join-protected-switch" />
                  This room has a password
                </label>
                {joinProtected && (
                  <div className="max-w-[16rem] space-y-2">
                    <Label htmlFor="join-password">Room password</Label>
                    <Input
                      id="join-password"
                      type="password"
                      value={joinPassword}
                      onChange={(e) => setJoinPassword(e.target.value)}
                      data-testid="join-password-input"
                    />
                  </div>
                )}
                <Button type="submit" disabled={joining} className="min-w-[10rem]" data-testid="join-room-button">
                  {joining ? "Joining…" : "Join room"}
                </Button>
              </form>
            </div>

            {/* Create */}
            <div className="sheet-fluoro flex flex-col justify-between gap-6 p-6 md:rotate-1 lg:p-8">
              <div>
                <h2 className="text-[40px]">Create a room</h2>
                <p className="mt-1 text-sm">Spin up a space and invite people with a code.</p>
                <ul className="mt-6 space-y-2 text-sm">
                  <li className="flex items-center gap-2"><Users size={15} aria-hidden="true" /><span><span className="measure">2</span> to <span className="measure">100</span> members</span></li>
                  <li className="flex items-center gap-2"><Lock size={15} aria-hidden="true" /> Optional password</li>
                  <li className="flex items-center gap-2"><Hash size={15} aria-hidden="true" /> Shareable code</li>
                </ul>
              </div>
              <Dialog open={createOpen} onOpenChange={setCreateOpen}>
                <DialogTrigger asChild>
                  <Button variant="outline" className="self-start" data-testid="open-create-room-button">
                    <Plus size={16} /> Create new room
                  </Button>
                </DialogTrigger>
                <DialogContent className="sm:max-w-md" data-testid="create-room-dialog">
                  <DialogHeader>
                    <DialogTitle className="font-display text-[40px] font-normal uppercase leading-none">Create a room</DialogTitle>
                    <DialogDescription>Set up your space and invite people with a code.</DialogDescription>
                  </DialogHeader>
                  <div className="space-y-6 py-2">
                    <div className="space-y-2">
                      <Label htmlFor="create-room-name">Room name</Label>
                      <Input
                        id="create-room-name"
                        value={roomName}
                        onChange={(e) => setRoomName(e.target.value)}
                        placeholder="e.g. Design Guild"
                        maxLength={100}
                        data-testid="create-room-name-input"
                      />
                    </div>
                    <div className="flex items-center justify-between gap-4 border-y border-rule py-4">
                      <div>
                        <Label htmlFor="create-room-protect">Password protect</Label>
                        <p className="mt-1 text-xs text-ink-3">Require a password to join</p>
                      </div>
                      <Switch id="create-room-protect" checked={roomProtected} onCheckedChange={setRoomProtected} data-testid="create-room-protect-switch" />
                    </div>
                    {roomProtected && (
                      <div className="space-y-2">
                        <Label htmlFor="create-room-password">Room password</Label>
                        <Input
                          id="create-room-password"
                          type="password"
                          value={roomPassword}
                          onChange={(e) => setRoomPassword(e.target.value)}
                          data-testid="create-room-password-input"
                        />
                      </div>
                    )}
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <Label id="create-room-capacity-label">Capacity</Label>
                        <span className="text-sm text-ink-2" data-testid="capacity-value">
                          <span className="measure font-medium text-ink">{capacity}</span> members
                        </span>
                      </div>
                      <Slider
                        value={[capacity]}
                        min={2}
                        max={100}
                        step={1}
                        onValueChange={(v) => setCapacity(v[0])}
                        aria-labelledby="create-room-capacity-label"
                        data-testid="create-room-capacity-slider"
                      />
                      <div className="measure flex justify-between text-xs text-ink-3">
                        <span>2</span><span>100</span>
                      </div>
                    </div>
                  </div>
                  <DialogFooter>
                    <Button
                      className="w-full"
                      onClick={handleCreate}
                      disabled={creating}
                      data-testid="confirm-create-room-button"
                    >
                      {creating ? "Creating…" : "Create room"}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </div>
          </section>

          {/* Room invitations */}
          <section>
            <div className="flex items-baseline justify-between gap-4 border-b border-rule pb-3">
              <h2 className="text-[40px] text-ink">Room invitations</h2>
              <span className="text-sm text-ink-3"><span className="measure">{invites.length}</span> pending</span>
            </div>
            <p className="mt-3 flex items-center gap-2 text-sm text-ink-3">
              <Info size={15} className="shrink-0" aria-hidden="true" />
              You can be in one room at a time: joining a room leaves your current one.
            </p>

            {invites.length === 0 ? (
              <div className="sheet mt-6 px-6 py-10" data-testid="no-invitations">
                <p className="font-medium text-ink-2">No invitations right now</p>
                <p className="mt-1 text-sm text-ink-3">When a friend invites you to their room, it shows up here.</p>
              </div>
            ) : (
              <ul className="sheet mt-6 px-5">
                {invites.map((inv) => (
                  <InvitationCard
                    key={inv.id}
                    inv={inv}
                    busy={busyInvite === inv.id}
                    onAccept={handleAcceptRoomInvite}
                    onDecline={handleDeclineRoomInvite}
                  />
                ))}
              </ul>
            )}
          </section>
        </div>

        {/* Sidebar: one ruled panel; rows inside are parted by hairlines, never boxed again */}
        <aside className="min-w-0">
          <div className="sheet sticky top-24">
            <Tabs value={tab} onValueChange={setTab}>
              <TabsList className="relative grid w-full grid-cols-2">
                {/* The marker under the current tab, moved by transform (never width) */}
                <span
                  aria-hidden="true"
                  className={`absolute bottom-0 left-0 h-0.5 w-1/2 bg-ink transition-transform duration-short ease-out ${tab === "notifs" ? "translate-x-full" : ""}`}
                />
                <TabsTrigger value="friends" className="data-[state=active]:shadow-none" data-testid="tab-friends">
                  Friends
                </TabsTrigger>
                <TabsTrigger value="notifs" className="data-[state=active]:shadow-none" data-testid="tab-notifications">
                  Activity
                  {unreadNotifs > 0 && (
                    <span className="measure ml-2 grid h-5 min-w-5 place-items-center bg-signal px-1 text-xs text-signal-ink">
                      {unreadNotifs}
                    </span>
                  )}
                </TabsTrigger>
              </TabsList>

              {/* Friends */}
              <TabsContent value="friends" className="mt-0 p-4">
                <div className="flex gap-2">
                  <Input
                    value={friendQuery}
                    onChange={(e) => setFriendQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleAddFriend()}
                    placeholder="Add friend by username"
                    aria-label="Add friend by username"
                    data-testid="add-friend-input"
                  />
                  <Button
                    size="icon"
                    variant="outline"
                    onClick={handleAddFriend}
                    aria-label="Send friend request"
                    className="shrink-0"
                    data-testid="add-friend-button"
                  >
                    <UserPlus size={16} />
                  </Button>
                </div>

                {requests.length > 0 && (
                  <div className="mt-6">
                    <h3 className="text-sm font-medium tracking-normal text-ink-3">
                      Requests <span className="measure">{requests.length}</span>
                    </h3>
                    <ul className="mt-2 border-t border-rule-2">
                      {requests.map((u) => (
                        <li key={u.id} className="flex items-center gap-3 border-b border-rule-2 py-2.5" data-testid={`friend-request-${u.id}`}>
                          <Avatar className="h-9 w-9">
                            <AvatarFallback style={{ backgroundColor: paperFor(u.sender_username) }}>{initial(u.sender_username)}</AvatarFallback>
                          </Avatar>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium text-ink">{u.sender_username}</p>
                            <p className="text-xs text-ink-3">{fromNow(u.created_at)}</p>
                          </div>
                          <Button
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => handleAcceptReq(u)}
                            aria-label={`Accept friend request from ${u.sender_username}`}
                            data-testid={`accept-request-${u.id}`}
                          >
                            <Check size={16} />
                          </Button>
                          <Button
                            size="icon"
                            variant="outline"
                            className="h-8 w-8"
                            onClick={() => handleDeclineReq(u)}
                            aria-label={`Decline friend request from ${u.sender_username}`}
                            data-testid={`decline-request-${u.id}`}
                          >
                            <X size={16} />
                          </Button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="mt-6">
                  <h3 className="text-sm font-medium tracking-normal text-ink-3">
                    Friends <span className="measure">{friends.length}</span>
                  </h3>
                  <ul className="rc-scroll mt-2 max-h-[42vh] overflow-y-auto border-t border-rule-2">
                    {friends.length === 0 && (
                      <li className="py-6 text-sm text-ink-3">
                        No friends yet. Add someone by username above.
                      </li>
                    )}
                    {friends.map((u) => {
                      // The backend's only presence signal is which room a friend is
                      // connected to right now (features.txt #4): "in a room" is the one
                      // thing we can state truthfully, so anything else reads as offline.
                      const inRoom = Boolean(u.current_room_code);
                      return (
                        <li key={u.friendship_id} className="flex items-center gap-3 border-b border-rule-2 py-2 transition-colors hover:bg-hover" data-testid={`friend-${u.friendship_id}`}>
                          <div className="relative">
                            <Avatar className="h-9 w-9">
                              <AvatarFallback style={{ backgroundColor: paperFor(u.username) }}>{initial(u.username)}</AvatarFallback>
                            </Avatar>
                            <span className="absolute -bottom-0.5 -right-0.5">
                              <StatusDot status={inRoom ? "online" : "offline"} />
                            </span>
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium text-ink">{u.username}</p>
                            <p className="truncate text-xs text-ink-3">
                              {inRoom ? `In ${u.current_room_name}` : "Offline"}
                            </p>
                          </div>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                size="icon"
                                variant="ghost"
                                className="h-8 w-8 text-ink-3"
                                aria-label={`Options for ${u.username}`}
                                data-testid={`friend-menu-${u.friendship_id}`}
                              >
                                <MoreVertical size={16} />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-44">
                              <DropdownMenuItem
                                className="text-error focus:text-error"
                                onClick={() => handleRemoveFriend(u)}
                                data-testid={`remove-friend-${u.friendship_id}`}
                              >
                                <UserMinus size={15} className="mr-2" /> Remove friend
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              </TabsContent>

              {/* Notifications */}
              <TabsContent value="notifs" className="mt-0 p-4" data-testid="notifications-panel">
                {notifs.length === 0 ? (
                  <p className="py-10 text-sm text-ink-3">You’re all caught up.</p>
                ) : (
                  <ul className="border-t border-rule-2">
                    {notifs.map((n) => (
                      <li
                        key={n.id}
                        className={`border-b border-rule-2 px-2 py-3 ${n.unread ? "bg-hover" : ""}`}
                        data-testid={`notification-${n.id}`}
                      >
                        {n.type === "system" ? (
                          <p className="text-sm text-ink-2">{n.text}</p>
                        ) : (
                          <div className="flex gap-3">
                            <Avatar className="h-9 w-9">
                              <AvatarFallback style={{ backgroundColor: paperFor(n.from) }}>{initial(n.from)}</AvatarFallback>
                            </Avatar>
                            <div className="min-w-0 flex-1">
                              <p className="text-sm leading-snug text-ink-2">
                                <span className="font-medium text-ink">{n.from}</span>{" "}
                                {n.type === "room_invite" ? (
                                  <>invited you to <span className="font-medium text-ink">{n.room}</span></>
                                ) : (
                                  "sent you a friend request"
                                )}
                              </p>
                              <p className="mt-0.5 text-xs text-ink-3">{n.time}</p>
                              <div className="mt-2 flex gap-2">
                                <Button
                                  size="sm"
                                  onClick={() => handleNotifAction(n, true)}
                                  data-testid={`accept-notification-${n.id}`}
                                >
                                  Accept
                                </Button>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => handleNotifAction(n, false)}
                                  data-testid={`decline-notification-${n.id}`}
                                >
                                  Decline
                                </Button>
                              </div>
                            </div>
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </TabsContent>
            </Tabs>
          </div>
        </aside>
      </main>
    </div>
  );
}

/** One pending room invitation, as a ruled row: the room, who sent it and when, its code,
 *  and Join / Decline. */
function InvitationCard({ inv, busy, onAccept, onDecline }) {
  // members / capacity / online are not in any invitation payload yet (features.txt #1),
  // so the row shows only what the payload has instead of placeholder dashes.
  return (
    <li className="flex flex-wrap items-center gap-4 border-b border-rule-2 py-4 last:border-b-0" data-testid={`room-invite-${inv.id}`}>
      <span
        className="grid h-11 w-11 shrink-0 place-items-center text-lg font-medium text-room-ink"
        style={{ backgroundColor: paperFor(inv.room_code) }}
        aria-hidden="true"
      >
        {initial(inv.room_name)}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-base font-medium tracking-normal text-ink">{inv.room_name}</h3>
          {inv.is_protected && (
            <Badge>
              <Lock size={12} className="mr-1" aria-hidden="true" /> Protected
            </Badge>
          )}
        </div>
        <p className="mt-0.5 text-sm text-ink-3">
          <span className="font-medium text-ink-2">{inv.sender_username}</span> invited you {fromNow(inv.created_at)}
        </p>
      </div>
      <span className="code-figure text-2xl text-ink">{inv.room_code}</span>

      {/* No password field: an accepted invitation IS the key. room_detail_api consumes
          the invitation row and mints the session grant, which is exactly what a correct
          password would have done. See features.txt "Deliberate deviations". */}

      <div className="flex gap-2">
        <Button
          onClick={() => onAccept(inv)}
          disabled={busy}
          data-testid={`accept-invite-${inv.id}`}
        >
          <LogIn size={16} /> {busy ? "Joining…" : "Join room"}
        </Button>
        <Button
          variant="outline"
          onClick={() => onDecline(inv)}
          disabled={busy}
          data-testid={`decline-invite-${inv.id}`}
        >
          Decline
        </Button>
      </div>
    </li>
  );
}
