export type Status = "green" | "yellow" | "red" | "n_a" | "pending";

export interface LineItem {
  id: number;
  item_name: string;
  gtin: string | null;
  batch: string;
  expiry: string | null;
  mfg_date: string | null;
  qty: number;
  uom: string;
  category: "pharma" | "non_pharma";
  sscc: string | null;
}

export interface Invoice {
  id: number;
  invoice_number: string;
  sold_to: string;
  ship_to: string;
  supplier: string;
  invoice_date: string;
  demo_flow: number | null;
  source: "sap" | "upload" | "preloaded";
  source_file_name: string | null;
  line_items: LineItem[];
}

export interface InvoiceSummary {
  id: number;
  invoice_number: string;
  demo_flow: number | null;
  item_count: number;
}

export interface Finding {
  rule: string;
  severity: "pass" | "info" | "warning" | "fail";
  message: string;
}

export interface Cumulative {
  previously_scanned: number;
  current_scan: number;
  total_scanned: number;
  remaining: number;
  status: string;
}

export interface ScannedData {
  gtin: string | null;
  batch: string | null;
  expiry: string | null;
  case_sscc: string | null;
  serials: string[];
  image_name: string | null;
  annotated_image_name: string | null;
  method: "barcode" | "opencv" | null;
  notes: string[];
}

export interface ValidationResult {
  line_item_id: number;
  invoice_match_status: Status;
  tatmeen_status: Status;
  quantity_status: Status;
  sscc_status: Status;
  overall_status: Status;
  resolution_action: "accepted" | "rejected" | null;
  resolution_note: string | null;
  findings: Finding[];
  cumulative: Cumulative;
  scanned?: ScannedData;
}

export interface UnmatchedBarcode {
  gtin: string | null;
  batch: string | null;
  count: number;
  serials: string[];
  expiry: string | null;
  image_name: string | null;
  annotated_image_name: string | null;
  message: string;
}

export interface RealScanResponse {
  results: ValidationResult[];
  unmatched: UnmatchedBarcode[];
  barcodes_found: number;
  photos_processed?: number;
  message?: string;
}

export interface SapInvoiceRow {
  invoice_number: string;
  invoice_date: string;
  supplier: string;
  item_count: number;
  total_quantity: number;
  status: Status;
  demo_flow: number | null;
}

export interface DashboardLineItem {
  item_name: string;
  category: string;
  invoice_status: Status;
  tatmeen_status: Status;
  quantity_status: Status;
  sscc_status: Status;
  overall_status: Status;
}

export interface Dashboard {
  invoice_number: string;
  total_items: number;
  pharma_count: number;
  non_pharma_count: number;
  items: DashboardLineItem[];
  overall_shipment_status: Status;
  reason: string | null;
}

export interface ShipmentSummaryRow {
  invoice_number: string;
  demo_flow: number | null;
  invoice_date: string;
  item_count: number;
  scanned_count: number;
  overall_status: Status;
}

export interface AllShipmentsSummary {
  shipments: ShipmentSummaryRow[];
  counts: Record<string, number>;
  total: number;
  tatmeen_counts: Record<string, number>;
  category_counts: Record<string, number>;
}
