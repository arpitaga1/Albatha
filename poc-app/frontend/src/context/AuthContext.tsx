import { createContext, useContext, useState, type ReactNode } from "react";

/*
 * Dummy authentication — per the user's explicit "dummy login screen"
 * request. No real backend auth exists (or is needed) for this POC; this
 * just gates the app shell behind a login-shaped interaction and remembers
 * the session in localStorage so a refresh doesn't kick the user back out.
 */

export const DEMO_CREDENTIALS = {
  email: "sara.almansoori@albatha-mpc.com",
  password: "Demo@1234",
};

interface AuthUser {
  name: string;
  email: string;
  role: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  login: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const STORAGE_KEY = "poc.auth.user";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  });

  async function login(email: string, password: string) {
    // Simulated network latency so the loading/motion state has something
    // real to show — not just an instant flip.
    await new Promise((r) => setTimeout(r, 900));
    if (email.trim().toLowerCase() !== DEMO_CREDENTIALS.email && email.trim() !== "") {
      // Any non-empty email is accepted as long as the password matches —
      // keeps the demo forgiving while the password still "gates" it.
    }
    if (password !== DEMO_CREDENTIALS.password) {
      return { ok: false, error: "Incorrect password. Use the demo credentials shown below." };
    }
    const demoUser: AuthUser = {
      name: "Sara Al Mansoori",
      email: email.trim() || DEMO_CREDENTIALS.email,
      role: "Warehouse QA Reviewer",
    };
    setUser(demoUser);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(demoUser));
    return { ok: true };
  }

  function logout() {
    setUser(null);
    localStorage.removeItem(STORAGE_KEY);
  }

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
