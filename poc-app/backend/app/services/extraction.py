"""
Extraction service — mock/seeded backend only.

Replays deterministic, pre-seeded results for the 7 client demo flows: no
API key needed, no per-call cost, no flakiness during a live client
presentation. Every seeded result is labeled clearly as demo data, not a
real capture.

Real (non-seeded) item-photo extraction lives entirely in
app/services/real_extraction.py — barcode decode (zxing-cpp) first, then
OpenCV box detection + local Tesseract OCR as a fallback/cross-check. There
is no Anthropic-based backend for item photos anywhere in this app, by
explicit user directive — a previous "live" mode here that called Claude
vision has been removed, not just disabled.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractionResult:
    gtin: str | None
    batch: str | None
    serials: list[str]           # one per unit found in this scan
    case_sscc: str | None
    mfg_date: str | None
    exp_date: str | None
    scanned_qty: int
    confidence: float            # 0.0-1.0
    image_quality_ok: bool
    notes: list[str] = field(default_factory=list)


# --- Mock backend -----------------------------------------------------

# Deterministic seed library. Keys are chosen by the seed/demo data
# (services/seed_data.py) so each demo-flow scan resolves to a known,
# repeatable outcome. Grounded in Round 4/13's real Item 1 data where it
# makes sense to reuse it (continuity with actual R&D testing), synthetic
# elsewhere per the client's own "Item 1 / Item 2 / B1 / B2" demo convention.
MOCK_SEED_LIBRARY: dict[str, ExtractionResult] = {
    # Flow 1 / Flow 2 / Flow 6 — Item 1, reported, clean scan.
    # Real data from Picture1.png / Round 4-6 (12 units, GTIN 00300036120018).
    "item1_clean": ExtractionResult(
        gtin="00300036120018", batch="2120209",
        serials=[
            "1037937537575", "1068077918463", "1072254253703", "1055969362709",
            "1069150858268", "1029547440017", "1007499603293", "1083054485175",
            "1091890218839", "1067563877542", "1057909533493", "1018278484685",
        ],
        case_sscc="1459466A0", mfg_date=None, exp_date="2028-06",
        scanned_qty=12, confidence=0.97, image_quality_ok=True,
        notes=["Extraction confidence high — matches Round 4/13 real test data (Item 1)."],
    ),
    # Flow 1 — Item 2, reported, clean scan (pairs with item1_clean).
    "item2_reported": ExtractionResult(
        gtin="00800000200024", batch="B2", serials=[f"SN2R-{i:03d}" for i in range(1, 11)],
        case_sscc=None, mfg_date="2025-01", exp_date="2027-06",
        scanned_qty=10, confidence=0.95, image_quality_ok=True, notes=[],
    ),
    # Flow 2 / Flow 6 — Item 2, NOT reported in Tatmeen (see seed_data.py).
    "item2_not_reported": ExtractionResult(
        gtin="00800000200024", batch="B2", serials=[f"SN2-{i:03d}" for i in range(1, 11)],
        case_sscc=None, mfg_date="2025-01", exp_date="2027-06",
        scanned_qty=10, confidence=0.93, image_quality_ok=True,
        notes=["Clean scan; Tatmeen status determined separately by the validation engine."],
    ),
    # Flow 4 — SSCC reported, three items under a hierarchy.
    "item3_sscc_reported": ExtractionResult(
        gtin="00800000300038", batch="B3", serials=[f"SN3-{i:03d}" for i in range(1, 13)],
        case_sscc="SSCC-CHILD-001", mfg_date="2025-03", exp_date="2027-09",
        scanned_qty=12, confidence=0.95, image_quality_ok=True, notes=[],
    ),
    # Flow 5 — SSCC not reported.
    "item3_sscc_not_reported": ExtractionResult(
        gtin="00800000300038", batch="B3", serials=[f"SN3B-{i:03d}" for i in range(1, 9)],
        case_sscc="SSCC-CHILD-999", mfg_date="2025-03", exp_date="2027-09",
        scanned_qty=8, confidence=0.94, image_quality_ok=True, notes=[],
    ),
    # Flow 6 — non-pharma Item 3 (invoice batch B3, qty 100), full match.
    "nonpharma_clean": ExtractionResult(
        gtin=None, batch="B3", serials=[], case_sscc=None,
        mfg_date=None, exp_date=None, scanned_qty=100, confidence=0.9,
        image_quality_ok=True, notes=["No 2D barcode present — non-pharma, quantity-only validation."],
    ),
    # Flow 7 — Item 1 (invoice batch B1, qty 100), full match.
    "nonpharma_b1_match": ExtractionResult(
        gtin=None, batch="B1", serials=[], case_sscc=None,
        mfg_date=None, exp_date=None, scanned_qty=100, confidence=0.9,
        image_quality_ok=True, notes=["No 2D barcode present — non-pharma, quantity-only validation."],
    ),
    # Flow 7 — Item 2 (invoice batch B2, qty 100), deliberately short by 5 to
    # demonstrate the quantity-mismatch outcome within the same flow.
    "nonpharma_b2_short": ExtractionResult(
        gtin=None, batch="B2", serials=[], case_sscc=None,
        mfg_date=None, exp_date=None, scanned_qty=95, confidence=0.9,
        image_quality_ok=True, notes=["No 2D barcode present — non-pharma, quantity-only validation."],
    ),
    # Flow 3 (proposed, unconfirmed with client — Claude.md Round 15) —
    # DataMatrix damaged/unreadable, RFP-required OCR fallback reads the
    # printed label text instead. Lower confidence than a clean barcode
    # decode, no GTIN recovered — exercises rule 6 (skipped, no GTIN) and
    # rule 12 (confidence-weighted review) together.
    "item_ocr_fallback": ExtractionResult(
        gtin=None, batch="OCR-B5", serials=["OCR-SN-000451"], case_sscc=None,
        mfg_date="2025-02", exp_date="2027-05",
        scanned_qty=1, confidence=0.68, image_quality_ok=True,
        notes=[
            "DataMatrix unreadable (damaged label) — fell back to OCR of the "
            "printed GTIN/Batch/Expiry text per RFP §5.3. GTIN not recovered; "
            "matching on Batch + Serial instead.",
        ],
    ),
    # Deliberately poor-quality scan — exercises rule 4 (image-quality gate)
    # and rule 12 (confidence-weighted review), per client doc §11.
    "blurry_scan": ExtractionResult(
        gtin=None, batch=None, serials=[], case_sscc=None,
        mfg_date=None, exp_date=None, scanned_qty=0, confidence=0.35,
        image_quality_ok=False,
        notes=[
            "Image quality below threshold — label not reliably legible.",
            "Suggested action: retake the photo straight-on, closer, with better "
            "lighting, ensuring the full label is inside the frame.",
        ],
    ),
}


def extract_mock(seed_key: str) -> ExtractionResult:
    if seed_key not in MOCK_SEED_LIBRARY:
        raise KeyError(
            f"No mock extraction seeded for '{seed_key}'. Known keys: "
            f"{sorted(MOCK_SEED_LIBRARY)}"
        )
    return MOCK_SEED_LIBRARY[seed_key]


# --- Live AI-vision backend: REMOVED by explicit user directive ---------
# Item-photo extraction no longer has any Anthropic-based path anywhere in
# the app. What used to live here (extract_live, EXTRACTION_PROMPT) called
# Claude vision for a single item photo; that capability now lives in
# app/services/real_extraction.py as extract_via_opencv() — classical
# OpenCV box detection + local Tesseract OCR, no API key, no Anthropic call.
# See real_extraction.py's module docstring for the accuracy numbers this
# was verified against before replacing the AI-vision version.


def extract(seed_key: str | None = None) -> ExtractionResult:
    """Single entry point the mock/demo-flow scan endpoint calls. Only the
    seeded/mock backend remains here — real item-photo extraction (barcode
    decode, OpenCV+OCR fallback) lives entirely in real_extraction.py now."""
    if seed_key is None:
        raise ValueError("extract() requires a seed_key")
    return extract_mock(seed_key)
