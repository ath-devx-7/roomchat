import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Braces, Component, Cookie, Crown, Database, FlaskConical, GripHorizontal, Lock, MoreVertical, Play, Radio, Search, Server, ShieldCheck, UserMinus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";
import { Board, Pin } from "@/components/board/Board";
import DemoRoom from "@/components/landing/DemoRoom";
import { AccessGate, ArchDiagram, CloseCodes, Lifecycle, MiddlewareStack, SchemaCards } from "@/components/landing/TechParts";
import { FEATURES, FLOW, STACK, STATS, TICKER } from "@/lib/techFacts";
import { initial, paperFor } from "@/lib/format";
import { useReveal } from "@/hooks/useReveal";
import { useAuth } from "@/App";

/** "Got a code?": six cells over one real input. Typing fills the cells (letters and digits
 *  only, upper-cased); a full code sends you to that room, through log in when needed. */
function CodeBox() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [code, setCode] = useState("");
  const [focused, setFocused] = useState(false);

  const go = (e) => {
    e.preventDefault();
    if (code.length !== 6) return;
    // Signed in: straight to the dashboard's join box. Otherwise log in first; Login carries
    // the code on (router state) and lands on the dashboard with it filled in.
    if (user) navigate(`/dashboard?code=${code}`);
    else navigate("/login", { state: { code } });
  };

  return (
    <form onSubmit={go} className="flex flex-col gap-5" data-testid="landing-code-form">
      <label className="relative block w-fit focus-within:outline focus-within:outline-2 focus-within:outline-offset-4 focus-within:outline-[var(--color-accent-ink)]">
        <span className="visually-hidden">Room code, 6 characters</span>
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6))}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          maxLength={6}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          className="absolute inset-0 z-10 h-full w-full cursor-text opacity-0 focus-visible:outline-none"
          data-testid="landing-code-input"
        />
        {/* The six cells. The next one to fill lifts while the box has focus. */}
        <div aria-hidden="true" className="flex gap-2">
          {Array.from({ length: 6 }, (_, i) => {
            const active = focused && i === Math.min(code.length, 5);
            return (
              <span
                key={i}
                className={`code-figure grid h-[68px] w-[52px] place-items-center border border-signal-ink text-[50px] shadow-[2px_2px_0_var(--color-accent-ink)] transition-transform duration-micro ${
                  active ? "-translate-y-1 bg-signal-ink text-signal" : "bg-signal text-signal-ink"
                }`}
              >
                {code[i] || ""}
              </span>
            );
          })}
        </div>
      </label>
      <button
        type="submit"
        disabled={code.length !== 6}
        className="inline-flex h-11 w-fit items-center gap-2 bg-signal-ink px-5 text-[15px] font-medium text-signal shadow-[4px_4px_0_rgb(0_0_0/0.35)] transition-transform duration-micro hover:-translate-x-px hover:-translate-y-px active:translate-x-1 active:translate-y-1 active:shadow-none disabled:cursor-not-allowed disabled:opacity-60"
        data-testid="landing-code-submit"
      >
        Take me to the room
      </button>
    </form>
  );
}

/** A heading on the left and its standfirst on the right, shared by every landing section. */
function SectionHead({ title, children, id }) {
  return (
    <div id={id} className="flex flex-wrap items-end justify-between gap-6 scroll-mt-28">
      <h2 className="max-w-[18ch] text-[clamp(3rem,4.5vw+1rem,5.25rem)] text-ink">{title}</h2>
      <p className="max-w-[46ch] text-lg leading-relaxed text-ink-3">{children}</p>
    </div>
  );
}

/** A drawn mark for each part of the stack (generic line icons, never vendor logos). */
const STACK_MARKS = {
  FastAPI: Braces, uvicorn: Server, PostgreSQL: Database, Redis: Radio,
  "Pydantic v2": ShieldCheck, "React 19": Component, pytest: FlaskConical, Sessions: Cookie,
};

/** A figure caption set under the thing it labels. */
const Caption = ({ children }) => <p className="mt-3 font-mono text-xs text-ink-3">{children}</p>;

/** The public landing page: an evidence board of the product, its features, and how it is built.
 *  The demo room is simulated in the browser and says so; every number on the page is true. */
export default function Landing() {
  const navigate = useNavigate();
  const rootRef = useRef(null);
  const archRef = useRef(null);
  const [frames, setFrames] = useState([]);
  useReveal(rootRef);

  // Each demo event lands in the frames receipt; a message also flies through the architecture.
  const onFrame = useCallback((f) => {
    setFrames((list) => [{ id: Math.random(), text: JSON.stringify(f) }, ...list].slice(0, 7));
    if (/message_created|send_message|reply_message/.test(f.type)) archRef.current?.journey();
  }, []);

  return (
    <div ref={rootRef} className="min-h-screen overflow-x-clip bg-paper text-ink">
      {/* Nav: a strip of copy paper pinned along the top */}
      <div className="px-4 pt-4 sm:px-6 lg:px-12">
        <nav className="sheet mx-auto flex w-full max-w-[1312px] items-center gap-6 px-4 py-2" data-testid="landing-nav">
          <Logo size="sm" />
          <div className="hidden gap-6 text-[15px] text-ink-3 lg:flex">
            <a href="#features" className="hover:text-ink">Features</a>
            <a href="#how" className="hover:text-ink">How it works</a>
            <a href="#app" className="hover:text-ink">The app</a>
            <a href="#tech" className="hover:text-ink">Tech board</a>
          </div>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <ThemeToggle />
            <Button variant="ghost" className="hidden sm:inline-flex" onClick={() => navigate("/login")} data-testid="nav-login-button">
              Log in
            </Button>
            <Button onClick={() => navigate("/register")} data-testid="nav-register-button">
              Sign up
            </Button>
          </div>
        </nav>
      </div>

      <main className="mx-auto w-full max-w-[1360px] px-4 sm:px-6 lg:px-12">
        {/* The case file: drag any card by its strip and the tape follows */}
        <Board className="mt-10" height={980} draggable links={[["head", "room"], ["room", "code"], ["room", "facts"], ["head", "facts"]]}>
          <Pin id="head" x={0} y={24} w={500} rotate={-1.2} className="sheet cursor-grab px-6 pb-6 pt-9 active:cursor-grabbing">
            <h1 className="text-[clamp(4rem,5.5vw+1rem,5.5rem)] text-ink">Where your people gather to talk.</h1>
            <p className="mt-4 text-lead text-ink">
              Create a room, share a 6-character code, and every message, join and kick reaches everyone inside the moment it happens.
            </p>
            <div className="mt-6 flex flex-wrap gap-3.5">
              <Button size="lg" onClick={() => navigate("/register")} data-testid="create-account-button">Create account</Button>
              <Button size="lg" variant="outline" onClick={() => navigate("/login")} data-testid="get-started-button">Log in</Button>
            </div>
          </Pin>

          <Pin id="room" x={560} y={0} w={620} rotate={0.8} className="sheet-raised px-3.5 pb-3.5 pt-6">
            <div data-handle className="flex cursor-grab justify-center pb-2 text-ink-3 active:cursor-grabbing" aria-label="Drag the demo room">
              <GripHorizontal size={18} aria-hidden="true" />
            </div>
            <DemoRoom onFrame={onFrame} />
            <Caption>Exhibit A: a live room, simulated in your browser. Try sending or replying.</Caption>
          </Pin>

          <Pin id="facts" x={30} y={660} w={470} rotate={-0.6} className="sheet cursor-grab px-5 pb-5 pt-9 active:cursor-grabbing">
            <dl className="grid grid-cols-3 gap-2.5">
              {STATS.map((s) => (
                <div key={s.label} className="bg-paper-4 px-3 py-2.5">
                  <dt className="sr-only">{s.label}</dt>
                  <dd className="code-figure text-[42px] text-ink" data-count-to={s.count} data-prefix={s.prefix || ""}>{(s.prefix || "") + s.count}</dd>
                  <dd className="text-[13px] leading-tight text-ink-3">{s.label}</dd>
                </div>
              ))}
            </dl>
            <Caption>Exhibit B: the numbers, all true of the code.</Caption>
          </Pin>

          <Pin id="code" x={830} y={680} w={420} rotate={2.5} className="sheet-fluoro px-6 pb-6 pt-9">
            <div data-handle className="cursor-grab active:cursor-grabbing">
              <h2 className="text-[44px] leading-none">Got a code?</h2>
              <p className="mb-4 mt-1.5 text-[15px]">Type it here. We'll take you to the room once you're logged in.</p>
            </div>
            <CodeBox />
          </Pin>

          <span className="stamp reveal absolute left-[560px] top-[690px] z-[4] max-[900px]:hidden" style={{ "--d": "0.6s" }}>Live · WS 101</span>
          <span className="sticker sticker-fluoro left-[520px] top-[900px] rotate-[-4deg] max-[900px]:hidden">{'{"type":"send_message"}'}</span>
          <span className="sticker left-[1180px] top-[560px] rotate-[6deg] max-[900px]:hidden">msgpack</span>
          <span className="sticker sticker-fluoro left-[870px] top-[612px] rotate-[2deg] max-[900px]:hidden">Drag any card by its strip · the tape follows</span>
          <span className="sticker sticker-outline left-[60px] top-[944px] rotate-[3deg] max-[900px]:hidden">pbkdf2_sha256$1200000$…</span>
        </Board>
      </main>

      {/* The ticker: the stack scrolling past, paused on hover */}
      <div className="rc-marquee mt-14 border-y border-rule bg-paper-2 py-3 font-mono text-[13px] text-ink-2" aria-label="Built with">
        <div>
          {[...TICKER, ...TICKER].map((t, i) => (
            <span key={i} aria-hidden={i >= TICKER.length} className="flex items-center gap-2">
              <span className="h-2 w-2 bg-signal" aria-hidden="true" /> {t}
            </span>
          ))}
        </div>
      </div>

      <main className="mx-auto w-full max-w-[1360px] px-4 sm:px-6 lg:px-12">
        {/* Features: six cards taped to the one app they all run on */}
        <section className="relative pt-24">
          <span className="sticker sticker-outline right-[36%] top-12 rotate-[3deg] max-lg:hidden">async def receive()</span>
          <SectionHead id="features" title="Everything in a room, pushed live.">
            Six features, all wired to one ASGI app. Drag them apart; the grey slip on each is how it works.
          </SectionHead>
          <Board className="mt-10" height={820} draggable links={FEATURES.map((f) => [f.key, "hub"])}>
            {FEATURES.map((f, i) => (
              <Pin
                key={f.key}
                id={f.key}
                x={[0, 442, 884, 0, 442, 884][i]}
                y={[0, 0, 0, 450, 480, 450][i]}
                w={380}
                rotate={[-1.5, 1, -0.5, 1.2, -1, 1.6][i]}
                className="sheet cursor-grab px-5 pb-5 pt-9 active:cursor-grabbing"
                data-testid={`feature-card-${i}`}
              >
                <h3 className="font-display text-[40px] uppercase leading-none text-ink">{f.title}</h3>
                <p className="mt-2 text-[15px] leading-relaxed text-ink">{f.text}</p>
                <p className="mt-3 bg-paper-4 p-2.5 font-mono text-xs leading-relaxed text-ink-2">{f.tech}</p>
              </Pin>
            ))}
            <Pin id="hub" x={522} y={360} w={220} className="sheet-fluoro cursor-grab px-4 pb-4 pt-8 text-center active:cursor-grabbing">
              <p className="font-display text-[34px] uppercase leading-none">ASGI app</p>
              <p className="mt-1 font-mono text-[11px]">FastAPI · uvicorn · one process</p>
            </Pin>
            <span className="sticker left-[300px] top-[390px] rotate-[-5deg] max-[900px]:hidden">close 4005</span>
            <span className="sticker sticker-fluoro left-[800px] top-[400px] rotate-[4deg] max-[900px]:hidden">PUBLISH room_82S0OT</span>
          </Board>
        </section>

        {/* The path of one message: five slips pinned along one string */}
        <section className="relative pt-24">
          <span className="sticker sticker-outline right-[38%] top-10 rotate-[-3deg] max-lg:hidden">101 Switching Protocols</span>
          <SectionHead id="how" title="The path of one message.">
            Pinned on one string, left to right: from the sender's socket to every member's screen.
          </SectionHead>
          <ol className="relative mt-12 grid grid-cols-5 gap-6 max-lg:grid-cols-2 max-sm:grid-cols-1 lg:before:absolute lg:before:inset-x-0 lg:before:top-3 lg:before:h-[2.5px] lg:before:bg-line lg:before:opacity-75 lg:before:content-['']">
            {FLOW.map(([title, note], i) => (
              <li key={title} className="reveal sheet pin px-4 pb-4 pt-9" style={{ "--rest": `rotate(${i % 2 ? 1.2 : -1.2}deg)`, "--d": `${i * 0.08}s` }}>
                <span className="code-figure block text-[44px] text-ink-3">{i + 1}</span>
                <span className="mt-1 block font-display text-[26px] uppercase leading-tight text-ink">{title}</span>
                <span className="mt-1.5 block font-mono text-xs leading-relaxed text-ink-3">{note}</span>
              </li>
            ))}
          </ol>
        </section>

        {/* Inside the app: the dashboard and the room, as they look signed in */}
        <section className="relative pt-24">
          <span className="sticker sticker-fluoro right-[34%] top-12 rotate-[4deg] max-lg:hidden">sessionid · HttpOnly · SameSite=Lax</span>
          <span className="sticker left-[44%] top-[62%] z-[3] rotate-[-6deg] max-lg:hidden">X-CSRFToken</span>
          <SectionHead id="app" title="Inside the app.">
            Your dashboard shows where your friends are; a room shows who is here and gives the owner moderation.
          </SectionHead>
          <div className="mt-12 grid items-start gap-8 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
            <figure className="reveal sheet-raised pin m-0 p-6 pt-10" style={{ "--rest": "rotate(-0.6deg)" }}>
              <div className="grid gap-6 sm:grid-cols-2">
                <div>
                  <p className="font-display text-[28px] uppercase leading-none text-ink">Friends</p>
                  <p className="mt-3 flex h-9 items-center gap-2 border border-rule bg-paper px-2.5 text-sm text-ink-3"><Search size={14} aria-hidden="true" /> Search friends</p>
                  <ul className="mt-2 text-[15px]">
                    {[["bob", "in Friday plans"], ["carol", "in Friday plans"], ["devraj", "offline"]].map(([n, s]) => (
                      <li key={n} className="flex items-center gap-2.5 border-b border-rule-2 py-2">
                        <span className="grid h-7 w-7 place-items-center font-display text-base text-room-ink" style={{ background: paperFor(n) }} aria-hidden="true">{initial(n)}</span>
                        <span className="text-ink">{n}</span>
                        <span className="ml-auto font-mono text-xs text-ink-3">{s}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="font-display text-[28px] uppercase leading-none text-ink">Invitations</p>
                  <div className="mt-3 bg-paper-4 p-3">
                    <p className="text-[15px] text-ink">Study group <Lock size={13} className="inline text-ink-3" aria-label="password protected" /></p>
                    <p className="text-sm text-ink-3">bob invited you · 2m ago</p>
                    <div className="mt-2.5 flex gap-2">
                      <span className="inline-flex h-8 items-center bg-signal px-3 text-sm text-signal-ink shadow-offset-xs">Join room</span>
                      <span className="inline-flex h-8 items-center bg-paper-3 px-3 text-sm text-ink shadow-offset-xs">Decline</span>
                    </div>
                  </div>
                  <p className="mt-4 font-display text-[28px] uppercase leading-none text-ink">Join a room</p>
                  <p className="code-figure mt-2 text-[40px] text-ink">DSN9Q2</p>
                </div>
              </div>
              <Caption>The dashboard: friends and the room each one is in, invitations, joining by code.</Caption>
            </figure>
            <figure className="reveal sheet-raised pin m-0 p-6 pt-10" style={{ "--rest": "rotate(1deg)", "--d": "0.12s" }}>
              <p className="font-display text-[28px] uppercase leading-none text-ink">Members</p>
              <ul className="mt-3 text-[15px]">
                {[["alice", "Owner"], ["bob", "Member"], ["carol", "Member"]].map(([n, r], i) => (
                  <li key={n} className={`flex items-center gap-2.5 px-2 py-2 ${i === 1 ? "bg-paper-4" : ""}`}>
                    <span className="grid h-7 w-7 place-items-center font-display text-base text-room-ink" style={{ background: paperFor(n) }} aria-hidden="true">{initial(n)}</span>
                    <span className="text-ink">{n}</span>
                    {r === "Owner" && <Crown size={13} className="text-ink" aria-hidden="true" />}
                    <span className="ml-auto text-xs text-ink-3">{r}</span>
                    {i === 1 && <MoreVertical size={15} className="text-ink-3" aria-hidden="true" />}
                  </li>
                ))}
              </ul>
              <div className="ml-auto mt-1 w-56 bg-paper-4 p-1 text-sm shadow-sheet">
                <p className="flex items-center gap-2 px-2 py-1.5 text-ink"><Crown size={14} aria-hidden="true" /> Transfer ownership</p>
                <p className="flex items-center gap-2 px-2 py-1.5 text-error"><UserMinus size={14} aria-hidden="true" /> Kick from room</p>
              </div>
              <p className="mt-4 flex h-9 items-center gap-2 border border-rule bg-paper px-2.5 text-sm text-ink-3"><Search size={14} aria-hidden="true" /> Search this room's messages</p>
              <Caption>A room: live members, owner moderation, and search through the loaded history.</Caption>
            </figure>
          </div>
        </section>
      </main>

      {/* The tech board: how it is built, pinned up and wired together */}
      <section className="fibre mt-24 bg-paper-2 py-20">
        <div className="mx-auto w-full max-w-[1360px] px-4 sm:px-6 lg:px-12">
          <div className="relative">
            <span className="sticker sticker-fluoro right-[34%] -top-6 rotate-[-4deg] max-lg:hidden">alembic upgrade head</span>
          </div>
          <SectionHead id="tech" title="The tech board.">
            How it's built, pinned up and wired together. Send a message in Exhibit A and watch the architecture light up.
          </SectionHead>
          <Board className="mt-10" height={1300} draggable links={[["arch", "frames"], ["arch", "mw"], ["arch", "codes"], ["codes", "gate"]]}>
            <Pin id="arch" x={0} y={0} w={840} className="sheet-raised px-6 pb-6 pt-9">
              <div data-handle className="cursor-grab active:cursor-grabbing">
                <h3 className="font-display text-[42px] uppercase leading-none text-ink">One ASGI app, two sockets, two stores.</h3>
              </div>
              <div className="mt-4"><ArchDiagram ref={archRef} /></div>
              <div className="mt-2 flex items-center gap-4">
                <Button onClick={() => archRef.current?.journey()}><Play /> Replay a message</Button>
                <Caption>Fig. 1: architecture. Packets are simulated.</Caption>
              </div>
            </Pin>
            <Pin id="frames" x={880} y={40} w={380} rotate={2} className="receipt-edge bg-paper-3 px-5 pb-5 pt-9 shadow-sheet">
              <div data-handle className="flex cursor-grab justify-between font-display text-[22px] uppercase text-ink active:cursor-grabbing">
                <span>Frames</span><span>/ws/chat/82S0OT/</span>
              </div>
              <ul className="mt-2 min-h-[190px]" aria-live="off">
                {frames.length === 0 && <li className="font-mono text-xs text-ink-3">Waiting for the demo room…</li>}
                {frames.map((f, i) => (
                  <li key={f.id} className={`truncate font-mono text-xs leading-[1.95] ${i === 0 ? "rc-pop text-ink" : "text-ink-3"}`}>{f.text}</li>
                ))}
              </ul>
              <Caption>Fig. 2: the frames Exhibit A sends, newest first.</Caption>
            </Pin>
            <Pin id="mw" x={0} y={600} w={540} className="sheet-raised px-6 pb-6 pt-9">
              <div data-handle className="cursor-grab active:cursor-grabbing">
                <h3 className="font-display text-[42px] uppercase leading-none text-ink">Eight layers, outermost first.</h3>
                <p className="mt-1.5 text-[15px] text-ink-3">Every HTTP request passes down through these and back up.</p>
              </div>
              <MiddlewareStack />
              <Caption>Fig. 3: roomchat/middleware.py.</Caption>
            </Pin>
            <Pin id="codes" x={584} y={560} w={680} className="sheet-raised px-6 pb-6 pt-9">
              <div data-handle className="cursor-grab active:cursor-grabbing">
                <h3 className="font-display text-[42px] uppercase leading-none text-ink">How a socket says goodbye.</h3>
              </div>
              <CloseCodes />
              <Caption>Fig. 4: close codes. A fatal one means the client never reconnects.</Caption>
            </Pin>
            <Pin id="gate" x={584} y={950} w={680} className="sheet-raised px-6 pb-6 pt-9">
              <div data-handle className="cursor-grab active:cursor-grabbing">
                <h3 className="font-display text-[42px] uppercase leading-none text-ink">The gate, in order.</h3>
              </div>
              <AccessGate />
              <Caption>Fig. 5: room access. Reordering it would leak history or bypass a ban.</Caption>
            </Pin>
            <span className="sticker sticker-fluoro left-[900px] top-[480px] rotate-[-5deg] max-[900px]:hidden">PUBLISH asgi__group__room_82S0OT</span>
            <span className="sticker left-[420px] top-[548px] rotate-[4deg] max-[900px]:hidden">X-CSRFToken</span>
          </Board>

          <figure className="reveal sheet-raised m-0 mt-12 px-7 pb-7 pt-8">
            <h3 className="font-display text-[42px] uppercase leading-none text-ink">PostgreSQL tables, cascading deletes.</h3>
            <SchemaCards />
            <Caption>Fig. 6: the data model. When a room goes, its messages, bans and invitations go with it.</Caption>
          </figure>
          <figure className="reveal sheet-raised m-0 mt-10 px-7 pb-7 pt-8">
            <h3 className="font-display text-[42px] uppercase leading-none text-ink">Born by POST, gone when empty.</h3>
            <Lifecycle />
            <Caption>Fig. 7: the room lifecycle.</Caption>
          </figure>
          {/* The stack as die-cut stickers: a drawn mark, the name, its job; varied tilt and size */}
          <h3 className="mt-16 font-display text-[42px] uppercase leading-none text-ink">What it's built with.</h3>
          <ul className="mt-8 grid grid-cols-4 items-start gap-x-6 gap-y-8 max-lg:grid-cols-2">
            {STACK.map(([name, role], i) => {
              const Mark = STACK_MARKS[name];
              return (
                <li
                  key={name}
                  className="reveal flex items-center gap-4 border-[6px] border-paper-4 bg-paper-3 p-4 shadow-sheet"
                  style={{ "--rest": `rotate(${[-2, 1.5, -1, 2.5, 1, -2.5, 2, -1.5][i]}deg)`, "--d": `${(i % 4) * 0.06}s`, marginTop: i % 2 ? 18 : 0 }}
                >
                  <span className={`grid h-16 w-16 shrink-0 place-items-center ${i % 3 === 0 ? "bg-signal text-signal-ink" : "bg-paper-4 text-ink"}`}>
                    <Mark size={34} strokeWidth={1.6} aria-hidden="true" />
                  </span>
                  <span className="min-w-0">
                    <span className="block font-display text-[28px] uppercase leading-none text-ink">{name}</span>
                    <span className="mt-1 block font-mono text-xs leading-snug text-ink-3">{role}</span>
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      </section>

      {/* The toner band: one line, board-coloured on toner, and the way in */}
      <section className="bg-ink text-paper">
        <div className="mx-auto flex w-full max-w-[1360px] flex-wrap items-end justify-between gap-8 px-4 py-20 sm:px-6 lg:px-12">
          <h2 className="max-w-[14ch] text-[clamp(3.5rem,5vw+1rem,6rem)]">Create a room. Share the code.</h2>
          <Button size="lg" onClick={() => navigate("/register")}>Create account</Button>
        </div>
      </section>

      {/* Footer: one colophon line on the board */}
      <footer>
        <div className="mx-auto flex w-full max-w-[1360px] flex-wrap items-center justify-between gap-4 px-4 py-9 text-sm text-ink sm:px-6 lg:px-12">
          <Logo size="sm" />
          <p>RoomChat, real-time rooms on FastAPI.</p>
          <p>© 2026 RoomChat</p>
        </div>
      </footer>
    </div>
  );
}
