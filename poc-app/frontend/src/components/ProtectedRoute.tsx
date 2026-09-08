import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({
  children, navPath,
}: {
  children: ReactNode;
  // Which sidebar nav path (see AppShell's NAV) this route corresponds to.
  // If the logged-in account is restricted (user.allowedNav) and doesn't
  // include this path, redirect instead of rendering - keeps a typed-in
  // URL from bypassing a hidden tab. Routes with no nav entry of their own
  // (e.g. the invoice detail page, reached from an allowed page) pass
  // nothing here and are always allowed once logged in.
  navPath?: string;
}) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (navPath && user.allowedNav && !user.allowedNav.includes(navPath)) {
    return <Navigate to={user.allowedNav[0] ?? "/login"} replace />;
  }
  return <>{children}</>;
}
