import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { LayoutDashboard, ScanLine, History, UploadCloud, Layers } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import albathaLogo from "../assets/albatha-logo.png";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/validate-new", label: "Start Validation", icon: ScanLine },
  { to: "/history", label: "History", icon: History },
  { to: "/validate", label: "Upload Invoice", icon: UploadCloud },
  { to: "/sscc-demo", label: "SSCC Proof", icon: Layers },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="h-screen flex overflow-hidden" style={{ background: "var(--color-paper)" }}>
      <aside
        className="w-60 shrink-0 h-full overflow-y-auto flex flex-col justify-between px-4 py-6"
        style={{ background: "linear-gradient(180deg, #0d2523, #0a1615)" }}
      >
        <div>
          <div className="flex items-center gap-2.5 px-2 mb-8">
            <div
              className="h-8 w-8 rounded-lg flex items-center justify-center shrink-0"
              style={{ background: "rgba(255,255,255,0.92)" }}
            >
              <img src={albathaLogo} alt="Albatha" className="h-5 w-5 object-contain" />
            </div>
            <div>
              <div className="text-white text-sm font-semibold leading-tight">Albatha / MPC</div>
              <div className="text-[10px] leading-tight" style={{ color: "#5a827e" }}>Validation POC</div>
            </div>
          </div>

          <nav className="space-y-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end
                className={({ isActive }) =>
                  `relative flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                    isActive ? "text-white" : "text-[#8fbdb9] hover:text-white"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <motion.div
                        layoutId="nav-active"
                        className="absolute inset-0 rounded-lg"
                        style={{ background: "rgba(20,184,166,0.16)" }}
                        transition={{ type: "spring", stiffness: 400, damping: 32 }}
                      />
                    )}
                    <item.icon size={16} strokeWidth={2} className="relative shrink-0" />
                    <span className="relative">{item.label}</span>
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="px-2">
          <div className="rounded-lg px-3 py-2.5 mb-2" style={{ background: "rgba(255,255,255,0.05)" }}>
            <div className="text-white text-xs font-medium truncate">{user?.name}</div>
            <div className="text-[10px] truncate" style={{ color: "#5a827e" }}>{user?.role}</div>
          </div>
          <button
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="w-full text-left text-xs font-medium text-[#8fbdb9] hover:text-white px-3 py-2 rounded-lg hover:bg-white/5 transition-colors"
          >
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 min-w-0 h-full overflow-y-auto">{children}</main>
    </div>
  );
}
