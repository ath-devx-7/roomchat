import "@/App.css";
import { createContext, useContext, useMemo, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { BOOTSTRAP } from "@/lib/api";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Dashboard from "@/pages/Dashboard";
import ChatRoom from "@/pages/ChatRoom";

// Seeded from window.__ROOMCHAT__, which Django renders into the shell. That means the
// first paint already knows whether the session is valid — no signed-out flash, and no
// /api/auth/me/ round-trip before the router can decide where to send the user.
const AuthContext = createContext(null);

export const useAuth = () => useContext(AuthContext);

function RequireAuth({ children }) {
  const { user } = useAuth();
  return user ? children : <Navigate to="/login" replace />;
}

function RedirectIfAuthed({ children }) {
  const { user } = useAuth();
  return user ? <Navigate to="/dashboard" replace /> : children;
}

function App() {
  const [user, setUser] = useState(BOOTSTRAP.user);
  const value = useMemo(() => ({ user, setUser }), [user]);

  return (
    <div className="App">
      <AuthContext.Provider value={value}>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<RedirectIfAuthed><Login /></RedirectIfAuthed>} />
            <Route path="/register" element={<RedirectIfAuthed><Register /></RedirectIfAuthed>} />
            <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
            <Route path="/room/:code" element={<RequireAuth><ChatRoom /></RequireAuth>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthContext.Provider>
      <Toaster position="top-right" richColors closeButton />
    </div>
  );
}

export default App;
