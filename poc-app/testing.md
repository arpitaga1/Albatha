# Testing Guide — Pharma & Non-Pharma Shipment Validation POC

Reference this whenever you sit down to test. Covers: how to start/reset the
app, then a checklist for every screen and flow, with what to expect at each
step. If actual behavior differs from "Expect," that's a real bug — note the
step and report it back.

---

## 0. Start / reset the app

**Backend:**
```
cd poc-app/backend
python -m uvicorn app.main:app --port 8000
```

**Frontend** (separate terminal):
```
cd poc-app/frontend
npm run dev
```

Open **http://localhost:5173**.

**To reset to a clean slate** (wipe all test data, re-seed the 8 SAP
invoices as "not scanned"):
1. Stop the backend (Ctrl+C).
2. Delete `poc-app/backend/poc.db`.
3. Restart the backend — it re-seeds automatically on first request.

Do this before any testing session where you want a fresh start, and any
time results look stale or contradictory.

---

## 1. Login

- [ ] Demo credentials are pre-filled (`demo@albatha-mpc.com` / `Demo@1234`) — click **Sign in**.
- [ ] Expect: animated dark gradient background, spinner → checkmark, redirect to Dashboard.
- [ ] Try a wrong password once — expect a red inline error, no redirect.

---

## 2. Dashboard

- [ ] 4 stat tiles: Total, Validated, Pending, Exceptions — should match reality (all 0 validated on a clean slate).
- [ ] "Start New Validation" card links to Start Validation.
- [ ] "Recent activity" list — empty or shows only what you've actually scanned.

---

## 3. Start Validation — real, live extraction

This is the **real** path: genuine OCR on the invoice, genuine barcode decode on the photo. No seed data.

### 3a. Invoices from SAP (top section)
- [ ] Table shows 8 rows (INV001–INV008), each tagged **"Fetched from SAP"**, with Invoice Number / Date / Supplier / Items / Total Qty / Status.
- [ ] Click a row → opens that invoice's wizard (see §4 SAP-sourced flow below).

### 3b. Upload Invoice (right section)
- [ ] Upload `Sample Invoice.pdf` (project root) → click **Upload & Extract**.
- [ ] Expect: redirects to a new invoice tagged **"Real upload — live extraction"**, showing 7–8 real OCR'd line items (GTINs like `3760095250090`, items like "WHITE CREAM"). Minor OCR character errors (e.g. "R25HO3" instead of "R25H03") are expected — real OCR, not fake.
- [ ] Upload `Test_Invoice_Item1_Item2.pdf` (project root) → expect 2 line items (GTIN `00300036120018`/Batch `2120209`/Qty `12`, GTIN `03664798023251`/Batch `41016`/Qty `20`), item names shown as "Item N (description not printed on label)" since this fixture never prints a real product description. This file has a different table layout than Sample Invoice.pdf — it's parsed by a second regex pattern targeting its "Annex" summary lines, not the primary layout.
- [ ] Go back, try uploading a random unrelated image/PDF — expect a clear error (422-style message) with a snippet of what OCR actually read, plus a suggestion to browse the SAP list instead, or to enable `EXTRACTION_MODE=live` for AI-vision extraction. **Should not silently show fabricated data.**
- [ ] (Optional, needs your own `ANTHROPIC_API_KEY`) Set `EXTRACTION_MODE=live` and restart the backend, then upload an invoice neither regex pattern covers — expect it to be read via a live Claude vision call instead of a 422, and the invoice's supplier field to say "extracted via live AI vision."

### 3c. Full real match walkthrough (recommended path)
- [ ] Upload `Real_Test_Invoice_Item1.pdf` → expect one line item, GTIN `00300036120018`, Batch `2120209`, Qty `12`.
- [ ] Scan `Picture1.png` in the scanner frame → click **Scan Photo**.
- [ ] Expect: **12 of 12** barcodes decoded (not 10 — that was a fixed bug), Quantity row shows ✓ Matched.
- [ ] Expect the **Expiry Date** row to show a mismatch/warning — the real decoded expiry (`2026-06-30`) is genuinely in the past relative to today. This is the expiry rule working correctly, not a bug.
- [ ] Since Expiry fails, a **Discrepancies Found** table should appear (Field / Expected / Detected / Reason / Recommended Action) with an expiry row.
- [ ] Type a reason in the note field → click **Review & Resolve — Accept**. Expect the discrepancy panel to collapse into a "Reviewer decision: accepted" note showing your text.
- [ ] **Validate with Tatmeen →** button should now appear (only after match-or-resolved). Click it → animated "Checking…" → **"Reported on Tatmeen — Validated."**
- [ ] Scroll down — **Final Summary** should show 4 sections (Invoice/Physical Scan/Matching/Tatmeen) with real counts, and a top verdict banner (should read "Validation Completed with Exceptions" given the accepted expiry override, not a plain "Successful").
- [ ] **Reload the page.** Expect everything above to still be there — no data loss.

### 3d. Real mismatch walkthrough
- [ ] Upload `Sample Invoice.pdf`, then scan `Picture1.png` against it.
- [ ] Expect: **zero matched results**, an **"Unexpected items found in photo"** alert listing the 12 decoded serials — because Sample Invoice's GTINs don't include Item 1's. A real, honest mismatch, not an error.

---

## 4. SAP-sourced flow (the 7 client demo flows + 1 bonus)

Open each from the "Invoices from SAP" table. Steps: **Load Invoice Data → Continue to Scan → pick a seed per item → Scan Photo → View Summary.**

| Invoice | Seed picks (per item) | Expect |
|---|---|---|
| **INV001** (Flow 1) | Item1→`item1_clean`, Item2→`item2_reported` | All green, Summary = "Validation Successful" |
| **INV002** (Flow 2) | Item1→`item1_clean`, Item2→`item2_not_reported` | Item2 red ("not reported in Tatmeen"), Summary = "Human Intervention Required" |
| **INV003** (Flow 3) | the one item→`item_ocr_fallback` | 🟡 routed to manual review (68% confidence, below threshold) |
| **INV004** (Flow 4) | Item1→`item1_clean`, Item2→`item2_reported`, Item3→`item3_sscc_reported` | All green incl. SSCC row |
| **INV005** (Flow 5) | same as Flow 4, Item3→`item3_sscc_not_reported` | Item 3 SSCC red, overall red |
| **INV006** (Flow 6) | Item1→`item1_clean`, Item2→`item2_not_reported`, Item3→`nonpharma_clean` | Item2 red, Item3 green (no Tatmeen row — non-pharma), overall red |
| **INV007** (Flow 7) | Item1→`nonpharma_b1_match`, Item2→`nonpharma_b2_short` | Item1 green, Item2 red ("short by 5"), no Tatmeen anywhere |
| **INV008** (bonus) | the one item→`item1_clean` | 🟡 Pending — Tatmeen shows activity but hasn't confirmed; proves Pending is reachable, not just red |

Also try, on any single item:
- [ ] Seed `blurry_scan` → immediate red, "Image not clear enough… retake the photo," no other rules run.

**For every row above**, also check:
- [ ] The field-by-field compare table shows real rows (GTIN/Batch/Quantity/Expiry, SSCC where applicable) — not just a flat pass/fail.
- [ ] Reopen the invoice from History after scanning — results should still be there.

---

## 5. History

- [ ] Lists every invoice you've touched (SAP + uploaded), status column shows **label text next to the dot**, not just a bare color.
- [ ] Search box filters by invoice number.
- [ ] Filter chips (Validated/Pending/Exceptions/Not scanned) work.
- [ ] Clicking "Open →" on any row goes to that invoice's wizard with results intact.

---

## 6. SSCC Proof

- [ ] Runs automatically on page load, no button.
- [ ] Expect two red findings: a foreign serial found in Item 1's real case, and a unit shown missing (simulated mispack) — both computed against real Item 1 data, calling the actual shipped rule code.

---

## 7. Cross-cutting checks (things that were bugs before — re-verify they stay fixed)

- [ ] **No data loss on navigation.** Scan an item, navigate to Dashboard, come back — results still there.
- [ ] **Multi-item single photo.** On a 3-item SAP flow (INV004/005/006), confirm one "Scan Photo" click covers all 3 items at once — not one upload per item.
- [ ] **Tatmeen only appears after match/resolve**, never before — confirms the gating logic.
- [ ] **Discrepancy resolution persists a real reason** — check the note you typed shows up after resolving, and survives a page reload.
- [ ] **Pharma vs non-pharma branching** — non-pharma items (Flow 6 Item 3, Flow 7) never show a Tatmeen row at all, just quantity.

---

## Known, expected limitations (not bugs — don't report these)

- Invoice OCR is tuned to Sample Invoice.pdf's layout; a very different invoice format will fail to parse with a clear error.
- Real barcode decode isn't always 100% on the first try depending on photo quality — that's realistic, not scripted.
- No real camera access (desktop POC) — the scanner frame's capture mechanism is file upload.
- Flow 3 (OCR-fallback) content is a proposed scenario, not client-confirmed.
- Login is a dummy, frontend-only gate — no real backend authentication.
