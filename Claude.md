# POC: Pharma & Non-Pharma Shipment Validation (Image ↔ Invoice ↔ Tatmeen)

## Status: R&D / manual testing phase — nothing built yet.
This file is the running context for the idea below. It gets updated as we test
manually in conversation. When the user says "build the POC", use this file
plus `project-plan.md` as the spec to scaffold the real application quickly.

**Governing spec:** `Pharma & Non-Pharma Shipment Validation POC – Updated
Requirements & Demo Flows.md` (client-provided, Round 15) is now the primary
source of truth for scope and the 7 demo flows. This file (Claude.md) is where
that spec gets reconciled with everything actually tested in Rounds 1–14, plus
the RFP and sample invoice data. Where the two disagree, the resolution is
recorded inline below with the round it was resolved in.

## The idea (updated Round 15 — now a 3-way check, not 2-way)
1. User provides a photo/image containing multiple physical items (e.g. boxes,
   products, parts laid out together).
2. AI (vision) analyzes the image to:
   - Identify each distinct item / item type present
   - Count the quantity of each item
   - Read any visible identifying details on the items themselves (GTIN,
     batch, serial numbers, expiry, case/SSCC code) if legible in the image
3. User provides invoice data for the same shipment (ERP-generated in
   production; PDF/Markdown test files here), with line items carrying GTIN,
   batch, quantity, and an **Invoice Number** (required — see Round 15).
4. **For pharma items** (has a 2D barcode): also cross-check against
   **Tatmeen** — a dummy/simulated database for this POC (see below) — for
   reported-status and reported-quantity. Non-pharma items skip this step
   entirely and are validated on quantity alone.
5. Compare image data, invoice data, and (for pharma) Tatmeen data. Report
   discrepancies per serial number / batch / SSCC: what the difference is,
   which field it's in, and which of the three sources disagree — not just
   "image vs invoice" anymore, any pair (or all three) can disagree
   independently.

## Current phase
We are testing this manually, one round at a time, directly in a Claude
conversation:
- User pastes/attaches an image → Claude (vision) extracts item list + counts
  (+ any readable serials/labels).
- User pastes/attaches invoice data → Claude extracts line items (serial,
  description, qty).
- Claude compares the two and reports mismatches by serial number.
- No code, scripts, or app are being built yet — this is purely to validate
  accuracy/feasibility of the approach before investing in a real POC.

## Tatmeen integration & the 3-way validation model (added Round 15)
The client's updated requirements doc adds a third independent data source
beyond image and invoice: **Tatmeen** (confirmed spelling — user directive,
Round 15; the requirements doc spells it "Tatmin," treat that as the same
system). This is the single biggest structural addition on top of everything
tested in Rounds 1–14, which was purely image-vs-invoice.

**Why it matters:** invoice and physical scan can agree perfectly and the
shipment can still fail — e.g. invoice says 10,000, scan says 10,000, but
Tatmeen only has 9,500 reported. Any one of the three can disagree with
either of the other two, independently. Every quantity/identity rule in this
file needs a Tatmeen-aware variant for pharma items, not just an image↔invoice
one.

**For this POC, Tatmeen is a simulated dummy database, not a real
integration** — consistent with "no paid services" for a POC (a local SQLite
file or JSON store is enough; the RFP's real Oridx/Tatmeen integration is
explicitly out of scope here). Dummy record shape (per client doc §8):
GTIN, Batch, Serial, Invoice Number, Reported (Y/N), Reported Quantity, SSCC,
SSCC Reported (Y/N), Reporting Date.

**Tatmeen validation logic (per client doc §9), for pharma items only:**
1. Find the item in Tatmeen by GTIN + Batch + Serial (+ Invoice Number where
   applicable).
2. Reported? No → exception. Yes → continue.
3. Compare Tatmeen's reported quantity against the invoice's expected
   quantity.
4. Status: 🟢 Matched / 🟡 Pending (not yet reported, but still inside the
   agreed reporting grace window — **assumed 1–2 days, unconfirmed, see open
   questions**) / 🔴 Failed (not reported after the grace window, or reported
   quantity doesn't satisfy the invoice).

**🟡 Pending is a genuinely new status** — Rounds 1–14 only ever produced
pass/fail. This needs real time-window logic (a reporting timestamp vs. a
configurable grace period), not just a boolean check.

## Pharma vs. Non-Pharma categorization (added Round 15)
- **Pharma**: has a 2D barcode (DataMatrix, per Round 5). Gets the full
  identity hierarchy (GTIN → Serial, see below) + Tatmeen validation.
  Note: our own Item 3 test data (`MF1204`, Pictures 3–6) is a live example
  of a pharma item with **no GTIN field printed at all** — only batch + Mfg/
  Exp + serial + DataMatrix — so "pharma" classification depends on the 2D
  barcode being present, not on GTIN specifically being one of its fields.
- **Non-pharma**: no 2D barcode. Validated on **quantity only** (invoice qty
  vs. scanned/received qty) — no Tatmeen check at all in this POC's scope.

## Identity-matching hierarchy — resolved (Round 15)
User-confirmed resolution of the ambiguity flagged after Round 9: **primary
match key is GTIN; if GTIN is not available, fall back to Serial Number.**
Client has committed that **all invoices will carry GTIN going forward** —
so this fallback is mainly a transitional/demo-data case, not a permanent
architecture requirement.

This sits alongside, and doesn't overrule, the separately-validated
extraction-side fallback from Round 9 (GTIN → Batch Code → Case code, used
when reading a physical label that has no GTIN printed on it at all, like
Item 3/`MF1204`) — that's about what to read off an item with no GTIN field;
this new rule is specifically about what to key the **invoice match** on when
GTIN isn't present on one side. Residual open question: this fallback only
works if the invoice actually lists serial numbers per line — Sample
Invoice.pdf's real data (Round 1) had a **blank Serial Number column** on
every line, so until confirmed otherwise, assume real ERP invoices may need
the same caveat.

## Sample invoices must carry an Invoice Number (added Round 15)
Client requirement: every sample/test invoice needs a proper Invoice Number
field (matching the Tatmeen dummy DB's `INV001`-style references, and the
7 demo flows' "Invoice 1..7" naming). `Test_Invoice_Item1_Item2.pdf`
currently uses a placeholder ("TEST-INV-001") — needs realigning to the
`INV0xx` convention when the demo-flow invoices are built. Not yet
regenerated as of Round 15 — queued as a build task in `project-plan.md`.

## Seven client demo flows (from the requirements doc, Flow 3 resolved)
1. **All pharma reported** → 🟢 Validated.
2. **One pharma item not reported** → 🔴 Manual Intervention (or full
   shipment exception, per open question #3 below).
3. **Reserved — was undefined in the client doc.** Proposed resolution
   (Round 15, not yet client-confirmed): demonstrate the **OCR-fallback
   path** — a damaged/unreadable DataMatrix, falling back to reading
   GTIN/Batch/Expiry from the printed label text. This is explicitly
   required by the RFP (§5.3) but wasn't represented in any of flows 1–7 as
   given, and it's exactly what Rounds 1–5 spent real effort validating
   (DataMatrix decode failing → reading the printed HRI text instead). Flag
   this to the client for sign-off before building it as Flow 3.
4. **SSCC reported** → 🟢 Validated (SSCC quantity matches expected).
5. **SSCC not reported** → 🔴 Manual Intervention.
6. **Mixed pharma (reported + not-reported) + non-pharma** → 🔴 Exception
   (demonstrates category-dependent validation rules in one shipment).
7. **Non-pharma only** → 🟢/🔴 purely on quantity match, no Tatmeen check.

## Open questions — still need client confirmation (carried from their §15)
Not resolved by us; listed here so they don't get silently assumed away:
1. Tatmeen quantity: exact match required, or is ≥ invoice quantity enough?
2. Exact Tatmeen match key combination — GTIN+Batch+Serial+Invoice Number,
   or fewer fields?
3. Does one unreported pharma item fail the *entire* shipment, or just that
   line?
4. Does an unreported SSCC fail the entire shipment?
5. Exact Tatmeen reporting grace window (currently just assumed 1–2 days).
6. Exact rules for partial/repeated scans (see cumulative-scan rule below).
7. Is SSCC generated by this POC, or received from another system?
8. Exact quantity-validation rules for non-pharma items (tolerance? exact?).
9. What happens when invoice qty, physical qty, and Tatmeen qty are all
   three different from each other?
10. Client sign-off on Flow 3's proposed content (OCR-fallback, above).

## Standard Image Analysis Process (SOP) — this IS the POC's core algorithm
Formalized in Round 12 after a real miscount (Picture5: single-pass whole-image
visual estimate said ~44 boxes; actual confirmed count was 60/12×5). Root cause:
analyzing a dense, angled photo in one holistic glance instead of a systematic
process. This SOP is meant to become the actual scanning algorithm in the real
POC (grid-detection + per-cell crop-and-decode), not just a conversational habit
— follow it for every image, every time.

**Step 1 — Ask for the known packing configuration first, when it might exist.**
Cartons/pallets usually follow a fixed, known pack spec (units per row × number
of rows, or a stated total) that the user or warehouse already knows. That is a
more reliable source of truth than visually inferring it from a photo,
especially a dense or steeply-angled one. Treat a visual count as a fallback/
cross-check, not the primary method, whenever a known spec is available or can
be asked for.

**Step 2 — Assess framing and image quality BEFORE analyzing content.**
Check all four edges of the photo for cropping (boxes cut off mid-label = the
carton extends beyond the frame — a photo problem, not a defect in the boxes).
Check for blur, steep angle, poor lighting. Apply the mandatory image-quality
gate (see below) with a concrete reupload suggestion — do this up front, not
after already producing a shaky count.

**Step 3 — Determine grid structure methodically, not by single holistic
eyeballing.** For dense grids (rough rule of thumb: more than ~20 items) or
steep camera angles, a single whole-image visual pass is unreliable (proven in
Round 11). Instead:
  - Identify row/column boundaries using visible physical cues (tape lines, box
    edges, shadows).
  - Cross-check the count using at least one independent signal beyond
    eyeballing where feasible: count of distinct DataMatrix/QR blobs (each item
    has exactly one), or count of distinct serial numbers extracted.
  - If signals disagree or confidence is low, report the count as **provisional**
    and say so explicitly — never present an estimate as a verified count.

**Step 4 — Extract data per-cell, not per-image.** Crop each identified item
individually and zoom in before reading its fields. Reading small/rotated text
off a dense whole-image render is consistently far less reliable than reading
one zoomed cell at a time (demonstrated across Rounds 1–10: every accurate read
came from a per-cell crop, every miscount/misread came from a whole-image pass).

**Step 5 — Run the standard checklist on the extracted data, every time:**
  - **Mixed-category check**: do all items share the same label template /
    identifier scheme? Flag if not (see [[feedback_image_scan_grouping]]).
  - **Identifier capture**: record whichever of GTIN / Batch-Lot Code /
    Case-SSCC-style code are present per item.
  - **Duplicate-serial integrity check**: are all serials in the group
    distinct? Does distinct-serial-count match the confirmed box count?
  - **Invoice match**, using the fallback hierarchy GTIN → Batch Code → Case
    code (see [[feedback_invoice_matching_hierarchy]]) — never conclude "no
    match" without checking all available identifier fields.

**Step 6 — Report structure, every time:**
  - Count: value + confidence level + method used + whether user-confirmed or
    visually estimated.
  - Template/category consistency result.
  - Identifiers found, per field, with confidence.
  - Duplicate-check result.
  - Invoice match result, naming the specific field(s) checked.
  - Any image-quality issues found, each with a concrete reupload/clarification
    suggestion (not just a passive confidence caveat).

## Methodology: identifier hierarchy & multi-category detection
Every image scan must check for **mixed categories/batches in one photo**, not
assume all items in a shot are one homogeneous group. Rule: don't just report a
total count — always check whether the visible boxes actually split into more
than one GTIN and/or more than one Batch/Lot before reporting a single number.

**Identifier roles (don't confuse these):**
- **GTIN** — shared across all units of the same product. Use to answer "how
  many distinct products are in this photo, and how many units of each."
- **Batch/Lot (+ Expiry as cross-check)** — shared across units from the same
  production run, but can differ *within* the same GTIN. Use to answer "these N
  units are one batch, those other N units are a different batch of the same
  product."
- **Serial Number (S/N)** — unique per individual unit. Never a grouping key —
  you don't group boxes "by" a serial number. Instead, use it as an integrity
  check *within* a GTIN/Batch group: every S/N in the group should be distinct;
  if two boxes show the same S/N, that's a red flag (duplicate/misread/
  counterfeit); and distinct-serial-count should equal the visual box count
  (catches double-counts or missed boxes).

**Two ways to split "10 boxes vs another 10 boxes" in the same photo:**
1. **Group by GTIN** (primary split) — cluster boxes by matching GTIN. Different
   GTIN clusters = different products.
2. **Group by Batch/Lot + Expiry within the same GTIN** (secondary split) — if
   two clusters share the same GTIN (same product), GTIN alone won't separate
   them; Batch/Lot (cross-checked with Expiry) is the next key that will.

**Preferred extraction method:** decode the DataMatrix code on each label rather
than OCR-ing the small text fields separately — these labels look like standard
GS1 encoding (AI 01=GTIN, AI 10=Batch/Lot, AI 17=Expiry, AI 21=Serial), so one
decode reliably yields all four fields together. OCR of the tiny rotated
text has been unreliable in testing so far (see Round 1/2 findings below). Note:
it's a GS1 **DataMatrix**, not a QR code (confirmed Round 5) — use a DataMatrix
decoder (e.g. pylibdmtx/zxing-cpp), not a QR decoder.

### Invoice-matching hierarchy — use whatever identifiers are actually present
(Corrected in Round 9 after a real misclassification: `MT1204` on Picture3/4 was
initially called "an incompatible identifier scheme" when it's actually a batch
code — GTIN being absent doesn't mean reconciliation is impossible.) Match using
the best available identifier, don't require GTIN specifically:
1. **GTIN** — primary product identifier, when printed on the label.
2. **Batch/Lot Code** — falls back to this for product+batch matching when GTIN
   is missing/unreadable (e.g. `MT1204`-style codes).
3. **SSCC / case-level code** — a larger code often printed bigger/sideways on
   the carton (e.g. Item 1's `1459466A0`) can serve as a case-level cross-check
   when present. Note: `1459466A0` is NOT a standard GS1 SSCC (those are 18
   numeric digits; this is 9 chars incl. a letter) — flag it as "functions like
   an SSCC / internal case code" rather than asserting it's a formal one.
4. **Serial Number** — always unique per individual unit (user-confirmed: every
   unit's serial differs). Never a grouping/quantity-matching key — only the
   per-unit identity once product/batch is already resolved, and a duplicate/
   integrity check.

Never conclude "no match possible" just because GTIN is absent — check batch
code and case-level codes too before reporting a real mismatch.

### Mandatory image-quality gate
Whenever blur, steep camera angle, cropping/frame cutoff, or any other issue
prevents a reliable read, give the user a **concrete, actionable reupload
suggestion** (e.g. "reupload a straight-on, well-lit, uncropped photo of the
full carton") — don't just note low confidence and move on. Every scan report
should include this when applicable.

## Open questions to resolve during testing (fill in as answered)
- What do the source images actually look like? (single item type in bulk vs
  many different item types together; items packed in boxes vs loose;
  labels/serials visible on items or not)
- Are serial numbers actually visible/legible in the image, or only on the
  invoice? If not visible on items, matching may need to fall back to
  item-type + count comparison instead of serial-level matching.
- Invoice format(s) to support: plain text, scanned image, PDF, Excel/CSV?
- What counts as a "mismatch"? (quantity only, or also description/spec
  mismatches, damaged/wrong item, missing item, extra item)
- Desired output format for the discrepancy report (table, structured JSON,
  plain-language summary)?

## Findings log (updated after each manual test round)

### Round 1 — 2026-08-17
**Inputs:** Photo of a carton with 12 small product boxes (4×3 grid), + `Sample Invoice.pdf`
(MPC Drug Store, Tax Invoice 206204777, 8 line items).

**Image observations:**
- Count of items is reliably determinable by visual layout (12 boxes, 4 rows × 3 cols).
- Each unit label has 4 printed fields: **GTIN, Lot, Exp, S/N**, plus a **QR code**,
  plus a large batch code printed sideways in big type across the carton face.
- Label text (Lot/Exp/S/N) is small and rotated 90° in a typical carton photo —
  **OCR confidence on exact digits was low**; did not want to assert exact serial
  numbers that could be misread, since a wrong digit silently breaks reconciliation.
- These look like standard **GS1 DataMatrix/QR-style pharma/cosmetics serialization
  labels** (AI 01=GTIN, AI 10=Batch/Lot, AI 17=Expiry, AI 21=Serial). Strong candidate:
  decode the QR code programmatically instead of OCR-ing the tiny printed text — much
  more reliable for the real POC.

**Invoice observations:**
- Line items carry GTIN + Description + Batch + Expiry + Qty (+ pricing, redacted in
  sample). Column header literally has a "Serial Number" column
  (`GTIN / Description / Serial Number`), **but no row in this sample has that field
  populated** — every line's serial number sub-field is blank.
- 4 of 8 lines have Qty = 12, same as the box count in the image, so which invoice
  line the photographed carton corresponds to was ambiguous without extra input
  (product confirmation from user, or reliable GTIN OCR).

**Key finding (important for POC scope):**
With an invoice like this sample, **per-unit serial-number reconciliation is not
testable** — the invoice simply doesn't carry serial numbers per line. The only
comparison this data actually supports is at **GTIN + Batch + Expiry + Quantity**
level (does the count of boxes for a given batch/GTIN match the invoice Qty for that
line), not true serial-by-serial matching. If serial-level matching is a hard
requirement for the POC, we need either (a) an invoice format that actually
populates serial numbers per unit, or (b) to treat "serial number" reconciliation
as "batch/lot number" reconciliation instead, since that's what's consistently
present on both sides.

**Open questions raised, awaiting answers:**
1. Which invoice line does the photographed carton correspond to? (or: provide a
   photo set where product identity is unambiguous)
2. Can we get a sharper, straight-on (non-rotated) photo of 1–2 individual labels to
   test whether OCR on GTIN/Lot/Exp/S/N is reliable at all, vs. needing QR decode?
3. Is the blank "Serial Number" column normal for invoices in this workflow, or does
   a fuller/unredacted version populate it? This determines whether serial-level
   matching is actually in scope for the POC, or whether batch/lot-level matching is
   the real target.

### Round 2 — 2026-08-17
**Inputs:** Photo of a second carton ("Item 2"), same `Sample Invoice.pdf` as Round 1.

**Image observations:**
- Count: **20 boxes**, 5×4 grid. Packing less uniform than Item 1 (boxes tilted at
  angles, one box partly obscured by glare/reflection but still countable).
- Same 4-field label format (GTIN/Lot/Exp/S/N) + QR + barcode, but the field
  layout/template looks different from Item 1's labels — likely a **different
  product/SKU**, not confirmed at pixel level (same OCR-confidence limitation as
  Round 1 applies here too).

**Cross-check result — mismatch found, but likely a data-completeness issue, not a
real discrepancy:**
- No invoice line has Qty = 20 (lines are 2, 1, 12, 12, 12, 10, 7, 12).
- **Root cause identified: the invoice PDF itself says `Page: 1/2`** — we only have
  page 1 of a 2-page invoice. The line item for this carton (probably Qty 20) is
  most likely on the missing page 2.

**POC design lesson (important):** the reconciliation engine must handle
**multi-page invoices** and must not report a false "mismatch" purely because a
line item lives on a page that wasn't ingested yet — it should detect "invoice
incomplete" as a distinct state from "quantity mismatch."

**Blocking questions for next round:**
1. Please provide **page 2** of the invoice to check for a Qty=20 line.
2. Confirm which product Item 2's carton is (label template differs from Item 1).

**Round 2b — re-scan applying the mixed-category methodology (same day):**
- Compared label template (field order/layout/QR position/font) across all 20
  boxes in the Item 2 photo — **all 20 use an identical template**, no box
  stands out as a different design. So: **no visual evidence of two different
  products (GTIN split) mixed in this carton.**
- Caveat that still stands: identical template only rules out a GTIN-level mix,
  not a **Batch/Lot-level mix of the same product** (e.g. 10+10 of two
  batches) — that would look visually identical and only show up in the small
  rotated Batch/Lot digits, which OCR hasn't been reliable enough to confirm
  at this photo resolution. Needs either a sharp zoomed crop of a few
  individual labels, or QR decode, to settle definitively.

### Round 3 — 2026-08-17
**Inputs:** Photo of a third carton ("Item 3"), densely packed, same `Sample
Invoice.pdf` (still only page 1/2).

**Image observations:**
- Count: **~90 boxes estimated (9 rows × 10 columns)**, counted row by row
  front-to-back. **Lower confidence than Rounds 1–2** — this photo is a
  steep top-down angle on a densely packed carton, so the back 2–3 rows are
  visually compressed/overlapping, and a manual count at this density could
  plausibly be off by a few units. Flagged as an estimate, not verified.
- Mixed-category check: all boxes use the same label template — no visual
  evidence of a second product (GTIN-level) mixed in. Same standing caveat as
  Round 2: can't rule out a same-template Batch/Lot-level mix without a
  zoomed crop or QR decode.

**Invoice cross-check:** blocked the same way as Round 2 — no page-1 line
gets close to ~90 (max Qty is 12), and page 2 is still missing.

**POC design lesson (important, new):** for dense/high-count cartons, a
photo-based manual/visual count is inherently unreliable past a certain
density (compressed rows at steep angles). The real POC should rely on
counting QR codes / detected labels programmatically rather than a visual
"eyeball" count once item counts get large — flag low-confidence counts to
the user rather than reporting them as exact.

**Blocking questions (same pattern as Round 2):**
1. Page 2 of the invoice.
2. Which product Item 3 is.
3. Ideally a straighter top-down photo (or a user-confirmed true count) to
   validate the ~90 estimate before trusting it for reconciliation.

### Round 4 — 2026-08-18
**Inputs:** `RFP_Barcode reading & Aggregation solution.pdf`, `Email_Albatha.pdf`
(appears to be a duplicate of the RFP — identical extracted content; flagged to user,
unresolved), and full-resolution reads of `Picture1.png` (=Item 1, 12 boxes) and
`Picture2.png` (=Item 2, 20 boxes) directly from disk (much clearer than the
compressed chat-uploaded versions used in Rounds 1–3).

**Business context (this is why the POC exists):** RFP is Albatha Group → seeking
an implementation partner for an AI-enabled Barcode Reading, OCR & Aggregation
solution for Modern Pharmaceuticals Company (MPC) warehouses (Sharjah, KIZAD,
Unicare Al Quoz, **MPC Drug Store Ajman** — matches Sample Invoice.pdf's ship-to),
to support **UAE Tatmeen Track & Trace** compliance. Working directory path
("Sales\Albhata MPC") plus RFP timeline (proposal due 3 Aug 2026, award 31 Aug
2026, today is between the two) suggests this POC is being built to demonstrate
capability ahead of a partner down-select/presentation, not the bid document
itself.

**This POC = the RFP's own core functional requirement, almost verbatim:**
RFP §5.3 literally says *"Verify products against warehouse transactions,
including quantity, batch, expiry, and serial number validation"* and requires
decoding GTIN/Serial/Batch/Expiry from 2D barcodes, OCR fallback when barcodes
are unreadable, validation against SAP ERP master data (in production "the
invoice" = **SAP Outbound Invoice Object**, our PDF is a stand-in), and —
importantly — **"configurable confidence thresholds for AI recognition with
manual verification... where confidence levels fall below predefined limits."**
That last point validates the approach taken in every round so far: flagging
low-confidence OCR reads instead of asserting them is literally the required
behavior, not a workaround.

**Sample Invoice.pdf vs. Picture1/Picture2 — resolved:** neither picture's GTIN
matches any Sample Invoice line item (Sample Invoice GTINs are all `3760095...`;
Picture1 is `00300036120018`, Picture2 is `03664798023251`). Sample Invoice was
only ever usable as a **format template**, never as real data for these two
items — explains why Rounds 2–3 couldn't find a matching line.

**Full-resolution re-read results:**
- **Item 1 (Picture1, 12 boxes):** GTIN `00300036120018`, Lot `2120209`,
  Exp `2026-06`. All 12 individual serials read with **high confidence** this
  time (full-res image, legible rotation) — see `Test_Invoice_Item1_Item2.md`
  for the list. This supersedes Round 1's "OCR confidence too low" caveat —
  that caveat applied to the compressed chat image, not the source file.
- **Item 2 (Picture2, 20 boxes):** GTIN `03664798023251`, Lot/Batch `41016`,
  Mfg `06/2024`, Exp `05/2026` — high confidence (repeats 20×). Individual
  serials still **not reliably legible** even at full resolution — steep
  camera angle on the source photo. Used clearly-labeled placeholders
  (`PH-ITEM2-01..20`) rather than inventing precise codes.

**Deliverable created:** `Test_Invoice_Item1_Item2.md` — same table structure as
Sample Invoice.pdf, populated with the real GTIN/Batch/Expiry/Qty for both items
plus real serials for Item 1 and placeholder serials for Item 2. Purpose: gives
us actual invoice-side data (including per-unit serials, which Sample
Invoice.pdf never had) so the reconciliation logic can actually be exercised
end-to-end, not just count-level checks like Rounds 1–3.

**Next step (per user):** start running reconciliation test cases — compare
Test_Invoice_Item1_Item2.md against Picture1/Picture2, deliberately introduce
mismatches to validate the detection logic, report problems by serial number.

### Round 5 — 2026-08-18
**Requested:** (1) convert Test_Invoice_Item1_Item2.md to an actual PDF mirroring
Sample Invoice.pdf's header/format; (2) decode the QR/2D code on Picture1 and
report its contents.

**PDF deliverable:** `Test_Invoice_Item1_Item2.pdf` created with reportlab
(installed via pip — environment had no PDF tool preinstalled: no pandoc,
wkhtmltopdf, soffice). Layout mirrors Sample Invoice.pdf: Sold-To/Ship-To/Tax
Invoice header block, Terms of payment/Transportation line, same 9-column item
table (GTIN/Description/Serial Number | SLOC | Batch/Expiry | Qty/UOM | RSP |
WSP | Dis-Val/Disc-Rate | VAT-Amt/VAT-Rate | Amt.Ex.VAT/Amt.In.VAT), page 1;
Annex A (Item 1's 12 real serials) + Annex B (Item 2's 20 placeholder serials)
on page 2. Pricing columns marked "TEST" / 0.00 rather than fabricated, matching
Sample Invoice.pdf's own redaction. Clearly banner-labeled "NOT A REAL TAX
DOCUMENT" to avoid any confusion with a real Albatha/MPC financial document.

**Correction — it's a DataMatrix, not a QR code:** zoomed inspection of the
label crop shows the classic GS1 DataMatrix finder pattern (solid L-border on
two adjacent sides, dashed on the other two), not QR's three corner squares.
Matches RFP's "2D barcode" language — DataMatrix is the GS1 standard for pharma
serialization, so production labels are likely this format too.

**Native decode attempted and failed — real tooling finding, not just a local
quirk:** tried three decoders against a full-res crop of one label's DataMatrix
(Picture1.png is only 850×704px total, so the code itself is roughly 40×40px —
already a tough source):
1. `cv2.QRCodeDetector` (OpenCV) — wrong decoder type for DataMatrix, found
   nothing, as expected.
2. `pyzbar` — installs fine, but its bundled `libzbar-64.dll` fails to load
   (`FileNotFoundError: ...could not find module...or one of its
   dependencies`) even with `os.add_dll_directory()` and explicit `winmode=0`.
3. `pylibdmtx` (correct decoder for DataMatrix) — same DLL load failure on its
   `libdmtx-64.dll`. Also needed a `distutils` shim first since Python 3.14
   removed distutils and the library (last released 2016) still imports
   `distutils.version.LooseVersion`.

Root cause suspected: both failing DLLs are MinGW-compiled native libraries;
`libdmtx-64.dll` ships with zero bundled dependency DLLs (unlike pyzbar's,
which at least ships `libiconv.dll`), meaning it's very likely missing a MinGW
runtime (libgcc/libwinpthread) that isn't present anywhere on this machine.
Checked and ruled out: VC++ redistributables (msvcp140/vcruntime140) are
present, so it's not that.

**POC design/tooling lesson (important):** don't assume `pyzbar`/`pylibdmtx`
"just work" on a fresh Windows/Python 3.14 box — they didn't here. For the real
POC, either (a) target Linux (these wheels are far more reliable there), (b)
use a decoder with a more modern/actively-maintained Windows wheel (e.g.
`zxing-cpp`, which wasn't tried yet), or (c) use a cloud/managed barcode
recognition API instead of a local native decode. Worth testing `zxing-cpp` next
round before concluding local DataMatrix decode isn't viable on this machine.

**What we know about the DataMatrix's contents anyway:** GS1 standard requires
a barcode's printed Human-Readable Interpretation (HRI) text to exactly match
what's encoded inside it — so even without a literal decode, the encoded
content can be stated with high confidence from the printed label text using
standard GS1 Application Identifiers:
`(01)00300036120018 (17)2606xx (10)2120209 (21)1037937537575` (exact expiry day
not shown on label, only month). Flagged to user as "reconstructed from HRI
text per GS1 standard," explicitly distinguished from an actual bit-level scan.

### Round 9 — 2026-08-18 (Picture3/Picture4 report + methodology correction)
**Reports run:** Picture3 (dense ~90-box carton) and Picture4 (partial/cropped
carton, same batch as Picture3 based on shared `MT1204`/`08/2024`/`07/2026`
fields) checked against Test_Invoice_Item1_Item2.pdf. Both: no invoice line
matches. Picture4 additionally flagged as **cropped by the camera frame**
(boxes cut off mid-label at the right edge, not bounded by a carton wall) — no
reliable total count derivable from that photo; visible-in-frame count ~66-70
is a floor, not a total.

**User correction (important, changes the matching methodology going
forward):** `MT1204` is a **batch code**, not an incompatible identifier
scheme — GTIN being absent on a label doesn't mean the item can't be
reconciled. User also confirmed: (a) serial numbers are always unique per
individual unit across all products (never shared/grouped), and (b) Item 1's
sideways case-level code (`1459466A0`) is a real, usable validation field
(user called it "SSCC," though it doesn't match the formal 18-digit numeric
GS1 SSCC format — using it functionally as a case-level identifier regardless).
Full corrected hierarchy now documented above in the Methodology section:
GTIN → Batch/Lot Code → SSCC/case code → Serial Number (uniqueness check only).

**Re-validated MT1204 under the corrected hierarchy:** still genuinely no
match on this invoice (checked batch code specifically, not just GTIN) —
Item 1's batch is `2120209`, Item 2's is `41016`, neither is `MT1204`. Same
conclusion as before, but now reached for the right reason.

**New standing requirement:** every scan report must include concrete reupload
suggestions when image quality (blur/angle/cropping) blocks a reliable read,
not just a passive confidence caveat. Applied retroactively as a table in this
round's report (Picture2: reupload straight-on close-up of labels; Picture4:
reupload full uncropped carton photo; Picture3: split into closer photos or
one top-down shot).

### Round 13 — 2026-08-19: SSCC/case-code containment check (Item 1)
Ran the case/SSCC-containment rule (from the new backlog below) against Item
1's existing data, per the SOP's per-cell verification step rather than
trusting the earlier whole-image impression that all case codes matched.
Cropped and individually re-verified all 12 boxes' case-code region (not
reused from memory) — confirmed `1459466A0` on all 12, no stray/mismatched
case code. Cross-checked the case's 12 contained serials against invoice
Annex A: exact 1:1 match, no extras, no missing. **Result: pass**, but flagged
as a positive control (Annex A was built from this same image) — a genuine
negative-control test (inject a foreign serial under the same case code, or
give one unit a different case code) is still needed to prove the rule
actually catches a real problem, not just confirms consistent data.

### Round 14 — 2026-08-19: SSCC/case-code containment check, negative control
Ran two synthetic fault scenarios against the real invoice data (Annex A,
Item 1 unchanged) to prove the containment rule actually catches problems,
not just passes clean data (Round 13 was a positive control only). Script:
`sscc_negative_control.py` (scratchpad).

- **Scenario A — foreign serial in the case** (13 units scanned under case
  `1459466A0`, 12 real + 1 fabricated `1099999999999`, invoice still says
  qty 12): correctly flagged both a quantity mismatch (over by 1) and the
  specific unexpected serial with no invoice entry.
- **Scenario B — one unit's case code mismatched** (same 12 real serials,
  same qty=12, but serial `1007499603293` given case code `1459466B1`
  instead of `1459466A0`): correctly flagged as a case-code inconsistency
  naming the exact serial — **even though a plain serial-count/match check
  would have reported a clean pass** (all 12 serials still individually
  match Annex A, count still 12=12). This is real evidence the case-level
  containment rule catches a mispacking-type error that pure serial
  reconciliation misses entirely — not redundant with the checks already
  in the backlog.

**Conclusion:** the SSCC/case-containment rule is validated as functional
(catches real injected faults, not just a rubber stamp) — promote it from
"candidate" to a rule with a working reference implementation for the POC.

## Full Validation Rule Set — 19 rules, ALL committed to the POC build
User directive (Round 15, reaffirmed from Round 15's predecessor instruction):
every rule below is in scope for the actual POC implementation — none are
optional extras to cut. The tested/not-yet-tested split is kept only as an
internal maturity tracker (useful for the client presentation: it shows some
rules are already proven, not just designed), not as a signal that the
untested ones are lower priority or up for debate. When the POC is built,
every rule here needs a working implementation.

First 5 already have a working reference implementation and passed real
tests (count match, GTIN→Batch→Case-code hierarchy, duplicate-serial check,
image-quality gate, case-containment check). Rules 6–19 are fully designed
below and scheduled for implementation — not yet exercised only because
we're still in the manual R&D phase, before any code is written. Rules 14–19
were added Round 15, driven directly by the client's Tatmeen/SSCC/pharma
requirements doc — see "Tatmeen integration" section above for the context
behind them. Grouped by what each catches.

**Data-integrity rules (cheap, catch errors before touching the invoice):**
- **GTIN check-digit (Mod-10) validation** — validate the extracted GTIN's
  check digit mathematically before trusting it. Catches an OCR misread digit
  for free, no invoice needed.
- **Mfg-before-Exp sanity check** — flag if Mfg date is after Exp date, or if
  Exp−Mfg doesn't match the product's expected shelf life. Catches OCR
  digit-swaps (relevant — we hit real MF/MT-1204 read ambiguity in testing).

**Quantity rules (richer than plain equal/not-equal):**
- **Signed variance reporting** — report "expected 60, found 58, short by 2"
  with direction, not just ✅/❌. That's what a warehouse team acts on.
- **UOM consistency check** — confirm the invoice's unit (EA vs CTN vs BOX)
  matches what the image is actually counting, to avoid a false N× discrepancy
  from counting units when the invoice line means cartons (or vice versa).

**Expiry/compliance rules (Tatmeen-relevant, not just reconciliation):**
- **Expired / near-expiry flag** — independent of invoice matching: is this
  stock already expired, or inside a near-expiry window, at time of scan?

**Aggregation rules (directly named in the RFP — "parent-child relationships
and bundle management"):**
- **Case/SSCC ↔ unit-serial containment check** — does the set of unit serials
  scanned inside a carton match what the case-level code claims to contain?
  **VALIDATED (Rounds 13–14)**: passed a positive control against Item 1, then
  correctly caught two injected faults in a negative-control test — a foreign
  serial in the case, and one unit with a mismatched case code (the latter
  slips past a plain serial-match check entirely, so this rule adds real,
  non-redundant coverage). Reference implementation:
  `sscc_negative_control.py` (scratchpad, Round 14). **Needs extending for
  Round 15's SSCC hierarchy requirement (rule 17 below)** — this rule as
  tested only covers one flat case, not a child→master SSCC tree.
- **Cross-photo duplicate detection** — when a shipment is scanned across
  multiple photos (like Picture3–6), check the same serial doesn't appear in
  two different photos, which would mean double-counting one physical box
  rather than counting two different boxes.

**Process rules (explicitly asked for in RFP §5.3):**
- **Confidence-weighted auto-approval** — attach a confidence score per
  extracted field; auto-pass only above a threshold, route lower-confidence
  reads to a manual-review queue instead of silently reporting them as fact.
  We've effectively been doing this manually every round (flagging low-
  confidence reads) — this formalizes it as a numeric-threshold rule.
- **Many-to-many matching** — don't assume 1 image = 1 invoice line; support a
  shipment split across multiple lines or multiple invoices (partial
  deliveries), not just pairwise comparison.

**Tatmeen rules (rules 14–19, added Round 15 — pharma-only unless noted):**
- **14. Tatmeen reported-status check** — is this GTIN+Batch+Serial (+Invoice
  Number) found and marked Reported in the Tatmeen dummy database at all?
  Not-found or Not-Reported → exception. This is Stage 2 of the client's core
  pipeline (Invoice → Scan → Invoice Validation → **Tatmeen Validation** →
  Quantity Validation → SSCC Validation → Final Status).
- **15. Tatmeen quantity validation** — does Tatmeen's reported quantity for
  this GTIN+Batch satisfy the invoice's expected quantity? Exact-match vs.
  "≥ is enough" is an **open question (#1 above)** — build this rule
  configurable, don't hardcode one interpretation.
- **16. Pharma/Non-Pharma conditional branching** — route pharma items
  through the full GTIN/Batch/Serial + Tatmeen pipeline; route non-pharma
  items through quantity-only validation, skipping Tatmeen entirely. Getting
  this branch wrong (e.g. running Tatmeen checks on non-pharma items) would
  itself be a bug worth testing for.
- **17. SSCC hierarchy validation** — extends rule 5 (case-containment,
  already validated) from a single flat case to a real parent/child tree:
  child SSCC quantities must sum correctly to their master SSCC, each SSCC's
  own reported-status in Tatmeen must be checked, and the SSCC must belong to
  the correct shipment. Rule 5's tested logic is a genuine head start here —
  this is additive complexity, not a rewrite.
- **18. Time-window Pending-status logic** — a "not yet reported in Tatmeen"
  result is **not automatically a failure**: if it's still inside the agreed
  reporting grace window (assumed 1–2 days, unconfirmed — open question #5),
  the correct status is 🟡 Pending, not 🔴 Failed. Needs a reporting
  timestamp comparison, not just a boolean lookup — genuinely new logic, nothing
  in Rounds 1–14 needed a time dimension before this.
- **19. Cumulative/partial-scan tracking** — support scanning the same
  invoice/batch across multiple separate sessions (e.g. 5,000 units today,
  5,000 more tomorrow) and track running totals (Previously Scanned / Current
  Scan / Total Scanned / Remaining) against both the invoice and Tatmeen.
  Distinct from cross-photo duplicate detection (rule 13, which stops
  double-counting the *same* box) — this is correctly *accumulating*
  legitimately separate deliveries. Requires persisted state across sessions
  (a local SQLite file is enough for the POC — still "no paid services," but
  not fully stateless either; flag this for the project plan).

### Round 15 — 2026-08-19: client requirements doc reconciled into scope
**Inputs:** `Pharma & Non-Pharma Shipment Validation POC – Updated
Requirements & Demo Flows.md` + `Demo Validation flows.png` (client-provided),
cross-checked against RFP, Sample Invoice.pdf, and Rounds 1–14.

**Analysis delivered first (chat only, no file changes)**, then user directed:
adopt "Tatmeen" spelling; GTIN→Serial is the confirmed invoice-matching
fallback (client committing to GTIN-on-all-future-invoices); generate
invoice-numbered sample invoices (queued, not yet built); resolve remaining
open items using best judgment and record what was changed.

**Updates made to this file** (detailed inline above, summarized here):
- New "Tatmeen integration & 3-way validation model" section — the core
  structural addition: image↔invoice↔Tatmeen, not just image↔invoice.
- New "Pharma vs. Non-Pharma categorization" section.
- Identity-matching hierarchy resolved: GTIN → Serial (invoice-matching),
  kept distinct from the separately-valid GTIN→Batch→Case extraction-side
  fallback from Round 9.
- Seven client demo flows recorded, with Flow 3 given a proposed (not yet
  client-confirmed) resolution: the RFP-required OCR-fallback path, which
  none of flows 1–7 otherwise covers and which Rounds 1–5 already did real
  work validating.
- Rule set expanded from 13 to **19** — added rules 14–19, all Tatmeen/SSCC-
  hierarchy/pharma-branching/pending-status/cumulative-scan related. Rule 5
  (case-containment) flagged as needing extension for real SSCC hierarchy.
- 10 open questions carried forward from the client's own §15, kept
  unresolved on purpose (not ours to assume away) — see list above.

**Not done in this round (queued):** regenerating sample invoices with a
proper `INV0xx` numbering convention (current `Test_Invoice_Item1_Item2.pdf`
still uses a placeholder reference) — queued as an early task in
`project-plan.md` rather than done ad hoc here.

**Next:** `project-plan.md` created alongside this update — tech stack, user
personas, phased scope, and the full open-questions list, for user validation
before any code is written.

### Round 16 — 2026-08-19: POC actually built and running
**Status change: no longer R&D-only — a working implementation exists** at
`poc-app/` (FastAPI + SQLite backend, React + Vite + Tailwind frontend).
Full detail in `poc-app/README.md`; summary here for continuity with the
findings log.

- All 19 rules implemented as real functions (`poc-app/backend/app/services/
  validation_engine.py`), not stubs.
- All 7 client demo flows seeded and **verified live against a running
  server** during the build — every flow's dashboard output checked against
  the client doc's expected result, not just assumed to work.
- Per user instruction: Tatmeen and "ERP" are dummy flows only — Tatmeen is
  a SQLite table seeded locally, invoices are seeded rows, nothing external
  is called unless `EXTRACTION_MODE=live` is explicitly set (opt-in, real
  Anthropic vision call, off by default — see project-plan.md's cost flag).
- **Two real bugs found by testing the build, not just written and trusted:**
  (1) synthetic GTIN placeholders failed the checksum rule — fixed by
  generating valid-checksum demo GTINs; (2) a data-flow bug let
  `tatmeen_status` show "yellow" while `overall_status` showed "red" for the
  same item — fixed by giving rule 18 sole ownership of the fail-vs-pending
  decision. Both documented as code comments in `validation_engine.py`.
- Known, documented gaps (not silently skipped): live-mode scan has no
  frontend UI yet; rule 5 (case-containment) isn't wired into the generic
  per-flow pipeline (proven correct via a dedicated `/sscc-demo` endpoint
  instead, since none of the 7 flows declare a fixed expected-serial
  roster); PDF invoice generation wasn't rebuilt for the 7 seeded invoices.

### Round 17 — 2026-08-20: UI overhaul — product feel, not a testing tool
User feedback: Round 16's UI was functionally correct but looked like a
bare testing harness (flat dropdowns, no login, no real flow). Rebuilt the
frontend around the exact flow the user described: upload invoice → invoice
preview + extracted data side by side → upload item photo → photo +
extracted data side by side → match confirmation → Tatmeen check (animated)
→ summary. Added a dummy animated login screen (demo credentials shown,
frontend-only — no real auth, consistent with Tatmeen/ERP being dummy too),
a persistent sidebar app shell, a Dashboard (stat tiles + recent activity),
and a History listing page. `framer-motion` added for real transitions
(login blobs, step transitions, staged reveals, Tatmeen-check spinner).

Backend: added `GET /api/dashboard/summary/all` (used by both Dashboard and
History, one call instead of N+1). Validation logic itself is unchanged —
this round was UI/UX only, reusing the same 19 rules and pipeline verified
in Round 16.

**Honesty note carried forward deliberately**: the new wizard's "extracted
invoice/item data" still comes from the same deterministic mock-seed system
as before — uploading a real file changes the preview image shown, not the
data returned, unless `EXTRACTION_MODE=live`. This was true and visible in
Round 16's flat dropdown UI too; Round 17 just presents the same underlying
mechanism as a guided flow instead of a raw control. Documented explicitly
in `poc-app/README.md` so it isn't mistaken for real invoice OCR.

Old `InvoiceListPage`/`InvoiceDetailPage` removed (superseded by
`ScenarioPickerPage`/`ValidationWizardPage`) — no dangling dead code.

### Round 18 — 2026-08-20: real extraction, no API key needed
User feedback: Round 17's polished UI still fundamentally ran on mock/seeded
data — invoice upload didn't extract anything real, item scans came from a
dropdown, and reopening a flow lost all progress. User wanted genuine
real-time validation: upload invoice → real extraction → upload photo →
real extraction → automatic compare → human intervention on mismatch →
explicit "Validate with Tatmeen" button on match → real Tatmeen result.

**Key discovery: this doesn't need the Anthropic API.** Tested two free,
local technologies directly against real files before building anything:
- `zxing-cpp` — unlike `pyzbar`/`pylibdmtx` (Round 5, blocked by a Windows
  DLL issue), this one just works. Decoded 10 of 12 real DataMatrix codes
  from Picture1.png directly, exact match with Round 4/13's manually
  transcribed data.
- Tesseract OCR (installed via `winget install UB-Mannheim.TesseractOCR`,
  not just pip) + PyMuPDF for PDF rendering — correctly read 7 of 8 real
  line items (GTIN, batch, qty, expiry) directly off the real
  `Sample Invoice.pdf`, with the kind of small OCR character-confusions
  ("R25H03"→"R25HO3") that are genuinely expected, not a bug.

**Built:** `app/services/real_extraction.py` (barcode decode + GS1 AI
parsing + OCR + invoice-line regex parser, disclosed as tuned to Sample
Invoice.pdf's layout — not a universal parser). New endpoints:
`POST /api/invoices/upload` (real OCR ingestion, creates a real Invoice
record from whatever was actually read), `POST /api/scans/upload-real`
(real barcode decode, matches each decoded GTIN/Batch to an invoice line,
handles multiple items in one photo and unmatched/unexpected items),
`GET /api/scans/results/{invoice_number}` (state persistence — fixes the
"reopening loses data" bug), `POST /api/scans/{id}/resolve` (real
human-intervention action: accept-with-override or reject, persisted).

**Verified fully end-to-end with real files, not just unit-level**:
uploaded `Real_Test_Invoice_Item1.pdf` (a fixture built this round, real
GTIN 00300036120018/Batch 2120209/Qty 12 in Sample Invoice.pdf's OCR-
friendly layout) → real OCR extraction → uploaded Picture1.png → real
barcode decode found 10 of 12 → real quantity mismatch ("short by 2",
genuinely emergent from the incomplete decode, not scripted) → real expiry
check (correctly flagged expired against actual today's date) → human
"Accept & Proceed" override → real Tatmeen lookup (found, reported,
qty sufficient) → "Validated from Tatmeen". Also verified the fully-
unmatched case (Sample Invoice.pdf + Picture1.png, genuinely different
GTINs → correctly reported as unexpected stock, zero results).

**Two more real bugs caught by testing, not assumed away:**
- Tatmeen lookup required an exact invoice-number match, which meant a
  genuinely new uploaded invoice could never match Tatmeen even for a
  GTIN/Batch that's really in the dummy DB — fixed with a GTIN+Batch-only
  fallback (matches how a real national Tatmeen DB is actually indexed).
- A stray `--reload` uvicorn process held a file lock on `poc.db`,
  silently serving stale data through a just-added endpoint even after a
  "clean" restart — caught by checking the endpoint's actual output, not
  just that it returned 200. Multiple accumulated stray processes across
  the session's restarts were the root cause; resolved by killing all and
  running a single non-`--reload` instance.

**Frontend restructured**: two clearly separate, clearly labeled entry
points — "New Validation" (real, `RealValidationStartPage` +
`RealScanFlow`) vs. "Demo Scenarios" (seeded, tagged "Seeded data" on
every screen) — since blurring these together was the root of the original
complaint. `ValidationWizardPage` branches on `invoice.demo_flow === null`
to route between them.

**Known, disclosed limits, not hidden**: invoice parser is regex-tuned to
one real layout (422 with a text snippet on failure, not a silent wrong
answer); barcode decode isn't 100% (a real-world rate, not a bug); no real
photo→count path for non-pharma (unsolved per the SOP's own Round 11-12
findings); OCR-fallback for damaged barcodes still needs either tuned OCR
or the unconfigured live-vision path. All documented in
`poc-app/README.md`.

### Round 19 — 2026-08-20: client spec formalization — SAP source, scanner UI, rich summary
User provided `Updated POC Validation Flow – Real-Time Invoice, Image
Extraction & Tatmeen Validation.md`, formalizing and extending the real-data
direction from Round 18 into a full spec. Implemented:

**Backend:**
- `app/services/sap_source.py` — clean `SAP Data Source -> Invoice Data`
  abstraction per the spec's explicit instruction; `GET /api/invoices/sap`
  goes through it exclusively. `Invoice.source` ("sap"|"upload") and
  `Invoice.supplier` added.
- `app/services/tatmeen_adapter.py` — formal `TatmeenAdapter` class,
  extracted from inline pipeline.py queries; adds a "Tatmeen Validation
  Failed" branch (system error) distinct from "not reported" (business
  result), per spec §9.
- `ScanEvent.extracted_expiry` added, and every scan response now returns a
  `scanned: {gtin, batch, expiry, case_sscc, serials}` object — the actual
  detected values, not just finding-message text — so the frontend can
  render genuine field-by-field comparison tables.
- Real bug caught: `invoice.demo_flow === null` was being used as the
  real-vs-SAP branch signal, but INV008 (bonus pending-status demo) has
  `demo_flow=null` AND `source="sap"` — would have misrouted it into the
  real-upload UI. Fixed by exposing `source` and branching on that instead.

**Frontend:**
- `StartValidationPage` replaces the old split `/validate` +
  `/demo-scenarios` nav entries — one screen, two sections ("Invoices from
  SAP" table + "Upload Invoice"), matching the spec's actual described flow
  (one branching step, not two destinations).
- `ScannerFrame` — viewfinder-style capture UI (corner brackets, animated
  scan line, status bar) replacing the plain dropzone specifically for the
  box/item photo step, per spec §4's "modern mobile/payment scanner"
  request. Upload remains the actual capture mechanism (no camera access in
  a desktop POC) — presented inside this frame rather than a bare file input.
- `ScanResultCard` rewritten: real field-by-field compare table (GTIN,
  Batch, Quantity, Expiry, SSCC — using the new `scanned` data, not
  finding-text parsing), structured Discrepancies table (Field/Expected/
  Detected/Reason/Recommended Action per spec §7), and a real reviewer
  reason input wired to the already-existing `resolve` endpoint's `note`
  param (was previously always sent empty — the UI just never asked).
- `FinalSummary` — four sub-sections (Invoice/Physical Scan/Matching/
  Tatmeen) computed dynamically from real results, 3-tier final result
  ("Validation Successful" / "Completed with Exceptions" / "Human
  Intervention Required") per spec §11 — not a single hardcoded badge.
  Used by both the SAP/demo wizard and RealScanFlow.

**Verified end-to-end again after the rewrite** (not just build-succeeded):
SAP list endpoint, invoice detail fields, mock scan's `scanned` payload,
full real upload -> scan -> resolve-with-reason -> state-persistence-reload
chain, all re-tested live against the running server.

## Notes for future POC build
- See `project-plan.md` (created Round 15) for tech stack, phases, personas,
  and data model, and `poc-app/README.md` (Rounds 16–19) for what's actually
  implemented, what's a known gap, and how to run it.
