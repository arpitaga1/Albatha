import type { AllShipmentsSummary, Dashboard, Invoice, InvoiceSummary, RealScanResponse, SapInvoiceRow, ValidationResult } from "./types";

// Local dev keeps hitting the relative "/api" path, which Vite's dev
// server proxies to the local backend (see vite.config.ts) - nothing
// changes there. A production build has no such proxy, so it needs the
// deployed backend's real URL instead, via VITE_API_BASE_URL (set in
// Vercel's project settings once the backend has a Render URL).
const BASE = `${import.meta.env.VITE_API_BASE_URL ?? ""}/api`;

// Every uploaded invoice document and scanned item photo is saved
// server-side and served back read-only at /api/files/<name> — this turns
// the filename the API returns into a clickable URL, so a user can reopen
// exactly what they uploaded, both right after upload and when reviewing a
// completed item later.
export function fileUrl(name: string | null | undefined): string | null {
  return name ? `${BASE}/files/${encodeURIComponent(name)}` : null;
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  listInvoices: () => fetch(`${BASE}/invoices`).then((r) => j<InvoiceSummary[]>(r)),
  listSapInvoices: () => fetch(`${BASE}/invoices/sap`).then((r) => j<SapInvoiceRow[]>(r)),
  listPreloadedInvoices: () => fetch(`${BASE}/invoices/preloaded`).then((r) => j<SapInvoiceRow[]>(r)),
  searchSapInvoice: (invoiceNumber: string) =>
    fetch(`${BASE}/invoices/sap/search/${encodeURIComponent(invoiceNumber)}`).then((r) => j<SapInvoiceRow>(r)),
  getInvoice: (invoiceNumber: string) =>
    fetch(`${BASE}/invoices/${invoiceNumber}`).then((r) => j<Invoice>(r)),
  getDashboard: (invoiceNumber: string) =>
    fetch(`${BASE}/dashboard/${invoiceNumber}`).then((r) => j<Dashboard>(r)),
  getAllShipmentsSummary: () =>
    fetch(`${BASE}/dashboard/summary/all`).then((r) => j<AllShipmentsSummary>(r)),
  listSeeds: () => fetch(`${BASE}/scans/seeds`).then((r) => j<string[]>(r)),
  scanMock: (lineItemId: number, seedKey: string) =>
    fetch(`${BASE}/scans/mock`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ line_item_id: lineItemId, seed_key: seedKey }),
    }).then((r) => j<ValidationResult>(r)),
  ssccNegativeControl: () =>
    fetch(`${BASE}/demo/sscc-negative-control`).then((r) => j<unknown>(r)),
  reseedDatabase: () =>
    fetch(`${BASE}/demo/reseed`, { method: "POST" }).then((r) => j<{ status: string; invoices: number }>(r)),

  // --- Real (no mock, no API key) extraction ---
  uploadInvoice: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`${BASE}/invoices/upload`, { method: "POST", body: fd }).then((r) => j<Invoice>(r));
  },
  uploadRealScan: (invoiceNumber: string, files: File[]) => {
    const fd = new FormData();
    fd.append("invoice_number", invoiceNumber);
    for (const f of files) fd.append("files", f);
    return fetch(`${BASE}/scans/upload-real`, { method: "POST", body: fd }).then((r) =>
      j<RealScanResponse>(r)
    );
  },
  // Gemini 3.5 Flash vision extraction - alternative engine to the classical
  // barcode/OpenCV pipeline above. Same request/response shape so callers
  // can swap between the two with no other changes.
  uploadGeminiScan: (invoiceNumber: string, files: File[]) => {
    const fd = new FormData();
    fd.append("invoice_number", invoiceNumber);
    for (const f of files) fd.append("files", f);
    return fetch(`${BASE}/scans/upload-gemini`, { method: "POST", body: fd }).then((r) =>
      j<RealScanResponse>(r)
    );
  },
  getResultsForInvoice: (invoiceNumber: string) =>
    fetch(`${BASE}/scans/results/${invoiceNumber}`).then((r) => j<Record<number, ValidationResult>>(r)),
  resolveDiscrepancy: (
    lineItemId: number,
    action: "accepted" | "rejected",
    note: string,
    corrections?: { gtin?: string; batch?: string; qty?: string; expiry?: string },
    reviewerName?: string
  ) => {
    const fd = new FormData();
    fd.append("action", action);
    fd.append("note", note);
    if (corrections?.gtin) fd.append("corrected_gtin", corrections.gtin);
    if (corrections?.batch) fd.append("corrected_batch", corrections.batch);
    if (corrections?.qty) fd.append("corrected_qty", corrections.qty);
    if (corrections?.expiry) fd.append("corrected_expiry", corrections.expiry);
    if (reviewerName) fd.append("reviewer_name", reviewerName);
    return fetch(`${BASE}/scans/${lineItemId}/resolve`, { method: "POST", body: fd }).then((r) =>
      j<ValidationResult>(r)
    );
  },
  correctScan: (
    lineItemId: number,
    corrections: { gtin?: string; batch?: string; qty?: string; expiry?: string },
    note: string,
    reviewerName?: string
  ) => {
    const fd = new FormData();
    if (corrections.gtin) fd.append("corrected_gtin", corrections.gtin);
    if (corrections.batch) fd.append("corrected_batch", corrections.batch);
    if (corrections.qty) fd.append("corrected_qty", corrections.qty);
    if (corrections.expiry) fd.append("corrected_expiry", corrections.expiry);
    fd.append("note", note);
    if (reviewerName) fd.append("reviewer_name", reviewerName);
    return fetch(`${BASE}/scans/${lineItemId}/correct`, { method: "POST", body: fd }).then((r) =>
      j<ValidationResult>(r)
    );
  },
  getScanHistory: (lineItemId: number) =>
    fetch(`${BASE}/scans/${lineItemId}/history`).then((r) =>
      j<{
        id: number; created_at: string | null; superseded: boolean; is_correction: boolean;
        gtin: string | null; batch: string | null; expiry: string | null; scanned_qty: number; notes: string[];
      }[]>(r)
    ),
  manualAssign: (
    invoiceNumber: string,
    lineItemId: number,
    data: { gtin: string; batch: string; qty: string; expiry: string; note: string }
  ) => {
    const fd = new FormData();
    fd.append("invoice_number", invoiceNumber);
    fd.append("line_item_id", String(lineItemId));
    fd.append("gtin", data.gtin);
    fd.append("batch", data.batch);
    fd.append("qty", data.qty);
    fd.append("expiry", data.expiry);
    fd.append("note", data.note);
    return fetch(`${BASE}/scans/manual-assign`, { method: "POST", body: fd }).then((r) => j<ValidationResult>(r));
  },
};
