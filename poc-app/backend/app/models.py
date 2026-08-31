"""
SQLAlchemy ORM models — SQLite only, no server, no paid database.
Field choices map directly to Claude.md's "Full Validation Rule Set" and
project-plan.md §5 (Data model sketch).
"""
import datetime as dt

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String
)
from sqlalchemy.orm import relationship

from app.database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    invoice_number = Column(String, unique=True, index=True, nullable=False)
    sold_to = Column(String, default="")
    ship_to = Column(String, default="")
    supplier = Column(String, default="")  # who shipped it — the "Supplier" column in the SAP list
    invoice_date = Column(String, default="")
    demo_flow = Column(Integer, nullable=True)  # 1-7, which client demo flow this seeds
    # "sap" = came from app.services.sap_source (dummy SAP data source, swappable for a real
    # SAP API later without touching the rest of the app); "upload" = user-uploaded + OCR'd.
    source = Column(String, default="upload")
    # Filename (not full path) of the originally-uploaded invoice document,
    # saved under config.UPLOADS_DIR, so a user can reopen and view exactly
    # what they uploaded later. Null for SAP-seeded invoices — there's no
    # real source document for those.
    source_file_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    line_items = relationship("InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    item_name = Column(String, nullable=False)
    gtin = Column(String, nullable=True)
    serial = Column(String, nullable=True)  # rarely present on an invoice line, but modeled — see Round 1 finding
    batch = Column(String, nullable=False)
    expiry = Column(String, nullable=True)
    mfg_date = Column(String, nullable=True)
    qty = Column(Integer, nullable=False)
    uom = Column(String, default="EA")
    category = Column(String, nullable=False)  # "pharma" | "non_pharma"
    sscc = Column(String, nullable=True)  # top-level SSCC this line ships under, if any
    sku = Column(String, nullable=True)
    manufacturer = Column(String, nullable=True)

    invoice = relationship("Invoice", back_populates="line_items")
    scan_events = relationship("ScanEvent", back_populates="line_item", cascade="all, delete-orphan")


class TatmeenRecord(Base):
    """Dummy/simulated Tatmeen database — no real Tatmeen integration in this POC."""
    __tablename__ = "tatmeen_records"

    id = Column(Integer, primary_key=True)
    gtin = Column(String, nullable=True)
    batch = Column(String, nullable=False)
    serial = Column(String, nullable=True)
    invoice_number = Column(String, nullable=False)
    reported = Column(Boolean, default=False)
    reported_qty = Column(Integer, default=0)
    sscc = Column(String, nullable=True)
    sscc_reported = Column(Boolean, default=False)
    reporting_date = Column(String, nullable=True)  # ISO date string, nullable if never reported


class SSCCRecord(Base):
    """Case/carton hierarchy — supports rule 17 (master/child SSCC validation)."""
    __tablename__ = "sscc_records"

    id = Column(Integer, primary_key=True)
    sscc_code = Column(String, unique=True, index=True, nullable=False)
    parent_sscc = Column(String, nullable=True)  # null = top-level/master
    invoice_number = Column(String, nullable=False)
    item_qty = Column(Integer, default=0)
    reported = Column(Boolean, default=False)


class ScanEvent(Base):
    """One image-scan submission against one invoice line item."""
    __tablename__ = "scan_events"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    line_item_id = Column(Integer, ForeignKey("invoice_line_items.id"), nullable=False)
    image_ref = Column(String, nullable=True)
    # Set only when this scan went through the OpenCV fallback/cross-check —
    # a copy of image_ref's photo with the detected item boundaries drawn
    # on it, numbered in detection order, so a reviewer can visually verify
    # what OpenCV actually found instead of just trusting a bare count.
    annotated_image_ref = Column(String, nullable=True)
    extracted_gtin = Column(String, nullable=True)
    extracted_batch = Column(String, nullable=True)
    extracted_expiry = Column(String, nullable=True)
    extracted_serials = Column(JSON, default=list)  # list[str], one per unit found in this scan
    case_sscc = Column(String, nullable=True)
    scanned_qty = Column(Integer, default=0)
    confidence = Column(Float, default=1.0)
    image_quality_ok = Column(Boolean, default=True)
    notes = Column(JSON, default=list)
    # A manual correction (resolve-with-corrected-values) supersedes every
    # prior scan for this line item rather than adding to them — without
    # this flag, cumulative quantity tracking (rule 19) treats a correction
    # as MORE physical stock found ("1 + 3 = 4"), not "the real count is 3,
    # replacing the earlier misread 1". Superseded events stay in the table
    # for audit history; every cumulative/duplicate calculation excludes them.
    superseded = Column(Boolean, default=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    line_item = relationship("InvoiceLineItem", back_populates="scan_events")


class ValidationResult(Base):
    """Latest computed validation outcome for one invoice line item."""
    __tablename__ = "validation_results"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    line_item_id = Column(Integer, ForeignKey("invoice_line_items.id"), unique=True, nullable=False)
    invoice_match_status = Column(String, default="pending")   # green | red | pending
    tatmeen_status = Column(String, default="n_a")             # green | yellow | red | n_a
    quantity_status = Column(String, default="pending")        # green | red | pending
    sscc_status = Column(String, default="n_a")                # green | yellow | red | n_a
    overall_status = Column(String, default="pending")         # green | yellow | red | pending
    findings = Column(JSON, default=list)  # list of {rule, severity, message}
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    # Human-intervention resolution (rule 12 / client doc "manual intervention"
    # workflow) — a real reviewer decision recorded against a real discrepancy,
    # not just a status color with nowhere to act on it.
    resolution_action = Column(String, nullable=True)   # "accepted" | "rejected" | None
    resolution_note = Column(String, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
