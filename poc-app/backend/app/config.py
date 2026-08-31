"""
Central configuration for the POC. Every setting here maps to an open
question or an assumption recorded in Claude.md — kept in one place so a
client-confirmed answer is a one-line change, not a hunt through the code.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # local secrets (ANTHROPIC_API_KEY etc.) — gitignored, never committed

DB_PATH = BASE_DIR / "poc.db"
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

# Claude.md open question #1: exact-match vs "Tatmeen qty >= invoice qty".
# Default to "gte" (>=) since the client's own worked examples (10,000 vs
# 10,000) never actually exercise a case where Tatmeen has MORE than the
# invoice — gte is the safer default until confirmed. Change to "exact" to
# require an exact match instead.
TATMEEN_QTY_MODE = os.environ.get("TATMEEN_QTY_MODE", "gte")  # "gte" | "exact"

# Claude.md open question #5: Tatmeen reporting grace window, assumed 1-2
# days in the client doc. Using 2 days (the upper bound of their stated
# assumption) as the default.
TATMEEN_GRACE_DAYS = int(os.environ.get("TATMEEN_GRACE_DAYS", "2"))

# Claude.md open question #3: does one unreported pharma item fail the
# WHOLE shipment, or just that line? Defaulting to "line" (fail only the
# affected line, shipment goes to Manual Intervention rather than a hard
# Return) since that's the less destructive default and easy to flip once
# confirmed.
UNREPORTED_ITEM_FAILS_SHIPMENT = os.environ.get("UNREPORTED_ITEM_FAILS_SHIPMENT", "false").lower() == "true"

# Claude.md open question #4: same question, for SSCC not reported.
UNREPORTED_SSCC_FAILS_SHIPMENT = os.environ.get("UNREPORTED_SSCC_FAILS_SHIPMENT", "false").lower() == "true"

# Image-quality gate threshold (rule 4 / rule 12): extraction confidence
# below this routes to manual review instead of auto-approval.
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.75"))

# Extraction backend: "mock" replays seeded/known results (safe default, no
# API cost, deterministic for demos) or "live" calls the Anthropic API for
# real vision extraction (requires ANTHROPIC_API_KEY). See
# app/services/extraction.py. Defaulting to mock — per project-plan.md §4,
# live vision extraction has a real per-call cost that wasn't explicitly
# confirmed, so it's opt-in, not silently on.
EXTRACTION_MODE = os.environ.get("EXTRACTION_MODE", "mock")  # "mock" | "live"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Comma-separated list of frontend origins allowed to call this API. Local
# dev origins are always included so `npm run dev` keeps working without
# any env var set; add the deployed frontend's real origin (e.g. a Vercel
# URL) via ALLOWED_ORIGINS in production rather than hardcoding it, since
# that URL isn't known until after the frontend's first deploy.
ALLOWED_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    *[o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()],
]
