import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Camera, Sparkles } from "lucide-react";
import { api } from "../api";
import { formatApiError } from "../errors";
import { useAuth } from "../context/AuthContext";
import ScannerFrame from "./ScannerFrame";
import ItemsTable from "./ItemsTable";
import type { Corrections } from "./ItemDetailModal";
import UnmatchedItemCard from "./UnmatchedItemCard";
import type { Invoice, RealScanResponse, UnmatchedBarcode, ValidationResult } from "../types";

type Mode = "real" | "simulate";

/**
 * Demo-scenario scan flow for SAP-sourced invoices. Supports TWO modes,
 * both driven by the exact same photo-capture UI (ScannerFrame) so upload
 * and "scan" are literally the same action either way — per user feedback
 * that the two needed to behave consistently rather than upload silently
 * being ignored in favor of a seed pick:
 *
 * - **Real Photo Scan** (default): the uploaded photo(s) are genuinely
 *   decoded server-side (zxing-cpp DataMatrix decode,
 *   `/api/scans/upload-real`) — the exact same real pipeline RealScanFlow
 *   uses for uploaded invoices, including support for multiple photos in
 *   one submission (e.g. one photo per item type) combined into a single
 *   result list. Works for any SAP invoice whose pharma line items carry a
 *   real GTIN (Item 1's actual photo, Picture1.png, is the best real test
 *   case).
 * - **Simulate Scenario**: the previous seed-picker behavior, kept because
 *   several of the 7 demo flows (not-reported, SSCC-not-reported, expired,
 *   blurry, OCR-fallback, non-pharma) describe outcomes no real photo in
 *   this repo can actually produce — a real decode of Item 1 can only ever
 *   yield one true result, it can't demonstrate "Tatmeen says not
 *   reported." The photo itself is cosmetic in this mode.
 */
export default function MockScanFlow({ invoice }: { invoice: Invoice }) {
  const { user } = useAuth();
  const [mode, setMode] = useState<Mode>("real");
  const [results, setResults] = useState<Record<number, ValidationResult>>({});
  const [unmatched, setUnmatched] = useState<UnmatchedBarcode[]>([]);
  const [seeds, setSeeds] = useState<string[]>([]);
  const [selectedSeed, setSelectedSeed] = useState<Record<number, string>>({});
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [tatmeenRevealed, setTatmeenRevealed] = useState<Set<number>>(new Set());
  const [tatmeenChecking, setTatmeenChecking] = useState<Set<number>>(new Set());
  const [loaded, setLoaded] = useState(false);

  // State persistence — same fix as RealScanFlow: reload existing results
  // on mount so re-opening (or, previously, switching away and back)
  // never loses what was already scanned.
  useEffect(() => {
    api.listSeeds().then(setSeeds).catch(() => setSeeds([]));
    api.getResultsForInvoice(invoice.invoice_number).then((r) => {
      setResults(r);
      const revealed = new Set(
        Object.values(r).filter((v) => v.tatmeen_status !== "n_a").map((v) => v.line_item_id)
      );
      setTatmeenRevealed(revealed);
      setLoaded(true);
    }).catch(() => setLoaded(true));
  }, [invoice.invoice_number]);

  function addFiles(newFiles: File[]) {
    setError(null);
    setScanMessage(null);
    setFiles((prev) => [...prev, ...newFiles]);
    setPreviews((prev) => [...prev, ...newFiles.map((f) => URL.createObjectURL(f))]);
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setPreviews((prev) => {
      URL.revokeObjectURL(prev[index]);
      return prev.filter((_, i) => i !== index);
    });
  }

  function clearFiles() {
    previews.forEach((p) => URL.revokeObjectURL(p));
    setFiles([]);
    setPreviews([]);
  }

  async function scanReal() {
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    setScanMessage(null);
    try {
      const res: RealScanResponse = await api.uploadRealScan(invoice.invoice_number, files);
      if (res.message) setScanMessage(res.message);
      setResults((prev) => {
        const next = { ...prev };
        for (const r of res.results) next[r.line_item_id] = r;
        return next;
      });
      setUnmatched(res.unmatched);
      clearFiles();
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  async function scanSimulated() {
    const toScan = invoice.line_items.filter((li) => selectedSeed[li.id]);
    if (toScan.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const settled = await Promise.all(
        toScan.map((li) => api.scanMock(li.id, selectedSeed[li.id]))
      );
      setResults((prev) => {
        const next = { ...prev };
        for (const r of settled) next[r.line_item_id] = r;
        return next;
      });
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  async function resolve(lineItemId: number, action: "accepted" | "rejected", note: string) {
    const r = await api.resolveDiscrepancy(lineItemId, action, note, undefined, user?.name);
    setResults((prev) => ({ ...prev, [lineItemId]: r }));
  }

  async function update(lineItemId: number, corrections: Corrections, note: string) {
    const r = await api.correctScan(lineItemId, corrections, note, user?.name);
    setResults((prev) => ({ ...prev, [lineItemId]: r }));
  }

  function handleAssigned(index: number, result: ValidationResult) {
    setUnmatched((prev) => prev.filter((_, i) => i !== index));
    setResults((prev) => ({ ...prev, [result.line_item_id]: result }));
  }

  // Bulk Tatmeen validation - see RealScanFlow's identical function for
  // the full reasoning (client feedback: one action validates every
  // currently-eligible item together, not one button per item).
  function revealTatmeenBulk(lineItemIds: number[]) {
    setTatmeenChecking((prev) => new Set([...prev, ...lineItemIds]));
    setTimeout(() => {
      setTatmeenChecking((prev) => {
        const next = new Set(prev);
        lineItemIds.forEach((id) => next.delete(id));
        return next;
      });
      setTatmeenRevealed((prev) => new Set([...prev, ...lineItemIds]));
    }, 1400);
  }

  if (!loaded) return <p className="text-sm text-[var(--color-muted)]">Loading…</p>;

  const anySelected = invoice.line_items.some((li) => selectedSeed[li.id]);

  return (
    <div>
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            Scan box / item
          </div>
          {/* Mode toggle - both use the same ScannerFrame upload action below,
              this only decides how the captured photo(s) get interpreted. */}
          <div className="inline-flex rounded-lg border p-0.5 bg-white" style={{ borderColor: "var(--color-line)" }}>
            {([
              { key: "real" as Mode, label: "Real Photo Scan", Icon: Camera },
              { key: "simulate" as Mode, label: "Simulate Scenario", Icon: Sparkles },
            ]).map((m) => (
              <button
                key={m.key}
                onClick={() => { setMode(m.key); setError(null); setScanMessage(null); }}
                className="relative flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors"
                style={mode === m.key ? { color: "white" } : { color: "var(--color-muted)" }}
              >
                {mode === m.key && (
                  <motion.div
                    layoutId="scan-mode-pill"
                    className="absolute inset-0 rounded-md"
                    style={{ background: "var(--color-accent)" }}
                    transition={{ type: "spring", stiffness: 400, damping: 32 }}
                  />
                )}
                <m.Icon size={12} className="relative" strokeWidth={2.5} />
                <span className="relative">{m.label}</span>
              </button>
            ))}
          </div>
        </div>

        <ScannerFrame
          files={files}
          previews={previews}
          onAddFiles={addFiles}
          onRemoveFile={removeFile}
          status={
            busy ? (mode === "real" ? "Decoding barcode(s)…" : "Scanning…")
              : files.length > 0 ? (mode === "real" ? "Photo(s) captured - ready for real barcode decode" : "Photo captured - select what's inside below, then scan")
              : mode === "real" ? "Ready - upload one or more real item/box photos, decoded genuinely (no seed data)" : "Ready to scan - seeded demo, this one photo represents the whole carton"
          }
          statusVariant={busy ? "active" : files.length > 0 ? "success" : "idle"}
        >
          {mode === "real" && files.length > 0 && (
            <button
              onClick={scanReal}
              disabled={busy}
              className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              style={{ background: "var(--color-accent)" }}
            >
              {busy ? "Decoding…" : files.length > 1 ? `Scan ${files.length} Photos` : "Scan Photo"}
            </button>
          )}
        </ScannerFrame>

        {mode === "simulate" && (
          <div className="mt-4 rounded-xl border bg-white p-4" style={{ borderColor: "var(--color-line)" }}>
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
              What's inside this photo (per item)
            </div>
            <div className="space-y-2">
              {invoice.line_items.map((li) => (
                <div key={li.id} className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium">{li.item_name}</div>
                  <select
                    value={selectedSeed[li.id] ?? ""}
                    onChange={(e) => setSelectedSeed((prev) => ({ ...prev, [li.id]: e.target.value }))}
                    className="border rounded-md px-2 py-1.5 text-sm bg-white min-w-[220px]"
                    style={{ borderColor: "var(--color-line)" }}
                  >
                    <option value="">Not in this photo…</option>
                    {seeds.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </div>
        )}

        {mode === "simulate" && (
          <button
            onClick={scanSimulated}
            disabled={!anySelected || busy}
            className="mt-3 rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            style={{ background: "var(--color-accent)" }}
          >
            {busy ? "Scanning…" : "Scan Photo"}
          </button>
        )}

        {error && <p className="text-sm text-[var(--color-red)] mt-2">{error}</p>}
        {scanMessage && (
          <p className="text-sm rounded-lg p-3 mt-2" style={{ background: "var(--color-yellow-tint)", color: "var(--color-yellow)" }}>
            {scanMessage}
          </p>
        )}
      </div>

      {unmatched.length > 0 && (
        <div className="space-y-3 mb-6">
          {unmatched.map((u, i) => (
            <UnmatchedItemCard key={i} item={u} invoice={invoice} onAssigned={(result) => handleAssigned(i, result)} />
          ))}
        </div>
      )}

      <ItemsTable
        invoice={invoice}
        results={results}
        tatmeenRevealed={tatmeenRevealed}
        tatmeenChecking={tatmeenChecking}
        onResolve={resolve}
        onUpdate={update}
        onRevealTatmeenBulk={revealTatmeenBulk}
      />
    </div>
  );
}
