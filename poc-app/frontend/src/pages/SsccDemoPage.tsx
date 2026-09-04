import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { RotateCcw, Loader2, CheckCircle2 } from "lucide-react";
import { api } from "../api";

interface Finding {
  rule: string;
  severity: string;
  message: string;
}
interface Scenario {
  description: string;
  findings: Finding[];
}
interface Result {
  scenario_a_foreign_serial: Scenario;
  scenario_b_case_mismatch: Scenario;
}

type ReseedState = "idle" | "confirm" | "busy" | "done" | "error";

export default function SsccDemoPage() {
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reseedState, setReseedState] = useState<ReseedState>("idle");

  useEffect(() => {
    api
      .ssccNegativeControl()
      .then((r) => setResult(r as Result))
      .catch((e) => setError(String(e)));
  }, []);

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
    <div className="px-8 py-8 max-w-3xl">
      <Link to="/dashboard" className="text-sm text-[var(--color-accent)] hover:underline">
        ← Dashboard
      </Link>
      <h1 className="text-2xl font-bold mt-3 mb-1">SSCC / Case-Containment Negative Control</h1>
      <p className="text-[var(--color-muted)] mb-6 max-w-xl">
        Reproduces the Round 13–14 R&amp;D proof: two deliberately-injected faults run against Item 1's
        real captured data (12 boxes, case <span className="mono">1459466A0</span>), calling this app's
        actual rule 5 implementation - not the standalone research script - to confirm the shipped code
        still catches both.
      </p>

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

      {error && <p className="text-[var(--color-red)]">{error}</p>}
      {!result && !error && <p className="text-[var(--color-muted)]">Running…</p>}

      {result && (
        <div className="grid gap-4">
          <ScenarioCard title="Scenario A - foreign serial in the case" scenario={result.scenario_a_foreign_serial} />
          <ScenarioCard title="Scenario B - unit mispacked into the wrong case" scenario={result.scenario_b_case_mismatch} />
        </div>
      )}
    </div>
  );
}

function ScenarioCard({ title, scenario }: { title: string; scenario: Scenario }) {
  return (
    <div className="rounded-lg border bg-white p-5" style={{ borderColor: "var(--color-line)" }}>
      <h2 className="font-semibold mb-1">{title}</h2>
      <p className="text-sm text-[var(--color-muted)] mb-3">{scenario.description}</p>
      <ul className="space-y-1 text-sm">
        {scenario.findings.map((f, i) => (
          <li key={i} className="text-[var(--color-red)]">
            <span className="mono text-xs opacity-70">[{f.rule}]</span> {f.message}
          </li>
        ))}
      </ul>
    </div>
  );
}
