import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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

export default function SsccDemoPage() {
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .ssccNegativeControl()
      .then((r) => setResult(r as Result))
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="px-8 py-8 max-w-3xl">
      <Link to="/dashboard" className="text-sm text-[var(--color-accent)] hover:underline">
        ← Dashboard
      </Link>
      <h1 className="text-2xl font-bold mt-3 mb-1">SSCC / Case-Containment Negative Control</h1>
      <p className="text-[var(--color-muted)] mb-8 max-w-xl">
        Reproduces the Round 13–14 R&amp;D proof: two deliberately-injected faults run against Item 1's
        real captured data (12 boxes, case <span className="mono">1459466A0</span>), calling this app's
        actual rule 5 implementation - not the standalone research script - to confirm the shipped code
        still catches both.
      </p>

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
