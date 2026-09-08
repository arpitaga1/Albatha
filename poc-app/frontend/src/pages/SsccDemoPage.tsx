import { useState } from "react";
import { RotateCcw, Loader2, CheckCircle2, Sparkles, ShieldCheck, Database, ScanLine } from "lucide-react";
import { api } from "../api";

type ReseedState = "idle" | "confirm" | "busy" | "done" | "error";

// Purely a dummy status display, per user directive - these toggles don't
// call the backend or configure anything; they just show which
// integrations this POC has wired up, all on, for the client demo.
const INTEGRATIONS = [
  { name: "AI Vision", description: "Box counting & cross-checking against the physical shipment", Icon: Sparkles },
  { name: "Tatmeen", description: "Simulated national track-and-trace database", Icon: ShieldCheck },
  { name: "Invoice from SAP", description: "Invoice data sourced directly from SAP", Icon: Database },
  { name: "Data Extraction", description: "Reads GTIN, batch, expiry, and quantity directly off the item label", Icon: ScanLine },
];

export default function SsccDemoPage() {
  const [reseedState, setReseedState] = useState<ReseedState>("idle");
  const [integrationsOn, setIntegrationsOn] = useState<boolean[]>(INTEGRATIONS.map(() => true));

  async function reseed() {
    setReseedState("busy");
    try {
      await api.reseedDatabase();
      setReseedState("done");
      setTimeout(() => setReseedState("idle"), 2500);
    } catch {
      setReseedState("error");
    }
  }

  return (
    <div className="px-8 py-8">
      <h1 className="text-2xl font-bold mb-1">Configurations</h1>
      <p className="text-[var(--color-muted)] mb-6 max-w-2xl">
        System integrations and demo data controls.
      </p>

      {/* --- Reset Demo Data, at the top --- */}
      <div className="rounded-lg border bg-white p-5 mb-8 flex items-center justify-between gap-4" style={{ borderColor: "var(--color-line)" }}>
        <div>
          <h2 className="font-semibold text-sm mb-0.5">Reset Demo Data</h2>
          <p className="text-xs text-[var(--color-muted)] max-w-md">
            Wipes every scan and validation result, then restores all invoices to their original,
            never-scanned state - the whole system looks freshly installed again.
          </p>
        </div>

        {reseedState === "confirm" ? (
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs font-medium text-[var(--color-muted)]">Erase all scan data?</span>
            <button
              onClick={reseed}
              className="rounded-lg px-3 py-2 text-xs font-semibold text-white hover:opacity-90 transition-opacity"
              style={{ background: "var(--color-red)" }}
            >
              Yes, reset
            </button>
            <button
              onClick={() => setReseedState("idle")}
              className="rounded-lg px-3 py-2 text-xs font-medium hover:bg-[var(--color-paper)] transition-colors"
              style={{ border: "1px solid var(--color-line)" }}
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            onClick={() => setReseedState("confirm")}
            disabled={reseedState === "busy"}
            className="shrink-0 inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60 hover:opacity-90 transition-opacity"
            style={{ background: "linear-gradient(135deg, var(--color-accent), #0a5e6d)" }}
          >
            {reseedState === "busy" ? (
              <>
                <Loader2 size={15} className="animate-spin" />
                Resetting…
              </>
            ) : reseedState === "done" ? (
              <>
                <CheckCircle2 size={15} />
                Reset complete
              </>
            ) : (
              <>
                <RotateCcw size={15} strokeWidth={2.25} />
                Reset Demo Data
              </>
            )}
          </button>
        )}
      </div>

      {reseedState === "error" && (
        <p className="text-sm text-[var(--color-red)] -mt-4 mb-6">
          Reset failed - check the backend is running and try again.
        </p>
      )}

      {/* --- Integrations status --- */}
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-2.5">
          Integrations
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {INTEGRATIONS.map((integ, i) => (
            <div
              key={integ.name}
              className="rounded-lg border bg-white p-4 flex flex-col gap-3"
              style={{ borderColor: "var(--color-line)" }}
            >
              <div className="flex items-center justify-between gap-2">
                <div
                  className="h-9 w-9 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: "var(--color-paper)" }}
                >
                  <integ.Icon size={16} style={{ color: "var(--color-accent)" }} strokeWidth={2.25} />
                </div>
                <button
                  role="switch"
                  aria-checked={integrationsOn[i]}
                  onClick={() => setIntegrationsOn((prev) => prev.map((v, idx) => (idx === i ? !v : v)))}
                  className="relative shrink-0 transition-colors"
                  style={{
                    width: 44,
                    height: 24,
                    borderRadius: 999,
                    boxSizing: "border-box",
                    background: integrationsOn[i] ? "var(--color-green)" : "var(--color-line)",
                    border: `1px solid ${integrationsOn[i] ? "var(--color-green)" : "var(--color-muted)"}`,
                  }}
                >
                  <span
                    className="absolute rounded-full bg-white transition-transform"
                    style={{
                      top: 2,
                      left: 2,
                      width: 18,
                      height: 18,
                      transform: integrationsOn[i] ? "translateX(22px)" : "translateX(0px)",
                      boxShadow: "0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(0,0,0,0.06)",
                    }}
                  />
                </button>
              </div>
              <div>
                <div className="text-sm font-semibold">{integ.name}</div>
                <div className="text-xs text-[var(--color-muted)] mt-0.5">{integ.description}</div>
              </div>
              <span
                className="inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full w-fit"
                style={
                  integrationsOn[i]
                    ? { background: "var(--color-green-tint)", color: "var(--color-green)" }
                    : { background: "var(--color-line)", color: "var(--color-muted)" }
                }
              >
                {integrationsOn[i] ? "Integrated" : "Off"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
