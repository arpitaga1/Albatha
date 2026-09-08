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

# Gemini vision extraction (separate, opt-in path from the Anthropic "live"
# mode above - see app/services/gemini_extraction.py). Real per-call cost
# same as any hosted vision model, so this is only used when explicitly
# invoked, not wired into the default scan pipeline.
#
# Routed through the user's company LLM gateway (an OpenAI-compatible
# proxy in front of Gemini), not Google's public API directly - the paid
# key issued by their IT team only works against this base_url, not
# generativelanguage.googleapis.com. GEMINI_BASE_URL defaults to Google's
# own endpoint so a plain Google AI Studio key (no base_url override)
# still works unmodified if this is ever pointed back at it.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_BASE_URL = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")

# Real-scan happy-flow guarantee (per explicit user directive): when on, any
# photo uploaded to /api/scans/upload-real - including a brand-new one
# captured live from the camera, for any invoice - reports an exact match
# against that invoice's own line items, instead of depending on the live
# barcode/OpenCV pipeline reproducing the same read reliably during a live
# demo. The only photos that still show the recapture prompt are the
# explicit reject entries in pinned_scans.py. Set to "false" to fall back to
# the live detection pipeline for every non-reject-pinned photo (the
# genuinely-tested-for-accuracy behavior from earlier in this project).
SCAN_HAPPY_FLOW = os.environ.get("SCAN_HAPPY_FLOW", "true").lower() == "true"

# Comma-separated list of frontend origins allowed to call this API. Local
# dev origins are always included so `npm run dev` keeps working without
# any env var set; add the deployed frontend's real origin (e.g. a Vercel
# URL) via ALLOWED_ORIGINS in production rather than hardcoding it, since
# that URL isn't known until after the frontend's first deploy.
ALLOWED_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    *[o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()],
]

# Vercel gives every deployment its own unique URL (e.g.
# https://albatha-3lesizhn4-damco-sales.vercel.app) in ADDITION to the
# stable custom domain (https://albatha-indol.vercel.app) - only the
# latter is normally in ALLOWED_ORIGINS above, so anyone opening a
# specific deployment's own URL (which the Vercel dashboard's own "Visit"
# button links to) hits a CORS error. This regex matches any deployment
# URL for this Vercel project so that keeps working without needing
# ALLOWED_ORIGINS updated on every single deploy.
ALLOWED_ORIGIN_REGEX = os.environ.get("ALLOWED_ORIGIN_REGEX", r"^https://albatha(-[a-z0-9]+)*\.vercel\.app$")
