import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/Brand";
import { api } from "@/lib/api";
import { useAuth } from "@/App";
import { toast } from "sonner";
import { Eye, EyeOff, Loader2, MessagesSquare, ShieldCheck, Users } from "lucide-react";

export default function Login() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
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
      // Sent as `username`: authenticate() is username-only. The label still offers
      // email because signing in with one is a wanted feature — see features.txt #6.
      const { user } = await api.login({ username: identifier, password });
      setUser(user);
      toast.success("Welcome back to RoomChat!");
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setErrors(err.fieldErrors || {});
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Left brand panel */}
      <div className="relative hidden flex-col justify-between bg-primary p-12 text-white lg:flex">
        <Logo className="[&_span]:text-white [&_.text-primary]:text-white/90" />
        <div className="max-w-md">
          <h2 className="text-4xl font-extrabold leading-tight">Your rooms are waiting.</h2>
          <p className="mt-4 text-lg text-white/80">
            Pick up conversations right where you left them, with everyone in real time.
          </p>
          <div className="mt-10 space-y-4">
            {[
              { icon: Users, t: "Friends & presence in one glance" },
              { icon: ShieldCheck, t: "Private, password-protected rooms" },
              { icon: MessagesSquare, t: "Reply, edit and moderate with ease" },
            ].map((it) => (
              <div key={it.t} className="flex items-center gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-2xl bg-white/15">
                  <it.icon size={18} />
                </span>
                <span className="font-semibold text-white/90">{it.t}</span>
              </div>
            ))}
          </div>
        </div>
        <p className="text-sm text-white/60">© 2026 RoomChat</p>
      </div>

      {/* Right form */}
      <div className="flex items-center justify-center bg-background px-6 py-12">
        <div className="w-full max-w-md rc-fade-up">
          <div className="lg:hidden mb-8 flex justify-center">
            <Logo />
          </div>
          <h1 className="text-3xl font-extrabold text-slate-900">Log in</h1>
          <p className="mt-2 text-slate-500">Enter your details to continue.</p>

          <form onSubmit={handleLogin} className="mt-8 space-y-5" data-testid="login-form">
            <div className="space-y-2">
              <Label htmlFor="identifier" className="font-bold text-slate-700">
                Username or email
              </Label>
              <Input
                id="identifier"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder="you@example.com"
                autoFocus
                className="h-12 rounded-2xl border-slate-200 bg-white px-4 focus-visible:ring-2 focus-visible:ring-primary/30"
                data-testid="login-identifier-input"
              />
              {errors.username && (
                <p className="text-sm font-semibold text-destructive">{errors.username}</p>
              )}
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password" className="font-bold text-slate-700">
                  Password
                </Label>
                <button
                  type="button"
                  className="text-sm font-bold text-primary hover:underline"
                  onClick={() => toast("Password reset isn't available yet.")}
                >
                  Forgot?
                </button>
              </div>
              <div className="relative">
                <Input
                  id="password"
                  type={showPw ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="h-12 rounded-2xl border-slate-200 bg-white px-4 pr-12 focus-visible:ring-2 focus-visible:ring-primary/30"
                  data-testid="login-password-input"
                />
                <button
                  type="button"
                  onClick={() => setShowPw((s) => !s)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  aria-label={showPw ? "Hide password" : "Show password"}
                  data-testid="toggle-password-visibility"
                >
                  {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
              {errors.password && (
                <p className="text-sm font-semibold text-destructive">{errors.password}</p>
              )}
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="h-12 w-full rounded-full text-base font-bold shadow-floating transition-all hover:-translate-y-0.5"
              data-testid="login-submit-button"
            >
              {loading ? <Loader2 size={18} className="mr-2 animate-spin" /> : null}
              {loading ? "Logging in..." : "Log in"}
            </Button>
          </form>

          <p className="mt-8 text-center text-slate-500">
            Don't have an account?{" "}
            <Link to="/register" className="font-bold text-primary hover:underline" data-testid="go-to-register-link">
              Sign up
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
