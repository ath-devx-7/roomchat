import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";
import { api } from "@/lib/api";
import { useAuth } from "@/App";
import { toast } from "sonner";
import { Check, Eye, EyeOff, Loader2, X } from "lucide-react";

export default function Register() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setUser } = useAuth();
  // A room code typed on the landing page rides along in router state; after signing in it
  // goes on to the dashboard as ?code=, where the join box picks it up.
  const presetCode = location.state?.code;
  const afterAuth = presetCode ? `/dashboard?code=${encodeURIComponent(presetCode)}` : "/dashboard";
  const [form, setForm] = useState({ username: "", email: "", password: "", confirm: "" });
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  // Guidance only. The authoritative checks are UserCreate's validators in
  // accounts/schemas.py, which require 8+ characters and a match but not a digit.
  const rules = [
    { label: "At least 8 characters", ok: form.password.length >= 8 },
    { label: "One number", ok: /\d/.test(form.password) },
    { label: "Passwords match", ok: form.password.length > 0 && form.password === form.confirm },
  ];

  const handleRegister = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErrors({});
    try {
      const { user } = await api.register({
        username: form.username,
        email: form.email,
        password: form.password,
        confirm_password: form.confirm,
      });
      setUser(user);
      toast.success("Account created! Welcome to RoomChat.");
      navigate(afterAuth, { replace: true });
    } catch (err) {
      setErrors(err.fieldErrors || {});
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fieldError = (name) =>
    errors[name] ? (
      <p className="text-sm text-error">{errors[name]}</p>
    ) : null;

  return (
    <div className="fibre flex min-h-screen flex-col bg-paper">
      {/* A strip of copy paper along the top: the way home, the theme switch, the way to log in */}
      <div className="px-4 pt-4 sm:px-6 lg:px-12">
        <nav className="sheet mx-auto flex w-full max-w-[1312px] items-center gap-3 px-4 py-2">
          <Link to="/" aria-label="RoomChat home"><Logo size="sm" /></Link>
          <ThemeToggle className="ml-auto" />
          <Link to="/login" state={location.state} className="hidden h-10 items-center px-3 text-[15px] text-ink hover:bg-paper-4 sm:flex">
            Have an account? Log in
          </Link>
        </nav>
      </div>

      <main className="mx-auto grid w-full max-w-[1312px] flex-1 items-center gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)] lg:px-12">
        {/* Left: the form, on a raised sheet taped to the board */}
        <div className="sheet-raised tape mx-auto w-full max-w-lg px-8 pb-9 pt-10 sm:px-10" style={{ transform: "rotate(-0.5deg)" }}>
          <h1 className="text-[clamp(3.5rem,3vw+1.5rem,4.5rem)] text-ink">Create your account</h1>
          <p className="mt-2 text-ink-3">Start creating and joining rooms in seconds.</p>

          <form onSubmit={handleRegister} className="mt-8 space-y-5" data-testid="register-form">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                value={form.username}
                onChange={set("username")}
                placeholder="alex_rivera"
                autoComplete="username"
                autoFocus
                className="h-11"
                data-testid="register-username-input"
              />
              {fieldError("username")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={form.email}
                onChange={set("email")}
                placeholder="you@example.com"
                autoComplete="email"
                className="h-11"
                data-testid="register-email-input"
              />
              {fieldError("email")}
            </div>
            <div className="grid gap-5 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPw ? "text" : "password"}
                    value={form.password}
                    onChange={set("password")}
                    autoComplete="new-password"
                    className="h-11 pr-12"
                    data-testid="register-password-input"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw((s) => !s)}
                    className="absolute right-1 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center text-ink-3 transition-colors hover:text-ink"
                    aria-label={showPw ? "Hide password" : "Show password"}
                  >
                    {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
                {fieldError("password")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirm">Confirm</Label>
                <Input
                  id="confirm"
                  type={showPw ? "text" : "password"}
                  value={form.confirm}
                  onChange={set("confirm")}
                  autoComplete="new-password"
                  className="h-11"
                  data-testid="register-confirm-input"
                />
                {fieldError("confirm_password")}
              </div>
            </div>

            {/* Password guidance: one line per rule, a check when it is met */}
            <ul className="space-y-1.5 text-sm" aria-label="Password rules">
              {rules.map((r) => (
                <li key={r.label} className={`flex items-center gap-2 transition-colors ${r.ok ? "text-ink" : "text-ink-3"}`}>
                  {r.ok ? <Check size={15} className="rc-pop text-success" aria-hidden="true" /> : <X size={15} aria-hidden="true" />}
                  {r.label}
                </li>
              ))}
            </ul>

            <Button
              type="submit"
              size="lg"
              disabled={loading}
              className="w-full"
              data-testid="register-submit-button"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : null}
              {loading ? "Creating account…" : "Create account"}
            </Button>
          </form>

          <p className="mt-8 text-ink-3">
            Already have an account?{" "}
            <Link to="/login" state={location.state} className="font-medium text-ink underline underline-offset-4 hover:text-ink-2" data-testid="go-to-login-link">
              Log in
            </Link>
          </p>
        </div>

        {/* Right: what an account gets you, with a sample code on the fluorescent sheet */}
        <aside className="relative hidden pb-16 lg:block">
          <div className="sheet pin px-8 pb-8 pt-11" style={{ transform: "rotate(1.2deg)" }}>
            <h2 className="text-[clamp(3.5rem,3vw+1.5rem,5rem)] text-ink">One code away from every conversation.</h2>
            <p className="mt-4 text-lg text-ink">
              Rooms of 2 to 100 people. Invite friends, hand off ownership, keep it private.
            </p>
            <ul className="mt-6 space-y-1 font-mono text-xs text-ink-3">
              <li>room_code · 6 × [A-Z0-9]</li>
              <li>passwords · PBKDF2-SHA256, 1.2M iterations</li>
              <li>rooms delete themselves when the last member leaves</li>
            </ul>
          </div>
          <div className="sheet-fluoro rc-sway absolute -bottom-2 right-8 px-7 py-4" style={{ "--rest": "rotate(-3deg)", transform: "rotate(-3deg)" }}>
            <p className="text-sm font-medium">Sample room code</p>
            <p className="code-figure text-[64px]">DSN9Q2</p>
          </div>
        </aside>
      </main>
    </div>
  );
}
