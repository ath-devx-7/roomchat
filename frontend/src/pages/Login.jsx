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
import { Eye, EyeOff, Loader2, MessagesSquare, ShieldCheck, Users } from "lucide-react";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setUser } = useAuth();
  // A room code typed on the landing page rides along in router state; after signing in it
  // goes on to the dashboard as ?code=, where the join box picks it up.
  const presetCode = location.state?.code;
  const afterAuth = presetCode ? `/dashboard?code=${encodeURIComponent(presetCode)}` : "/dashboard";
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!identifier || !password) {
      toast.error("Please fill in all fields");
      return;
    }
    setLoading(true);
    setErrors({});
    try {
      // Sent as `username`: authenticate() is username-only, so the label says Username.
      // Signing in with an email is a wanted feature (features.txt #6).
      const { user } = await api.login({ username: identifier, password });
      setUser(user);
      toast.success("Welcome back to RoomChat!");
      navigate(afterAuth, { replace: true });
    } catch (err) {
      setErrors(err.fieldErrors || {});
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid min-h-screen bg-paper lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      {/* Left: a quiet ruled column with the product's promise */}
      <aside className="hidden flex-col justify-between bg-paper-2 p-12 lg:flex">
        <Logo />
        <div className="max-w-md">
          <h2 className="text-[64px] text-ink">Your rooms are waiting.</h2>
          <p className="mt-4 text-lg text-ink">
            Pick up conversations right where you left them, with everyone in real time.
          </p>
          <ul className="mt-10 border-t border-rule">
            {[
              { icon: Users, t: "Friends & presence in one glance" },
              { icon: ShieldCheck, t: "Private, password-protected rooms" },
              { icon: MessagesSquare, t: "Reply, edit and moderate with ease" },
            ].map((it) => (
              <li key={it.t} className="flex items-center gap-3 border-b border-rule py-3.5 text-ink">
                <it.icon size={17} className="shrink-0" aria-hidden="true" />
                {it.t}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-sm text-ink">© 2026 RoomChat</p>
      </aside>

      {/* Right: the form */}
      <div className="relative flex items-center justify-center px-6 py-16">
        <ThemeToggle className="absolute right-4 top-4" />
        <div className="sheet-raised w-full max-w-md p-8 sm:p-10">
          <div className="mb-10 lg:hidden">
            <Logo />
          </div>
          <h1 className="text-[56px] text-ink">Log in</h1>
          <p className="mt-2 text-ink-3">Enter your details to continue.</p>

          <form onSubmit={handleLogin} className="mt-8 space-y-5" data-testid="login-form">
            <div className="space-y-2">
              <Label htmlFor="identifier">Username</Label>
              <Input
                id="identifier"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder="alex_rivera"
                autoComplete="username"
                autoFocus
                className="h-11"
                data-testid="login-identifier-input"
              />
              {errors.username && (
                <p className="text-sm text-error">{errors.username}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPw ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  className="h-11 pr-12"
                  data-testid="login-password-input"
                />
                <button
                  type="button"
                  onClick={() => setShowPw((s) => !s)}
                  className="absolute right-1 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center text-ink-3 transition-colors hover:text-ink"
                  aria-label={showPw ? "Hide password" : "Show password"}
                  data-testid="toggle-password-visibility"
                >
                  {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
              {errors.password && (
                <p className="text-sm text-error">{errors.password}</p>
              )}
            </div>

            <Button
              type="submit"
              size="lg"
              disabled={loading}
              className="w-full"
              data-testid="login-submit-button"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : null}
              {loading ? "Logging in…" : "Log in"}
            </Button>
          </form>

          <p className="mt-8 text-ink-3">
            Don’t have an account?{" "}
            <Link to="/register" state={location.state} className="font-medium text-ink underline underline-offset-4 hover:text-ink-2" data-testid="go-to-register-link">
              Sign up
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
