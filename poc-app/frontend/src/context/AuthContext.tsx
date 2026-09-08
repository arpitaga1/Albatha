import { createContext, useContext, useState, type ReactNode } from "react";

/*
 * Dummy authentication — per the user's explicit "dummy login screen"
 * request. No real backend auth exists (or is needed) for this POC; this
 * just gates the app shell behind a login-shaped interaction and remembers
 * the session in localStorage so a refresh doesn't kick the user back out.
 */

interface DemoUser {
  name: string;
  email: string;
  password: string;
  role: string;
  // Sidebar nav paths (see AppShell's NAV) this account is limited to -
  // undefined/omitted means full access to every tab.
  allowedNav?: string[];
}

// Two dummy demo accounts. Sara (Warehouse QA Reviewer) is scoped to just
// Start Validation + History, per client request - she only ever needs to
// run a validation and look up past ones, not the dashboard/upload/SSCC
// admin-ish pages. Rashid (Operations Manager) keeps full access to every
// tab, same as this POC's original single-account behavior.
export const DEMO_USERS: DemoUser[] = [
  {
    name: "Sara Al Mansoori",
    email: "sara.almansoori@albatha-mpc.com",
    password: "Demo@1234",
    role: "Worker",
    allowedNav: ["/validate-new", "/history"],
  },
  {
    name: "Rashid Al Suwaidi",
    email: "rashid.alsuwaidi@albatha-mpc.com",
    password: "Demo@1234",
    role: "Manager",
  },
];

export const DEMO_CREDENTIALS = { email: DEMO_USERS[0].email, password: DEMO_USERS[0].password };

interface AuthUser {
  name: string;
  email: string;
  role: string;
  allowedNav?: string[];
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
    const trimmedEmail = email.trim();
    // Blank email defaults to the first demo account, same forgiving
    // behavior as before; a non-blank email must match one of the known
    // demo accounts so the right name/role gets assigned.
    const candidateEmail = trimmedEmail === "" ? DEMO_USERS[0].email : trimmedEmail;
    const match = DEMO_USERS.find((u) => u.email.toLowerCase() === candidateEmail.toLowerCase());
    if (!match || password !== match.password) {
      return { ok: false, error: "Incorrect email or password. Use one of the demo accounts shown below." };
    }
    const demoUser: AuthUser = { name: match.name, email: match.email, role: match.role, allowedNav: match.allowedNav };
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
