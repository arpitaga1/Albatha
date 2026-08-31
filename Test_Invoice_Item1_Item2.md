# TEST INVOICE — derived from Picture1.png & Picture2.png

**This is NOT a real tax invoice.** It's a test data file, built in the same table
structure as `Sample Invoice.pdf`, but with GTIN/Batch/Expiry/Serial data actually
read off the two photographed cartons (Item 1 / Item 2), so we have real invoice-side
data to reconcile against the image-side counts. Sample Invoice.pdf's own line items
do not match either picture's GTIN, so nothing there was reusable beyond the format.

Header fields below are carried over from Sample Invoice.pdf purely for format
consistency (same customer/ship-to) — not verified against a real order for this
shipment.

| Field | Value |
|---|---|
| Sold-To / Ship-To | MPC Drug Store Company L.L.C (Sole Proprietorship), Exhibition Showroom No1, Jurf Indus, Ajman |
| Reference | TEST-INV-001 (not a real Tatmeen/SAP document number) |
| Date | 2026-08-18 |

## Line items

| Line | GTIN | Description | SLOC | Batch/Lot | Mfg | Expiry | Qty | UOM |
|---|---|---|---|---|---|---|---|---|
| 1 | 00300036120018 | *Unknown — not printed on label; would resolve via SAP ERP master-data lookup by GTIN, per RFP §5.3* | WM01 | 2120209 | — | 2026-06 | **12** | EA |
| 2 | 03664798023251 | *Unknown — not printed on label; would resolve via SAP ERP master-data lookup by GTIN* | WM01 | 41016 | 2024-06 | 2026-05 | **20** | EA |

## Serial Numbers — Item 1 (GTIN 00300036120018, Batch 2120209, Qty 12)
**Confidence: high** — labels were legible at full image resolution, cross-checked across all 12 boxes.

| # | Serial Number |
|---|---|
| 1 | 1037937537575 |
| 2 | 1068077918463 |
| 3 | 1072254253703 |
| 4 | 1055969362709 |
| 5 | 1069150858268 |
| 6 | 1029547440017 |
| 7 | 1007499603293 |
| 8 | 1083054485175 |
| 9 | 1091890218839 |
| 10 | 1067563877542 |
| 11 | 1057909533493 |
| 12 | 1018278484685 |

## Serial Numbers — Item 2 (GTIN 03664798023251, Batch 41016, Qty 20)
**Confidence: LOW — placeholders, not real OCR reads.** Picture2 was shot at a steep
angle; the shared fields (GTIN/Batch/Mfg/Exp) repeat 20× so those are trustworthy, but
the individual serial suffixes are small rotated alphanumeric strings I could not
reliably resolve digit-by-digit. Rather than invent plausible-looking codes that could
be wrong, every serial below is a placeholder (`PH-ITEM2-##`) — good enough to validate
the reconciliation *logic* (does a mismatch get caught, is it reported against the
right line), but **not to be treated as the real printed values.**

| # | Serial Number (placeholder) |
|---|---|
| 1 | PH-ITEM2-01 |
| 2 | PH-ITEM2-02 |
| 3 | PH-ITEM2-03 |
| 4 | PH-ITEM2-04 |
| 5 | PH-ITEM2-05 |
| 6 | PH-ITEM2-06 |
| 7 | PH-ITEM2-07 |
| 8 | PH-ITEM2-08 |
| 9 | PH-ITEM2-09 |
| 10 | PH-ITEM2-10 |
| 11 | PH-ITEM2-11 |
| 12 | PH-ITEM2-12 |
| 13 | PH-ITEM2-13 |
| 14 | PH-ITEM2-14 |
| 15 | PH-ITEM2-15 |
| 16 | PH-ITEM2-16 |
| 17 | PH-ITEM2-17 |
| 18 | PH-ITEM2-18 |
| 19 | PH-ITEM2-19 |
| 20 | PH-ITEM2-20 |

**To upgrade Item 2 to real data:** either send a sharper/straighter close-up of a few
Item 2 labels so the serials can be read for real, or provide the actual serial list
if you have it from another source (e.g. the Tatmeen packing data / SAP record for
this batch).
