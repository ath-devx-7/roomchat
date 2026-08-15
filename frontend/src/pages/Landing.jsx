import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/Brand";
import { BOOTSTRAP } from "@/lib/api";
import { ArrowRight, ShieldCheck, Users, Zap, MessageCircle } from "lucide-react";

// Comes from Django via {% static %}. It cannot be a literal "/static/..." path or an
// import: CompressedManifestStaticFilesStorage renames collected files, so only a URL
// resolved server-side survives collectstatic. See templates/index.html.
const HERO_IMG = BOOTSTRAP.heroImage;

const features = [
  { icon: Users, title: "Rooms up to 100", text: "Spin up private or open rooms with fine-grained capacity." },
  { icon: Zap, title: "Realtime presence", text: "See who joins and leaves the moment it happens." },
  { icon: ShieldCheck, title: "Owner controls", text: "Kick, transfer ownership, and lock rooms with a password." },
];

export default function Landing() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-background overflow-x-hidden">
      {/* Nav */}
      <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-6" data-testid="landing-nav">
        <Logo />
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            className="rounded-full font-bold text-slate-600 hover:text-slate-900"
            onClick={() => navigate("/login")}
            data-testid="nav-login-button"
          >
            Log in
          </Button>
          <Button
            className="rounded-full font-bold px-6 shadow-floating"
            onClick={() => navigate("/register")}
            data-testid="nav-register-button"
          >
            Sign up
          </Button>
        </div>
      </nav>

      {/* Hero */}
      <section className="mx-auto grid max-w-7xl items-center gap-12 px-6 py-16 lg:grid-cols-2 lg:py-24">
        <div className="rc-fade-up">
          <span className="inline-flex items-center gap-2 rounded-full bg-accent px-4 py-1.5 text-sm font-bold text-accent-foreground">
            <MessageCircle size={16} /> Real-time room-based chat
          </span>
          <h1 className="mt-6 text-4xl font-extrabold leading-[1.05] tracking-tight text-slate-900 sm:text-5xl lg:text-6xl">
            Where your people <span className="text-primary">gather</span> to talk.
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-relaxed text-slate-500">
            Create a room, share a 6-character code, and start chatting instantly. Friends,
            presence, invites and moderation — all in one warm, simple space.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Button
              size="lg"
              className="group rounded-full px-8 py-6 text-base font-bold shadow-floating transition-all hover:-translate-y-0.5"
              onClick={() => navigate("/login")}
              data-testid="get-started-button"
            >
              Get started
              <ArrowRight size={18} className="ml-1 transition-transform group-hover:translate-x-1" />
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="rounded-full border-2 px-8 py-6 text-base font-bold text-slate-700"
              onClick={() => navigate("/register")}
              data-testid="create-account-button"
            >
              Create account
            </Button>
          </div>
        </div>

        <div className="relative rc-fade-up" style={{ animationDelay: "120ms" }}>
          <div className="absolute -inset-4 rounded-[2.5rem] bg-primary/10 blur-2xl" />
          <img
            src={HERO_IMG}
            alt="Friends planning a meetup in a group chat"
            className="relative aspect-[4/3] w-full rounded-[2rem] bg-white object-contain p-3 shadow-floating"
          />
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-7xl px-6 pb-24">
        <div className="grid gap-6 md:grid-cols-3">
          {features.map((f, i) => (
            <div
              key={f.title}
              className="rounded-3xl bg-card p-8 shadow-soft transition-all hover:-translate-y-1 hover:shadow-floating rc-fade-up"
              style={{ animationDelay: `${i * 90}ms` }}
              data-testid={`feature-card-${i}`}
            >
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-accent text-primary">
                <f.icon size={22} />
              </span>
              <h3 className="mt-5 text-xl font-extrabold text-slate-900">{f.title}</h3>
              <p className="mt-2 text-slate-500">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-border py-8 text-center text-sm font-semibold text-slate-400">
        RoomChat — real-time rooms on Django + Channels.
      </footer>
    </div>
  );
}
