from typing import Optional
from pydantic import BaseModel, ConfigDict


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_name: str
    gtin: Optional[str]
    batch: str
    expiry: Optional[str]
    mfg_date: Optional[str]
    qty: int
    uom: str
    category: str
    sscc: Optional[str]


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    invoice_number: str
    sold_to: str
    ship_to: str
    supplier: str = ""
    invoice_date: str
    demo_flow: Optional[int]
    source: str = "upload"  # "sap" | "upload" — the real branch signal, see StartValidationPage
    source_file_name: Optional[str] = None  # servable at /api/files/<name> — null for SAP-seeded invoices
    line_items: list[LineItemOut]


class InvoiceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    invoice_number: str
    demo_flow: Optional[int]
    item_count: int


class ValidationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    line_item_id: int
    invoice_match_status: str
    tatmeen_status: str
    quantity_status: str
    sscc_status: str
    overall_status: str
    resolution_action: Optional[str] = None
    resolution_note: Optional[str] = None
    findings: list[dict]


class ScanEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    line_item_id: int
    extracted_gtin: Optional[str]
    extracted_batch: Optional[str]
    extracted_serials: list[str]
    case_sscc: Optional[str]
    scanned_qty: int
    confidence: float
    image_quality_ok: bool
    notes: list[str]


class ScanRequest(BaseModel):
    """Used by the mock-mode scan endpoint (JSON body) — no file upload needed
    for demo flows since results are seeded/deterministic. The real-mode
    endpoint (multipart file upload) uses a separate route."""
    line_item_id: int
    seed_key: Optional[str] = None  # which seeded extraction result to replay


class DashboardLineItem(BaseModel):
    item_name: str
    category: str
    invoice_status: str
    tatmeen_status: str
    quantity_status: str
    sscc_status: str
    overall_status: str


class DashboardOut(BaseModel):
    invoice_number: str
    total_items: int
    pharma_count: int
    non_pharma_count: int
    items: list[DashboardLineItem]
    overall_shipment_status: str
    reason: Optional[str]
