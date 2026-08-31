# Pharma & Non-Pharma Shipment Validation POC
## Updated High-Level Requirements & Client Demo Flows

---

# 1. POC Objective

The objective of this POC is to validate a shipment received against the **ERP-generated invoice**, validate the physical item/box information, and then verify applicable pharma items against **Tatmin**.

The overall validation process is:

**Invoice → Item/Box Scan → Invoice Validation → Tatmin Validation → Quantity Validation → SSCC Validation → Final Shipment Status**

The POC will demonstrate different combinations of:

- Reported pharma items
- Non-reported pharma items
- SSCC-reported items
- SSCC non-reported items
- Non-pharma items
- Quantity matching
- Partial/repeated scanning
- Manual intervention

---

# 2. Product Categories

## 2.1 Pharma Items

Pharma items contain a **2D barcode** and are validated at item level.

The system should capture/validate information such as:

- GTIN
- Batch Number
- Serial Number
- Quantity
- Invoice Number / shipment reference, where applicable

After invoice validation, the pharma item is checked against the **Tatmin database**.

Tatmin validation should verify:

1. Whether the item is reported in Tatmin.
2. Whether the batch number matches.
3. Whether the relevant serial/item exists.
4. Whether the quantity reported in Tatmin matches/is sufficient against the invoice quantity.

Therefore, **Tatmin validation is not only a reported/not-reported check; quantity must also be validated.**

---

## 2.2 Non-Pharma Items

Non-pharma items do not have the pharma 2D barcode.

For non-pharma items, the primary validation is:

**Invoice Quantity vs Scanned/Detected Quantity**

Example:

> Invoice Quantity = 100  
> Received/Scanned Quantity = 100  
> Result = Quantity Matched

If the quantity does not match, the item should be flagged for exception/manual intervention.

Non-pharma items do **not require Tatmin validation** in the current POC scope.

---

# 3. Core Validation Logic

The system will perform validation in multiple stages.

### Stage 1 – Invoice Validation

The scanned item is matched against the invoice using the relevant information.

For pharma:

**GTIN + Batch Number + Serial Number + Quantity**

For non-pharma:

**Item + Batch/Reference + Quantity**

---

### Stage 2 – Tatmin Validation

Applicable only to pharma items.

The system checks:

**Is the item reported in Tatmin?**

AND

**Does the Tatmin quantity match/satisfy the invoice quantity?**

Example:

| Validation | Expected | Tatmin | Result |
|---|---:|---:|---|
| Item Reported | Yes | Yes | 🟢 |
| Batch | B1 | B1 | 🟢 |
| Quantity | 100 | 100 | 🟢 |

If the item is reported but the quantity does not match:

> 🔴 **Tatmin quantity does not match the invoice quantity. Manual intervention required.**

---

# 4. Quantity Validation

Quantity will be validated at both the **invoice level** and, for pharma items, the **Tatmin level**.

## Example

Invoice:

> Item 1  
> Batch: B1  
> Quantity: 10,000

Physical scan:

> Quantity: 10,000

Tatmin:

> Reported Quantity: 10,000

Result:

**🟢 Fully Matched**

---

### Quantity Mismatch Example

Invoice:

> Quantity = 10,000

Physical scan:

> Quantity = 10,000

Tatmin:

> Quantity = 9,500

Result:

**🔴 Tatmin Quantity Mismatch**

The item should not be considered fully validated until the discrepancy is resolved.

---

# 5. Partial / Multiple Scanning

The system should support multiple scans for the same invoice/batch.

Example:

Invoice:

**10,000 units**

### First Scan

5,000 units received.

System displays:

> Previously Scanned: 0  
> Current Scan: 5,000  
> Total Scanned: 5,000  
> Remaining: 5,000

### Second Scan

Another 5,000 units received.

System displays:

> Previously Scanned: 5,000  
> Current Scan: 5,000  
> Total Scanned: 10,000  
> Remaining: 0  
> Status: 🟢 Quantity Matched

The same cumulative quantity logic should be used when comparing the shipment quantity with Tatmin.

---

# 6. Seven Client Demo Flows

The POC will demonstrate the following **7 predefined invoice scenarios**.

---

## Flow 1 – All Pharma Items Reported

### Invoice 1

| Item | Batch | Category | Tatmin Status |
|---|---|---|---|
| Item 1 | B1 | Pharma | Reported |
| Item 2 | B2 | Pharma | Reported |

### Validation

1. Upload Invoice 1.
2. Scan Item 1.
3. Match Item 1 against invoice.
4. Check Item 1 in Tatmin.
5. Validate Item 1 quantity against invoice and Tatmin.
6. Scan Item 2.
7. Repeat validation.
8. Both items are successfully reported and quantities match.

### Expected Result

🟢 **Shipment Validated**

Message:

> **All pharma items are reported in Tatmin and quantities match the invoice.**

---

# Flow 2 – One Pharma Item Not Reported

### Invoice 2

| Item | Batch | Category | Tatmin Status |
|---|---|---|---|
| Item 1 | B1 | Pharma | Reported |
| Item 2 | B2 | Pharma | Not Reported |

### Validation

Item 1:

- Invoice Match → 🟢
- Tatmin Reported → 🟢
- Quantity Match → 🟢

Item 2:

- Invoice Match → 🟢
- Tatmin Reported → 🔴
- Tatmin Quantity Validation → Cannot be completed/failed

### Expected Result

🔴 **Manual Intervention Required**

Message:

> **Item 2 is not reported in Tatmin for Batch B2. Manual intervention is required.**

If the confirmed business rule is that any unreported pharma item causes the complete shipment to be returned, the shipment should be marked:

**🔴 Shipment Exception / Return**

---

# Flow 3 – Reserved / Additional Scenario

Flow 3 is currently not represented in the provided demo matrix.

This flow should be finalized with the client before implementation.

Potentially, this can be used for:

- Quantity mismatch
- Partial quantity
- Duplicate scan
- Image quality failure
- Tatmin quantity mismatch

The exact scenario should be confirmed before including it in the final POC.

---

# Flow 4 – SSCC Reported

### Invoice 4

| Item | Batch | Category | Tatmin / SSCC Status |
|---|---|---|---|
| Item 1 | B1 | Pharma | Reported |
| Item 2 | B2 | Pharma | Reported |
| Item 3 | B3 | Pharma | SSCC Reported |

### Validation

The system validates:

1. Item 1 against invoice.
2. Item 2 against invoice.
3. Item 3 against invoice.
4. Pharma items against Tatmin.
5. Quantity against invoice.
6. SSCC information.
7. SSCC quantity against expected quantity.

### Expected Result

🟢 **Shipment Validated**

The SSCC is successfully identified/reported and its quantity matches the expected shipment quantity.

---

# Flow 5 – SSCC Not Reported

### Invoice 5

| Item | Batch | Category | Tatmin / SSCC Status |
|---|---|---|---|
| Item 1 | B1 | Pharma | Reported |
| Item 2 | B2 | Pharma | Reported |
| Item 3 | B3 | Pharma | SSCC Not Reported |

### Validation

Item 1:

🟢 Reported + Quantity Matched

Item 2:

🟢 Reported + Quantity Matched

Item 3:

🔴 SSCC Not Reported

### Expected Result

🔴 **Manual Intervention Required**

Message:

> **SSCC for Item 3 / Batch B3 is not reported in Tatmin. Manual intervention is required.**

The exact behavior at shipment level should follow the client's confirmed business rule.

---

# Flow 6 – Mixed Pharma & Non-Pharma Shipment

### Invoice 6

| Item | Batch | Category | Status |
|---|---|---|---|
| Item 1 | B1 | Pharma | Reported |
| Item 2 | B2 | Pharma | Not Reported |
| Item 3 | B3 | Non-Pharma | Quantity Based |

### Validation

### Item 1 – Pharma

- Invoice Match → 🟢
- Tatmin Reported → 🟢
- Tatmin Quantity → Match → 🟢

### Item 2 – Pharma

- Invoice Match → 🟢
- Tatmin Reported → 🔴
- Tatmin Quantity → Failed/Pending

### Item 3 – Non-Pharma

- No Tatmin validation.
- Validate received quantity against invoice quantity.

### Expected Result

🔴 **Shipment Exception / Manual Intervention**

The purpose of this flow is to demonstrate that the system applies **different validation rules based on the product category**.

---

# Flow 7 – Non-Pharma Only

### Invoice 7

| Item | Batch | Category | Validation |
|---|---|---|---|
| Item 1 | B1 | Non-Pharma | Quantity |
| Item 2 | B2 | Non-Pharma | Quantity |

### Validation

For both items:

- Identify item.
- Compare expected invoice quantity.
- Compare scanned/received quantity.
- No Tatmin validation is required.

### Expected Result

If quantities match:

🟢 **Shipment Validated**

If quantities do not match:

🔴 **Quantity Mismatch – Manual Intervention Required**

---

# 7. Client Demo Matrix

The seven scenarios can be presented to the client as follows:

| Flow | Invoice | Item Scenario | Category | Expected Result |
|---|---|---|---|---|
| 1 | Invoice 1 | All items reported | Pharma | 🟢 Validated |
| 2 | Invoice 2 | One item not reported | Pharma | 🔴 Exception |
| 3 | Invoice 3 | To be confirmed | TBD | TBD |
| 4 | Invoice 4 | SSCC reported | Pharma | 🟢 Validated |
| 5 | Invoice 5 | SSCC not reported | Pharma | 🔴 Exception |
| 6 | Invoice 6 | Reported + Non-Reported + Non-Pharma | Mixed | 🔴 Exception |
| 7 | Invoice 7 | Quantity-based validation only | Non-Pharma | 🟢/🔴 Based on quantity |

---

# 8. Tatmin Dummy Database

For the POC, Tatmin will be simulated through a dummy database.

The database should contain item-level records with:

- GTIN
- Batch Number
- Serial Number
- Invoice Number
- Reported Status
- Reported Quantity
- SSCC
- SSCC Reported Status
- Reporting Date

Example:

| GTIN | Batch | Serial | Invoice | Reported | Tatmin Qty | SSCC | SSCC Reported |
|---|---|---|---|---|---:|---|---|
| GTIN001 | B1 | SN001 | INV001 | Yes | 100 | SSCC001 | Yes |
| GTIN002 | B2 | SN002 | INV001 | Yes | 100 | SSCC001 | Yes |
| GTIN003 | B2 | SN003 | INV002 | No | 0 | SSCC002 | No |
| GTIN004 | B3 | SN004 | INV004 | Yes | 500 | SSCC003 | Yes |
| GTIN005 | B3 | SN005 | INV005 | Yes | 500 | SSCC004 | No |

---

# 9. Tatmin Validation Logic

The Tatmin validation should follow this logic:

### Step 1 – Find Item

Search Tatmin using the relevant item identifiers:

**GTIN + Batch + Serial Number**

and invoice/shipment reference where applicable.

↓

### Step 2 – Check Reported Status

**Reported?**

- Yes → Continue
- No → 🔴 Exception

↓

### Step 3 – Check Quantity

Compare:

**Invoice Expected Quantity**

vs.

**Tatmin Reported Quantity**

↓

### Step 4 – Determine Status

### 🟢 Matched

Tatmin item is reported and quantity matches.

### 🟡 Pending

Item is expected to be reported but is not yet available in Tatmin and is within the agreed reporting timeframe.

### 🔴 Failed

Item is not reported after the allowed timeframe or Tatmin quantity does not satisfy the invoice requirement.

---

# 10. SSCC Validation

SSCC represents the packaging/shipment hierarchy.

For example, if there are **12,000 items**:

- SSCC 001 → 10,000 items
- SSCC 002 → 1,000 items
- SSCC 003 → 1,000 items
- Master SSCC → contains the above SSCCs

The system should validate:

- SSCC exists.
- SSCC is reported where applicable.
- SSCC belongs to the correct shipment.
- SSCC quantity is correct.
- Child SSCC quantities add up correctly.
- Master SSCC quantity matches the total expected quantity.

---

# 11. Image Validation

Before item data is extracted, the system should validate the image quality.

If the image is unclear:

> 🔴 **The uploaded image is not clear enough to validate the item. Please retake or re-upload the image.**

If the user chooses to proceed despite the warning:

> **Manual Intervention Required**

This prevents potentially incorrect OCR/barcode extraction from being automatically accepted.

---

# 12. Final Shipment Status

The final shipment status should be determined based on all applicable validations.

### 🟢 Validated

- Invoice matched
- Quantity matched
- Pharma items reported in Tatmin
- Tatmin quantity matched
- SSCC validated
- No critical exceptions

### 🟡 Pending

- Additional quantity is yet to be scanned
- Tatmin reporting is pending
- Additional validation is required

### 🔴 Manual Intervention Required

Examples:

- Invoice mismatch
- Batch mismatch
- Quantity mismatch
- Tatmin item not reported
- Tatmin quantity mismatch
- SSCC not reported
- SSCC quantity mismatch
- Invalid image
- Invalid barcode
- Duplicate scan

---

# 13. End-to-End POC Flow

The complete POC flow is:

**ERP generates Invoice**

↓

**User uploads Invoice**

↓

**System extracts Invoice Data**

↓

**Expected Item List Created**

↓

**User scans item/box**

↓

**Image Quality Validation**

↓

**Barcode / Item Data Extraction**

↓

**Invoice vs Scanned Data Validation**

↓

### Pharma?

**YES**

↓

**Tatmin Item Validation**

↓

**Tatmin Reported?**

- NO → 🔴 Exception / Pending
- YES → Continue

↓

**Tatmin Quantity vs Invoice Quantity**

↓

**Quantity Matched?**

- NO → 🔴 Exception
- YES → Continue

↓

**SSCC Validation**

↓

**Final Shipment Decision**

---

### If Non-Pharma

**Invoice vs Scanned Quantity**

↓

**Quantity Matched?**

- YES → Continue
- NO → 🔴 Exception

↓

**SSCC Validation where applicable**

↓

**Final Shipment Decision**

---

# 14. Recommended POC Dashboard

The main dashboard should provide a consolidated view such as:

### Invoice: INV-0006

**Total Items:** 3  
**Pharma:** 2  
**Non-Pharma:** 1

| Item | Category | Invoice | Tatmin | Quantity | Status |
|---|---|---|---|---|---|
| Item 1 | Pharma | 🟢 Match | 🟢 Reported | 🟢 Match | 🟢 |
| Item 2 | Pharma | 🟢 Match | 🔴 Not Reported | 🔴 Failed | 🔴 |
| Item 3 | Non-Pharma | 🟢 Match | N/A | 🟢 Match | 🟢 |

### Overall Status

🔴 **Manual Intervention Required**

Reason:

> **Item 2 is not reported in Tatmin.**

---

# 15. Key Business Rules for Client Confirmation

Before finalizing the POC, the following should be confirmed:

1. Whether Tatmin quantity must be **exactly equal** to invoice quantity or only **greater than/equal to** the required quantity.
2. Whether Tatmin matching requires **GTIN + Batch + Serial Number + Invoice Number** or a different combination.
3. Whether an unreported pharma item causes the **entire shipment to be returned**.
4. Whether an SSCC not reported in Tatmin causes the complete shipment to fail.
5. Exact Tatmin reporting timeframe — currently assumed to be **1–2 days**.
6. Exact rules for partial/repeated scans.
7. Whether SSCC is generated by the POC or received from another system.
8. Exact quantity validation rules for non-pharma items.
9. What should happen when physical quantity, invoice quantity and Tatmin quantity are all different.
10. What scenario should be demonstrated as **Flow 3**, since it is currently not defined in the provided demo matrix.

---

# 16. POC Scope Summary

The POC will demonstrate:

**Invoice Upload**

→ **Invoice Item Extraction**

→ **Pharma / Non-Pharma Identification**

→ **Image & Barcode Validation**

→ **Invoice Matching**

→ **Quantity Reconciliation**

→ **Tatmin Reported Validation**

→ **Tatmin Quantity Validation**

→ **SSCC Validation**

→ **Exception Detection**

→ **Manual Intervention**

→ **Final Shipment Status**

The key principle of the POC is:

> **The invoice defines what is expected, the physical scan defines what has been received, and Tatmin confirms whether the applicable pharma items are reported and whether their quantity satisfies the invoice requirement. Non-pharma items are validated primarily through quantity reconciliation.**