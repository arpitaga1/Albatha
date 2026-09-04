import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth, DEMO_CREDENTIALS } from "../context/AuthContext";
import albathaLogo from "../assets/albatha-logo.png";

const BLOBS = [
  { size: 520, top: "-10%", left: "-8%", color: "#0b7285", dur: 22 },
  { size: 420, top: "55%", left: "70%", color: "#0a5e6d", dur: 26 },
  { size: 340, top: "70%", left: "-5%", color: "#14b8a6", dur: 30 },
];

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState(DEMO_CREDENTIALS.email);
  const [password, setPassword] = useState(DEMO_CREDENTIALS.password);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setStatus("loading");
    setError(null);
    const result = await login(email, password);
    if (result.ok) {
      setStatus("success");
      setTimeout(() => navigate("/validate-new"), 700);
    } else {
      setStatus("error");
      setError(result.error ?? "Login failed");
    }
  }

  return (
    <div className="relative min-h-screen w-full overflow-hidden flex items-center justify-center"
         style={{ background: "linear-gradient(160deg, #0a1615 0%, #0d2523 45%, #0b3a3d 100%)" }}>
      {/* Animated background blobs */}
      {BLOBS.map((b, i) => (
        <motion.div
          key={i}
          className="absolute rounded-full blur-3xl opacity-30 pointer-events-none"
          style={{ width: b.size, height: b.size, top: b.top, left: b.left, background: b.color }}
          animate={{
            x: [0, 40, -20, 0],
            y: [0, -30, 20, 0],
            scale: [1, 1.08, 0.96, 1],
          }}
          transition={{ duration: b.dur, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}

      {/* Subtle grid overlay for a "systems" feel */}
      <div
        className="absolute inset-0 opacity-[0.06] pointer-events-none"
        style={{
          backgroundImage:
            "linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)",
          backgroundSize: "48px 48px",
        }}
      />

      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="relative z-10 w-full max-w-md mx-4"
      >
        <div className="mb-8 text-center">
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.15, duration: 0.5, ease: "backOut" }}
            className="inline-flex h-16 w-16 items-center justify-center rounded-2xl mb-4"
            style={{ background: "rgba(255,255,255,0.92)" }}
          >
            <img src={albathaLogo} alt="Albatha" className="h-10 w-10 object-contain" />
          </motion.div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Shipment Validation Platform</h1>
          <p className="text-sm mt-1" style={{ color: "#8fbdb9" }}>
            Albatha / MPC · Pharma &amp; Non-Pharma Reconciliation POC
          </p>
        </div>

        <div className="rounded-2xl p-8 backdrop-blur-xl border"
             style={{ background: "rgba(255,255,255,0.06)", borderColor: "rgba(255,255,255,0.12)" }}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: "#8fbdb9" }}>Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg px-3.5 py-2.5 text-sm text-white outline-none border transition-colors focus:border-[#14b8a6]"
                style={{ background: "rgba(255,255,255,0.06)", borderColor: "rgba(255,255,255,0.15)" }}
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: "#8fbdb9" }}>Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg px-3.5 py-2.5 text-sm text-white outline-none border transition-colors focus:border-[#14b8a6]"
                style={{ background: "rgba(255,255,255,0.06)", borderColor: "rgba(255,255,255,0.15)" }}
              />
            </div>

            <AnimatePresence>
              {status === "error" && (
                <motion.p
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="text-sm rounded-lg px-3 py-2"
                  style={{ background: "rgba(211,47,47,0.15)", color: "#ff8a80" }}
                >
                  {error}
                </motion.p>
              )}
            </AnimatePresence>

            <motion.button
              type="submit"
              disabled={status === "loading" || status === "success"}
              whileTap={{ scale: 0.98 }}
              className="w-full rounded-lg py-2.5 text-sm font-semibold text-[#06201f] flex items-center justify-center gap-2 disabled:opacity-80"
              style={{ background: "linear-gradient(135deg, #14b8a6, #5eead4)" }}
            >
              {status === "loading" && (
                <motion.span
                  className="h-3.5 w-3.5 rounded-full border-2 border-[#06201f] border-t-transparent"
                  animate={{ rotate: 360 }}
                  transition={{ duration: 0.7, repeat: Infinity, ease: "linear" }}
                />
              )}
              {status === "success" && (
                <motion.svg initial={{ scale: 0 }} animate={{ scale: 1 }} width="16" height="16" viewBox="0 0 24 24" fill="none">
                  <path d="M4 12l5 5L20 6" stroke="#06201f" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                </motion.svg>
              )}
              {status === "idle" && "Sign in"}
              {status === "loading" && "Signing in…"}
              {status === "success" && "Success - redirecting…"}
              {status === "error" && "Try again"}
            </motion.button>
          </form>

          <div className="mt-5 rounded-lg px-3.5 py-3 text-xs leading-relaxed"
               style={{ background: "rgba(20,184,166,0.08)", color: "#8fbdb9", border: "1px dashed rgba(20,184,166,0.3)" }}>
            <span className="font-semibold text-[#5eead4]">Demo credentials</span> (pre-filled - just click Sign in)
            <div className="mono mt-1 text-white/80">
              {DEMO_CREDENTIALS.email} / {DEMO_CREDENTIALS.password}
            </div>
          </div>
        </div>

        <p className="text-center text-xs mt-6" style={{ color: "#5a827e" }}>
          Proof-of-concept build - no real credentials, invoices, or Tatmeen data.
        </p>
      </motion.div>
    </div>
  );
}
