import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/Brand";
import { api } from "@/lib/api";
import { useAuth } from "@/App";
import { toast } from "sonner";
import { Check, Eye, EyeOff, Loader2, X } from "lucide-react";

export default function Register() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
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
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setErrors(err.fieldErrors || {});
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fieldError = (name) =>
    errors[name] ? (
      <p className="text-sm font-semibold text-destructive">{errors[name]}</p>
    ) : null;

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Left form */}
      <div className="flex items-center justify-center bg-background px-6 py-12">
        <div className="w-full max-w-md rc-fade-up">
          <div className="mb-8 flex justify-center lg:justify-start">
            <Logo />
          </div>
          <h1 className="text-3xl font-extrabold text-slate-900">Create your account</h1>
          <p className="mt-2 text-slate-500">Start creating and joining rooms in seconds.</p>

          <form onSubmit={handleRegister} className="mt-7 space-y-4" data-testid="register-form">
            <div className="space-y-2">
              <Label htmlFor="username" className="font-bold text-slate-700">Username</Label>
              <Input
                id="username"
                value={form.username}
                onChange={set("username")}
                placeholder="alex_rivera"
                autoFocus
                className="h-12 rounded-2xl border-slate-200 bg-white px-4 focus-visible:ring-2 focus-visible:ring-primary/30"
                data-testid="register-username-input"
              />
              {fieldError("username")}
            </div>
            <div className="space-y-2">
              <Label htmlFor="email" className="font-bold text-slate-700">Email</Label>
              <Input
                id="email"
                type="email"
                value={form.email}
                onChange={set("email")}
                placeholder="you@example.com"
                className="h-12 rounded-2xl border-slate-200 bg-white px-4 focus-visible:ring-2 focus-visible:ring-primary/30"
                data-testid="register-email-input"
              />
              {fieldError("email")}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="password" className="font-bold text-slate-700">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPw ? "text" : "password"}
                    value={form.password}
                    onChange={set("password")}
                    placeholder="••••••••"
                    className="h-12 rounded-2xl border-slate-200 bg-white px-4 pr-11 focus-visible:ring-2 focus-visible:ring-primary/30"
                    data-testid="register-password-input"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw((s) => !s)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                    aria-label={showPw ? "Hide password" : "Show password"}
                  >
                    {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
                {fieldError("password")}
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirm" className="font-bold text-slate-700">Confirm</Label>
                <Input
                  id="confirm"
                  type={showPw ? "text" : "password"}
                  value={form.confirm}
                  onChange={set("confirm")}
                  placeholder="••••••••"
                  className="h-12 rounded-2xl border-slate-200 bg-white px-4 focus-visible:ring-2 focus-visible:ring-primary/30"
                  data-testid="register-confirm-input"
                />
                {fieldError("confirm_password")}
              </div>
            </div>

            <div className="grid gap-2 rounded-2xl bg-secondary/60 p-4 sm:grid-cols-3">
              {rules.map((r) => (
                <div key={r.label} className="flex items-center gap-2 text-sm font-semibold">
                  <span
                    className={`grid h-5 w-5 place-items-center rounded-full ${
                      r.ok ? "bg-green-500 text-white" : "bg-slate-200 text-slate-400"
                    }`}
                  >
                    {r.ok ? <Check size={12} /> : <X size={12} />}
                  </span>
                  <span className={r.ok ? "text-slate-700" : "text-slate-400"}>{r.label}</span>
                </div>
              ))}
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="h-12 w-full rounded-full text-base font-bold shadow-floating transition-all hover:-translate-y-0.5"
              data-testid="register-submit-button"
            >
              {loading ? <Loader2 size={18} className="mr-2 animate-spin" /> : null}
              {loading ? "Creating account..." : "Create account"}
            </Button>
          </form>

          <p className="mt-6 text-center text-slate-500">
            Already have an account?{" "}
            <Link to="/login" className="font-bold text-primary hover:underline" data-testid="go-to-login-link">
              Log in
            </Link>
          </p>
        </div>
      </div>

      {/* Right brand panel */}
      <div className="relative hidden flex-col justify-between bg-primary p-12 text-white lg:flex">
        <div />
        <div className="max-w-md">
          <h2 className="text-4xl font-extrabold leading-tight">One code away from every conversation.</h2>
          <p className="mt-4 text-lg text-white/80">
            Rooms of 2 to 100 people. Invite friends, hand off ownership, keep it private — all
            with a warm, familiar feel.
          </p>
          <div className="mt-10 rounded-3xl bg-white/10 p-6 backdrop-blur">
            <p className="text-sm font-bold uppercase tracking-wide text-white/70">Sample room code</p>
            <p className="mt-2 font-mono text-3xl font-extrabold tracking-[0.3em]">DSN9Q2</p>
          </div>
        </div>
        <p className="text-sm text-white/60">© 2026 RoomChat</p>
      </div>
    </div>
  );
}
