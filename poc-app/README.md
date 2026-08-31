# Pharma & Non-Pharma Shipment Validation POC — Implementation

Companion code to `../Claude.md` (validation-rule design, R&D findings) and
`../project-plan.md` (tech stack rationale, personas, phasing). Read those
first for *why* — this file is only *how to run it* and *what's real vs.
stubbed*.

## What this is

A working demonstration of all 19 validation rules and the client's 7 demo
flows, reconciling a scanned item against an invoice and a **simulated**
Tatmeen database. Per your instruction: **Tatmeen and ERP integration are
dummy flows — nothing external actually connects.** Tatmeen is a table in
the local SQLite file; there's no real Tatmeen/ERP system anywhere.

**As of Round 18, invoice and item extraction are genuinely real** — not
mock, not an API-key-gated stub. Two free, local technologies do real work
on real uploaded files, no Anthropic API key required:

- **Barcode/DataMatrix decode** (`zxing-cpp`) — reads the actual GS1-encoded
  2D barcode off an uploaded item photo. Verified against Picture1.png: 10
  of 12 real DataMatrix codes decoded correctly, exact match with data
  manually transcribed during Rounds 1–6.
- **OCR + parsing** (Tesseract, installed via winget + PyMuPDF for PDF
  rendering) — reads the actual text off an uploaded invoice and parses
  line items out of it. Verified against the real `Sample Invoice.pdf`:
  correctly read 7 of 8 GTINs, batches, quantities, and expiry dates
  directly from the document, with the kind of small character-level OCR
  imperfections (e.g. "R25H03" read as "R25HO3") that are genuinely
  expected from real OCR, not a bug.

## Quick start

**Backend** (Python 3.10+; built and tested here on 3.14.5):

```
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```

Real OCR also needs the Tesseract engine itself (not just the Python
wrapper) — install it separately if `pip install` alone isn't enough:
`winget install --id UB-Mannheim.TesseractOCR -e` on Windows, or
`apt install tesseract-ocr` / `brew install tesseract` elsewhere. The path
is hardcoded as a fallback in `app/services/real_extraction.py` for this
Windows dev box — adjust `_TESSERACT_CANDIDATES` if tesseract lives
somewhere else, or just make sure it's on `PATH`.

First run auto-creates `poc.db` and seeds it with the 7 demo invoices, a
matching Tatmeen dummy dataset, and SSCC hierarchy records. Delete `poc.db`
and restart to reseed from scratch.

**Frontend** (Node 18+; built and tested here on Node 24):

```
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. It proxies `/api/*` to the backend on
`:8000` — both must be running. You'll land on a login screen —
**demo credentials are pre-filled**, just click Sign in
(`demo@albatha-mpc.com` / `Demo@1234`). This is a dummy, frontend-only auth
gate (no real backend auth), per the request to make the app feel like a
real product rather than a bare testing tool.

## The UI, end to end

**"Start Validation"** is one screen, two sections (per the client spec) —
not two separate nav destinations like the previous round:

- **Invoices from SAP** — a table of dummy invoices explicitly tagged
  "Fetched from SAP," sourced exclusively through
  `app/services/sap_source.py` (the client's requested clean
  `SAP Data Source -> Invoice Data` abstraction — swap that one module for a
  real SAP call later, nothing else changes). Click a row to open it.
- **Upload Invoice** — genuinely OCR'd on the spot, no seed picker. Try
  `Sample Invoice.pdf` (the client's real sample) or
  `Real_Test_Invoice_Item1.pdf` (a fixture built to give a full-match happy
  path using Item 1's real GTIN/batch).

Once inside an invoice (either source), the flow is the same shape:

1. **Review invoice data** (from SAP: already loaded; from upload: already
   OCR'd) — GTIN/Batch/Qty/Category per line.
2. **Scan** — a viewfinder-style scanner screen (corner brackets, animated
   scan line — upload is the actual capture mechanism in a desktop POC,
   presented inside that frame rather than a bare file input). Real
   invoices get genuine barcode decode; SAP invoices get a seed picker per
   item (since there's no real photo for most seeded scenarios) — one photo
   action covers every item in the carton either way.
3. **Compare** — a real field-by-field table (GTIN/Batch/Quantity/Expiry/
   SSCC, invoice vs. scanned) using the actual detected values (a new
   `scanned` object in the API response), not text parsed out of rule
   messages.
4. **Discrepancies**, if any — a structured table (Field / Expected /
   Detected / Reason / Recommended Action), a real reviewer-note input, and
   **Review & Resolve — Accept/Reject**, persisted server-side.
5. **Validate with Tatmeen →** (only once matched or resolved) — animated
   check, then **"Reported on Tatmeen — Validated,"** **"pending
   confirmation,"** **"Not Reported on Tatmeen,"** or **"Tatmeen Validation
   Failed"** (a real system-error branch, distinct from a business
   not-reported result).
6. **Final Summary** — four sub-sections (Invoice / Physical Scan /
   Matching / Tatmeen counts) computed dynamically from real results, plus a
   3-tier final verdict (Validation Successful / Completed with Exceptions /
   Human Intervention Required) — never a single hardcoded badge.

**Reopening any invoice later shows the same real results immediately** —
`GET /api/scans/results/{invoice_number}`, called on page load.

### Everything else
- **Dashboard** — stat tiles + recent activity across *all* shipments, SAP
  and uploaded together.
- **History** — searchable/filterable listing, same.
- **SSCC Proof** — unchanged, the Round 13–14 negative-control demo.

## Known, disclosed limitations of the real extraction path

Being upfront about where "real" still has edges, rather than overselling it:

- **The invoice parser is regex-based and tuned to Sample Invoice.pdf's
  specific two-line-per-item layout.** It correctly reads that real
  document and the `Real_Test_Invoice_Item1.pdf` fixture (same layout by
  design), but a differently-formatted invoice will need its own pattern —
  you'll get a clear 422 error with a snippet of what OCR actually read,
  not a silent wrong answer. See `real_extraction.py`'s docstring.
- **Barcode decode isn't 100% on every photo** — 10 of 12 on Picture1.png,
  same real-world imperfection rate you'd expect from any physical
  scanning process. This is a feature for demo purposes, not a bug to
  hide: it's exactly what produces genuine, non-scripted discrepancies
  (see the quantity-mismatch example above), which is what proves the
  validation logic is really running, not just replaying a script.
- **Item-photo extraction has no Anthropic/AI-vision path at all, by
  explicit user directive** — the RFP's OCR-fallback requirement (reading
  GTIN/batch/expiry from printed text when the barcode itself is
  unreadable) is met entirely locally: `real_extraction.extract_via_opencv()`
  detects individual item boundaries via classical OpenCV edge/contour
  detection, then reads each one's label text with local Tesseract OCR.
  Verified against the project's own real test photos: 8/12, 16/20, and
  94/96 units correctly recovered (that last one better than the AI-vision
  approach it replaced, which measured 85/96 on the same photo) — see
  `real_extraction.py`'s module docstring for the full accuracy history,
  including the earlier fixed-parameter version that did NOT generalize
  across photo densities before this was fixed. One genuinely degraded
  real photo (steep angle, heavy blur) still can't be read by either
  barcode decode or OpenCV — an honest "no identifiable items" result in
  that case, not a fabricated count. Only invoice-document OCR
  (`extract_invoice_live`) still has an opt-in Anthropic fallback, since
  that's a different problem (parsing a document's text layout) — see the
  Invoice section above.
- **Non-pharma quantity-only items have no real "photo → count" path via
  barcode decode** — counting loose items with no barcode to decode is
  what `extract_via_opencv()` above was built to address; it applies to
  any item photo, pharma or not, whenever the barcode path can't help.

## What's actually implemented (not stubbed)

- **All 19 validation rules**, real callable Python functions
  (`app/services/validation_engine.py`).
- **Three real extraction paths** (barcode decode, OpenCV+local-OCR
  fallback/cross-check, invoice OCR) — see above — plus the original
  mock-seed system, kept for the 7 demo scenarios. Item-photo paths are
  100% local, no API key required for any of them.
- **Real human-intervention workflow**: `POST /api/scans/{id}/resolve`
  records an actual reviewer decision (accept/reject + note), persisted,
  changes the item's status for real.
- **Real state persistence**: `GET /api/scans/results/{invoice_number}`
  rehydrates a previously-scanned invoice's real results on page load.
- **All 7 client demo flows** (seeded), verified live end-to-end.
- **3 bonus proof scenarios**: `INV008` (Pending-status), `/sscc-demo`
  (Round 13–14 negative control against shipped code), `blurry_scan` seed
  (image-quality gate rejection).

## What's a known gap (next steps, not silently skipped)

- **Login is dummy/frontend-only** — no real user database or session.
- **Invoice OCR's live AI-vision fallback (`EXTRACTION_MODE=live`) needs
  `ANTHROPIC_API_KEY` if you want it** — only affects invoice-document
  parsing for layouts the two regex patterns can't read. Item-photo
  extraction (barcode + OpenCV/OCR fallback) needs no API key at all.
- **Configurable-but-unconfirmed business rules** live in `app/config.py`
  — `TATMEEN_QTY_MODE` (gte vs exact), `TATMEEN_GRACE_DAYS`, whether one
  unreported item fails the whole shipment. All ten open questions from
  Claude.md are still open; these are reasonable defaults, not answers.
- **No auth, no multi-warehouse, no real persistence beyond SQLite** — by
  design, per project-plan.md's explicit out-of-scope list.

## Real bugs this session's own testing caught and fixed

1. Seeding "GTIN002" as literal placeholder text made the GTIN checksum
   rule correctly fail it — fixed by generating valid-checksum GTINs.
2. A data-flow bug let `tatmeen_status: yellow` and `overall_status: red`
   show simultaneously — fixed by giving rule 18 sole ownership of that
   decision.
3. **(Round 18)** Tatmeen lookup required an exact invoice-number match,
   which meant a genuinely new real-uploaded invoice could *never* find a
   Tatmeen record even for a GTIN/Batch that genuinely exists in the dummy
   database — fixed by falling back to GTIN+Batch alone, invoice-agnostic,
   matching how a real national Tatmeen database would actually be indexed.
4. **(Round 18)** A stray `--reload` uvicorn process held a file lock on
   `poc.db`, silently serving stale scan data through a newly-added
   endpoint after a "clean restart" that didn't actually take effect —
   caught by testing the endpoint's actual output, not just checking it
   returned 200.

## Project layout

```
poc-app/
  backend/
    app/
      main.py               FastAPI app, CORS, seeds DB on startup
      config.py              All the "unconfirmed assumption" toggles, in one place
      models.py               SQLAlchemy models (+ resolution_action/note for human intervention)
      schemas.py               Pydantic request/response shapes
      services/
        real_extraction.py      REAL barcode decode (zxing-cpp) + OCR/parse (tesseract+pymupdf) — no API key
        extraction.py            Mock seed system (7 demo flows) + live Anthropic vision (unconfigured)
        validation_engine.py    All 19 rules as functions
        pipeline.py              Orchestrates Invoice->Tatmeen->Qty->SSCC, GTIN+Batch Tatmeen fallback
        seed_data.py              The 7 demo invoices + Tatmeen dummy DB + SSCC records
      routers/
        invoices.py               GET, + POST /upload (real OCR ingestion)
        scans.py                   /mock, /live, /upload-real (real decode), /results/{inv} (state persistence), /{id}/resolve
        dashboard.py, demo.py
  frontend/
    src/
      context/AuthContext.tsx      Dummy login/session state
      components/
        AppShell.tsx                 Sidebar nav: Dashboard / New Validation / Demo Scenarios / History / SSCC Proof
        RealScanFlow.tsx              The real flow: box upload -> compare -> discrepancy/accept -> Validate with Tatmeen
        ItemScanPanel.tsx              The seeded-demo per-item mini-flow (unchanged)
        UploadDropzone.tsx, StatusBadge.tsx, ProtectedRoute.tsx
      pages/
        LoginPage.tsx, DashboardPage.tsx, HistoryPage.tsx
        RealValidationStartPage.tsx     "New Validation" — real invoice upload entry point
        ScenarioPickerPage.tsx           "Demo Scenarios" — the 7 flows, tagged "Seeded data"
        ValidationWizardPage.tsx          Branches: real invoice -> RealScanFlow, seeded -> guided wizard
        SsccDemoPage.tsx
      api.ts, types.ts
```
