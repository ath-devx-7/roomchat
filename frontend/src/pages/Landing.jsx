import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Pause, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";
import { BOOTSTRAP } from "@/lib/api";
import { currentMode } from "@/lib/theme";
import { useAuth } from "@/App";

// Comes from the backend via static() (roomchat/staticfiles.py). It is not a literal
// "/static/..." path or an import, because only a URL built server-side carries the
// ?v=<content hash> that busts the cache after a rebuild. See templates/index.html.
// Each asset comes in a dark (black wall) and a light (kraft) colourway.
const HERO = {
  dark: { video: BOOTSTRAP.heroVideo, poster: BOOTSTRAP.heroImage },
  light: { video: BOOTSTRAP.heroVideoLight || BOOTSTRAP.heroVideo, poster: BOOTSTRAP.heroImageLight || BOOTSTRAP.heroImage },
};
// Captures of the app for the feature sheets, passed the same way (rooms/views.py spa).
const SCREENS = BOOTSTRAP.screens || {};
// The sample room's code as it appears in the hero recording (public/img/hero*.webm). The
// recording and this string come from the same scratch session: update them together.
const HERO_CODE = "82S0OT";

// The wall: each feature's capture pasted on as a lifted sheet at its real size (w x h in CSS
// pixels), its title and line on the sheet's foot, with two room rules set as flyers between
// them. Mixed spans on twelve columns; two pieces tilt.
const wall = [
  {
    kind: "shot",
    title: "Rooms up to 100",
    text: "Spin up private or open rooms with fine-grained capacity.",
    dark: SCREENS.create,
    light: SCREENS.createLight,
    w: 448,
    h: 260,
    alt: "Part of the create-room dialog: password protection switched on, a room password field and a capacity slider from 2 to 100",
    span: "lg:col-span-5",
    tilt: "",
  },
  { kind: "flyer", figure: "6", line: "characters in every room code", fluoro: true, span: "lg:col-span-3", tilt: "lg:rotate-[2deg]" },
  {
    kind: "shot",
    title: "Invite friends",
    text: "Pull someone from your friends list into the room.",
    dark: SCREENS.invite,
    light: SCREENS.inviteLight,
    w: 448,
    h: 182,
    alt: "The invite dialog: a friend who is not in the room yet, with an Invite button",
    span: "lg:col-span-4",
    tilt: "",
  },
  {
    kind: "shot",
    title: "Owner controls",
    text: "Kick, transfer ownership, and lock rooms with a password.",
    dark: SCREENS.owner,
    light: SCREENS.ownerLight,
    w: 288,
    h: 215,
    alt: "The members list with a member's menu open: transfer ownership, kick from room",
    span: "lg:col-span-4",
    tilt: "lg:-rotate-1",
  },
  {
    kind: "shot",
    title: "Realtime presence",
    text: "See who joins and leaves the moment it happens.",
    dark: SCREENS.members,
    light: SCREENS.membersLight,
    w: 288,
    h: 300,
    alt: "The members sidebar: four members, the owner marked, and the newest one flashing as they join",
    span: "lg:col-span-4",
    tilt: "",
  },
  { kind: "flyer", figure: "1 room", line: "at a time: joining one leaves the last", fluoro: false, span: "lg:col-span-4", tilt: "" },
];

/** A capture in both colourways; CSS in index.css shows the one matching the mode. */
function Capture({ dark, light, alt, className, ...props }) {
  return (
    <>
      <img src={dark} alt={alt} className={`rc-dark-only ${className}`} {...props} />
      <img src={light || dark} alt={alt} className={`rc-light-only ${className}`} {...props} />
    </>
  );
}

/** The mode on screen, kept in sync with the theme toggle and the OS setting. */
function useMode() {
  const [mode, setModeState] = useState(currentMode);
  useEffect(() => {
    const sync = () => setModeState(currentMode());
    // The toggle writes data-mode on <html>; the OS can change too.
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-mode"] });
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", sync);
    return () => {
      observer.disconnect();
      mq.removeEventListener("change", sync);
    };
  }, []);
  return mode;
}

/** The hero's live room: a short muted loop recorded from the real app, with a visible
 *  pause control in the caption row under it. It starts paused (on its poster) when the OS
 *  asks for reduced motion. */
function LiveRoom({ caption }) {
  const mode = useMode();
  const videoRef = useRef(null);
  const [playing, setPlaying] = useState(
    () => !window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  const src = HERO[mode];

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    if (playing) {
      // Browsers may refuse to play (data saver, power saving): fall back to the poster.
      v.play().catch(() => setPlaying(false));
    } else {
      v.pause();
    }
  }, [playing, mode]);

  return (
    <div>
      <video
        key={mode}
        ref={videoRef}
        src={src.video}
        poster={src.poster}
        muted
        loop
        playsInline
        preload="metadata"
        width="1440"
        height="1280"
        aria-label="A recording of a RoomChat room: four messages arriving one after another"
        className="block aspect-[9/8] w-full bg-paper object-cover object-left-top"
      />
      {/* Caption on the right (the code sheet overlaps the left corner), then the toggle */}
      <div className="mt-3 flex items-center justify-end gap-3">
        <p className="text-sm text-ink">{caption}</p>
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          aria-pressed={!playing}
          aria-label={playing ? "Pause the recording" : "Play the recording"}
          className="grid h-10 w-10 shrink-0 place-items-center border border-ink bg-paper-3 text-ink shadow-offset-xs transition-transform duration-micro ease-out active:translate-x-0.5 active:translate-y-0.5 active:shadow-none"
          data-testid="hero-video-toggle"
        >
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </button>
      </div>
    </div>
  );
}

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
    <form onSubmit={go} className="flex flex-col gap-6" data-testid="landing-code-form">
      <label className="relative block w-fit focus-within:outline focus-within:outline-2 focus-within:outline-offset-4 focus-within:outline-focus">
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
        {/* The six cells. The next one to fill turns fluorescent while the box has focus. */}
        <div aria-hidden="true" className="flex gap-2 sm:gap-3">
          {Array.from({ length: 6 }, (_, i) => {
            const active = focused && i === Math.min(code.length, 5);
            return (
              <span
                key={i}
                className={`code-figure grid h-16 w-11 place-items-center border border-ink text-[44px] shadow-offset-xs transition-colors duration-micro sm:h-20 sm:w-14 sm:text-[56px] lg:h-24 lg:w-[4.25rem] lg:text-[72px] ${
                  active ? "bg-signal text-signal-ink" : "bg-paper-3 text-ink"
                }`}
              >
                {code[i] || ""}
              </span>
            );
          })}
        </div>
      </label>
      <Button type="submit" size="lg" disabled={code.length !== 6} className="w-fit" data-testid="landing-code-submit">
        Take me to the room
      </Button>
    </form>
  );
}

/** The public landing page: a Stage hero with a live room under a fluorescent code sheet, a
 *  code box, the features as a paste-up wall, a toner band and a footer. */
export default function Landing() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-paper">
      {/* Nav: a strip of copy paper pinned along the top */}
      <div className="px-4 pt-4 sm:px-6 lg:px-16">
        <nav className="sheet mx-auto flex w-full max-w-[1312px] items-center justify-between px-4 py-2" data-testid="landing-nav">
          <Logo size="sm" />
          <div className="flex items-center gap-2 sm:gap-3">
            <ThemeToggle />
            {/* Under 640px the hero's own Log in button is right below, so this one steps aside */}
            <Button variant="ghost" className="hidden sm:inline-flex" onClick={() => navigate("/login")} data-testid="nav-login-button">
              Log in
            </Button>
            <Button onClick={() => navigate("/register")} data-testid="nav-register-button">
              Sign up
            </Button>
          </div>
        </nav>
      </div>

      {/* Hero (Stage): the poster head on five columns, the live room on seven */}
      <section className="mx-auto grid w-full max-w-[1440px] items-center gap-16 px-4 pb-24 pt-12 sm:px-6 lg:min-h-[calc(100svh-88px)] lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:px-16 lg:py-12">
        <div>
          <h1 className="text-[clamp(4rem,7vw+1rem,7.3rem)] text-ink [text-wrap:balance]">
            Where your people gather to talk.
          </h1>
          <p className="mt-6 max-w-[38ch] text-lead text-ink">
            Create a room, share a 6-character code, and start chatting instantly.
          </p>
          <div className="mt-10 flex flex-wrap items-center gap-4">
            <Button size="lg" onClick={() => navigate("/register")} data-testid="create-account-button">
              Create account
            </Button>
            <Button size="lg" variant="outline" onClick={() => navigate("/login")} data-testid="get-started-button">
              Log in
            </Button>
          </div>
        </div>

        {/* sm:pb-12 keeps the overlapping code sheet inside the figure's box, so the hero centres */}
        <figure className="relative m-0 w-full sm:pb-12 lg:max-w-[620px] lg:justify-self-start">
          {/* The room, printed on a copy sheet and pasted on at a slight tilt */}
          <div className="sheet-raised p-3 sm:p-4 lg:rotate-[1.2deg]">
            <LiveRoom caption="A live room, recorded in the app." />
          </div>
          {/* The signature: the room's code on the fluorescent sheet, overlapping the print */}
          <div className="sheet-fluoro relative mt-6 inline-block -rotate-2 px-7 py-4 sm:absolute sm:bottom-0 sm:left-[-1.5rem] sm:mt-0 sm:-rotate-3">
            <p className="text-sm font-medium">Room code</p>
            <p className="code-figure text-[56px] sm:text-[72px]">{HERO_CODE}</p>
          </div>
        </figure>
      </section>

      {/* Got a code? The form as a sheet, beside its head set big on the board */}
      <section className="mx-auto grid w-full max-w-[1440px] items-center gap-10 px-4 pb-24 pt-12 sm:px-6 lg:grid-cols-12 lg:px-16 lg:pt-20">
        <div className="lg:col-span-5">
          <h2 className="text-[clamp(3rem,4vw+1rem,5.5rem)] text-ink">Got a code?</h2>
          <p className="mt-4 max-w-[34ch] text-lead text-ink">Type it here. We’ll take you to the room once you’re logged in.</p>
        </div>
        <div className="sheet-raised p-6 sm:p-10 lg:col-span-6 lg:col-start-7">
          <CodeBox />
        </div>
      </section>

      {/* The features as a paste-up wall: captures at real size on lifted sheets, two flyers */}
      <section className="fibre bg-paper-2">
        <div className="mx-auto w-full max-w-[1440px] px-4 py-24 sm:px-6 lg:px-16 lg:py-28">
          <h2 className="text-[clamp(3rem,4.5vw+1rem,6rem)] text-ink lg:max-w-[22ch]">Friends, presence, invites and moderation.</h2>
          <p className="mt-4 text-lead text-ink">All in one warm, simple space.</p>

          <div className="mt-16 grid items-start gap-8 lg:grid-cols-12">
            {wall.map((item, i) =>
              item.kind === "flyer" ? (
                <div key={item.figure} className={`${item.fluoro ? "sheet-fluoro" : "sheet-raised"} p-8 ${item.span} ${item.tilt}`}>
                  <p className="code-figure text-[clamp(4.5rem,6vw,7.5rem)] uppercase">{item.figure}</p>
                  <p className="mt-3 text-lg">{item.line}</p>
                </div>
              ) : (
                <figure key={item.title} className={`sheet-raised m-0 min-w-0 p-4 ${item.span} ${item.tilt}`} data-testid={`feature-card-${i}`}>
                  {/* The capture at its real size; it only shrinks when the sheet is narrower */}
                  <div className="flex justify-center bg-paper p-4">
                    <Capture
                      dark={item.dark}
                      light={item.light}
                      alt={item.alt}
                      width={item.w}
                      height={item.h}
                      loading="lazy"
                      className="h-auto w-full max-w-full shadow-card"
                      style={{ maxWidth: item.w }}
                    />
                  </div>
                  <figcaption className="px-2 pb-2 pt-5">
                    <h3 className="text-title text-ink">{item.title}</h3>
                    <p className="mt-1 text-ink">{item.text}</p>
                  </figcaption>
                </figure>
              )
            )}
          </div>
        </div>
      </section>

      {/* The toner band: one line, board-coloured on toner, and the way in */}
      <section className="bg-ink text-paper">
        <div className="mx-auto flex w-full max-w-[1440px] flex-wrap items-end justify-between gap-8 px-4 py-20 sm:px-6 lg:px-16">
          <h2 className="max-w-[18ch] text-[clamp(3rem,5vw+1rem,6.5rem)]">Create a room. Share the code.</h2>
          <Button size="lg" onClick={() => navigate("/register")}>
            Create account
          </Button>
        </div>
      </section>

      {/* Footer: one colophon line on the board */}
      <footer>
        <div className="mx-auto flex w-full max-w-[1440px] flex-wrap items-center justify-between gap-4 px-4 py-10 text-sm text-ink sm:px-6 lg:px-16">
          <Logo size="sm" />
          <p>RoomChat, real-time rooms on FastAPI.</p>
          <p>© 2026 RoomChat</p>
        </div>
      </footer>
    </div>
  );
}
