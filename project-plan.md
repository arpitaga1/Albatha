# Project Plan — Pharma & Non-Pharma Shipment Validation POC

Status: **Draft for validation — not yet built.** Companion to `Claude.md`
(validation-rule logic and R&D findings) and the client's `Pharma & Non-Pharma
Shipment Validation POC – Updated Requirements & Demo Flows.md`. This file
covers everything Claude.md doesn't: tech stack, personas, data model,
phasing, and delivery scope.

---

## 1. Objective

Demonstrate — for the Albatha/MPC RFP evaluation — that shipments can be
validated automatically across three independent sources: what the **invoice**
expects, what a **photo scan** physically finds, and (for pharma items only)
what **Tatmeen** confirms is reported. Prove this with the client's 7 demo
flows, running against realistic (not production) data.

This is a **proof of concept for a client presentation**, not the production
system described in the RFP. Scope is deliberately narrow — see §3.

---

## 2. User roles / personas

| Persona | What they do in the POC | Primary screens |
|---|---|---|
| **Warehouse Operator** | Uploads/scans item and carton photos; sees per-item validation status as it happens; responds to "photo not clear, please retake" prompts. | Scan/upload screen, live item status |
| **Invoice Coordinator** | Uploads the (ERP-generated, simulated here) invoice; confirms the extracted line items look right before validation starts. | Invoice upload & review screen |
| **Compliance / QA Reviewer** | Works the "Manual Intervention Required" queue — unreported Tatmeen items, SSCC issues, quantity mismatches — and records a resolution. | Exception queue |
| **Ops Manager (demo audience)** | Views the consolidated shipment dashboard, overall 🟢/🟡/🔴 status, drills into any flagged item. This is the persona the client demo is really staged for. | Shipment dashboard (client doc §14) |
| **Demo Administrator** *(internal, not a real end-user role)* | Seeds/edits the Tatmeen dummy dataset and the 7 demo-flow sample invoices before a presentation. | Admin/seed screen or scripts |

---

## 3. Scope

### In scope (this POC)
- The 7 client demo flows (Flow 3 pending confirmation — see Claude.md open
  questions).
- Image upload → SOP-based extraction (grid detection, per-cell crop,
  DataMatrix/OCR read, image-quality gate).
- Invoice upload → line-item extraction (GTIN, batch, expiry, qty, invoice
  number).
- Tatmeen validation against a **simulated dummy database**, not a real
  integration.
- All 19 validation rules from Claude.md.
- Consolidated dashboard matching the client doc's §14 mockup.
- Sample data: 7 invoices (one per demo flow) with proper `INV0xx` numbers,
  matching dummy Tatmeen records.

### Explicitly out of scope (belongs to the full RFP, not this POC)
- Real SAP ERP integration (RFP §5.4) — invoices are uploaded files here, not
  a live SAP Outbound Invoice Object feed.
- Real Tatmeen/Oridx integration (RFP §5.4) — dummy database only.
- Hardware procurement (scanners, industrial cameras — RFP §5.11).
- Security/compliance hardening (MFA, PAM, SIEM, ISO 27001, VAPT — RFP §5.9)
  — not meaningful for a local demo POC.
- Multi-warehouse rollout (RFP names 4 warehouses; POC runs as one
  environment).
- Application Managed Services / Hypercare (RFP §5.8, §5.10) — post-award
  concerns, not POC concerns.

This split should be stated explicitly to the client so the POC isn't
mistaken for a production-ready slice — it's a capability demonstration.

---

## 4. Tech stack

Constraint carried from your instruction: **no paid databases or paid
services** — everything below is free/local, suitable for a POC that just
needs to run and be demoed.

| Layer | Choice | Why |
|---|---|---|
| Frontend | **React + Vite (TypeScript)** | Fast to build a small dashboard/upload UI; free; no build-server cost. |
| Backend | **Python + FastAPI** | This session already has a proven, working Python toolchain from R&D (OpenCV for image cropping/grid analysis, reportlab for PDF generation) — reusing it avoids re-deriving what's already tested. FastAPI is lightweight and free. |
| Database | **SQLite** | File-based, zero-config, genuinely free — holds the Tatmeen dummy dataset, parsed invoices, scan sessions (for cumulative partial-scan tracking), and the validation-result log. No server, no hosting cost. |
| Image processing | **OpenCV + Pillow** | Already proven this session for per-cell cropping, zoom, and grid-structure detection (the SOP's Steps 3–4). |
| AI extraction (OCR / label reading) | **Claude API (vision)** | This is the mechanism validated across all 15 R&D rounds — reading GTIN/Batch/Serial/Expiry off real photographed labels, running the image-quality gate, doing grid/count analysis. Recommend continuing with it here. **Flagging a nuance**: this does carry a small per-call API cost — different in kind from "paid infrastructure" (a hosted DB, a SaaS OCR subscription), but still a real cost during the demo. Worth an explicit yes from you, since "no paid services" was stated for infra/hosting. |
| Barcode / DataMatrix decode | **Not resolved yet — real risk, see §8** | Round 5 found `pyzbar`/`pylibdmtx` fail to load on this Windows/Python 3.14 setup (missing native DLL dependency). Recommend either running the backend on Linux/WSL/Docker (these wheels are far more reliable there) or leaning primarily on Claude vision for extraction with native decode as an optional enhancement, not a hard dependency. |
| PDF generation (sample invoices) | **reportlab** | Already proven this session (`Test_Invoice_Item1_Item2.pdf`). |
| Hosting | **Local/dev machine for the demo** | No hosting infrastructure needed for a POC walkthrough — zero cost. |

---

## 5. Data model (sketch, not final schema)

- **Invoice**: `invoice_number`, `sold_to`, `ship_to`, `date`, `line_items[]`
- **InvoiceLineItem**: `gtin`, `description`, `batch`, `expiry`, `qty`, `uom`, `category` (pharma / non-pharma)
- **ScanRecord**: `image_ref`, `extracted_gtin`, `batch`, `serial`, `case_sscc`, `mfg_date`, `exp_date`, `confidence`, `timestamp`
- **TatmeenRecord** *(dummy)*: `gtin`, `batch`, `serial`, `invoice_number`, `reported` (bool), `reported_qty`, `sscc`, `sscc_reported` (bool), `reporting_date`
- **SSCC**: `sscc_code`, `parent_sscc` (nullable — for master/child hierarchy), `reported` (bool), `item_qty`
- **ValidationResult**: `item_ref`, `invoice_match_status`, `tatmeen_status`, `quantity_status`, `sscc_status`, `overall_status` (🟢/🟡/🔴), `notes`
- **ScanSession**: `invoice_number`, `batch`, `cumulative_qty`, `session_history[]` — supports rule 19 (partial/cumulative scanning)

---

## 6. Validation rules

All 19 rules live in `Claude.md` under "Full Validation Rule Set" — not
duplicated here to avoid drift. Summary: rules 1–5 already have a working
reference implementation and passed real tests against Item 1's data; rules
6–19 are fully designed and committed, not yet built.

---

## 7. The 7 demo flows

Recorded in full in `Claude.md`. Quick reference:

| Flow | Scenario | Expected result |
|---|---|---|
| 1 | All pharma items reported | 🟢 Validated |
| 2 | One pharma item not reported | 🔴 Manual Intervention |
| 3 | **Reserved — proposed: OCR-fallback path (unconfirmed, needs client sign-off)** | TBD |
| 4 | SSCC reported | 🟢 Validated |
| 5 | SSCC not reported | 🔴 Manual Intervention |
| 6 | Mixed pharma (reported + not) + non-pharma | 🔴 Exception |
| 7 | Non-pharma only, quantity-based | 🟢/🔴 depending on quantity |

---

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Native DataMatrix decode doesn't work on Windows/Python 3.14 (Round 5 finding) | Extraction step may need to lean on Claude vision only, or backend needs to run on Linux/WSL | Test `zxing-cpp` early in Phase 1; fall back to vision-only extraction if native decode remains blocked |
| Dense/angled carton photos are genuinely hard to count accurately (Round 11 finding: 44 vs actual 60) | Demo counts could be wrong if photos aren't good | SOP's per-cell + cross-check method is already proven — bake it into Phase 1, don't skip it for demo speed |
| 10 open business-rule questions from the client (Claude.md) are still unanswered | Building the wrong behavior for exact-match vs. threshold logic, shipment-level fail rules, etc. | Get these answered before Phase 2 (Tatmeen logic) starts — they directly affect what gets built |
| Claude API usage has a real (if small) per-call cost during extraction | Runs against the spirit of "no paid services" even though it's not infrastructure | Flagged above — needs an explicit yes/no from you before Phase 1 |

---

## 9. Branding

Color theme and logo to be sourced from the RFP document and/or the
Albatha/MPC public website, applied during Phase 4 (Dashboard & Polish). Not
actioned yet — noted here so it's not forgotten, per your instruction.

---

## 10. Phased build plan (effort estimates, not calendar dates — pending team size confirmation)

| Phase | Scope | Est. effort |
|---|---|---|
| **0 — Setup & test data** | Scaffold frontend/backend, SQLite schema, seed Tatmeen dummy dataset (client's example table), regenerate the 7 demo-flow sample invoices with proper `INV0xx` numbers | 1–2 days |
| **1 — Core invoice + scan + match** | Rules 1–5 (already validated in R&D): invoice upload/parse, image upload with full SOP extraction, identity-matching hierarchy, duplicate check, image-quality gate, case-containment check | 3–4 days |
| **2 — Tatmeen + pharma/non-pharma branching** | Rules 14–16 + rules 6–13: Tatmeen dummy DB + reported/quantity checks, category routing, GTIN checksum, date sanity, signed variance, UOM check, expiry flag | 3–4 days |
| **3 — SSCC hierarchy + pending + cumulative scanning** | Rules 17–19: master/child SSCC validation, time-window pending logic, multi-session scan tracking | 3–4 days |
| **4 — Dashboard, 7 flows, branding** | Consolidated dashboard (client §14 mockup), wire up all 7 flows end-to-end, apply branding, cross-photo duplicate detection, confidence-weighted review, many-to-many matching | 3–4 days |
| **5 — Rehearsal & polish** | Run all 7 flows live, fix rough edges, prep talking points tied back to RFP requirements | 1–2 days |

**Total: roughly 14–20 working days (~3–4 weeks)** for a small team (1–2
developers) — a rough estimate to validate against your actual team capacity,
not a committed schedule.

---

## 11. Deliverables

- Working POC application (frontend + backend + SQLite), runnable locally.
- Seed data: Tatmeen dummy dataset + 7 numbered sample invoices.
- All 19 validation rules implemented and demonstrable.
- Dashboard matching the client's §14 mockup.
- Demo script covering all 7 flows (with Flow 3 finalized once confirmed).

---

## 12. Open items blocking full confidence in this plan

Same 10 questions listed in `Claude.md`'s "Open questions" section, carried
here for visibility since they affect Phases 2–3 directly — recommend getting
answers before those phases start, not mid-build.
