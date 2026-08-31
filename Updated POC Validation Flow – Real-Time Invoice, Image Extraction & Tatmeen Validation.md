# Updated POC Validation Flow – Real-Time Invoice, Image Extraction & Tatmeen Validation

Update the existing POC flow to implement a **realistic end-to-end validation process** using actual data extraction and matching logic instead of predefined/hardcoded validation results.

The objective is to demonstrate how invoice data is received from SAP, how invoice data is extracted, how physical box/item images are scanned, how both datasets are matched, and finally how the items are validated against Tatmeen.

---

## Step 1: Invoice Data from SAP

When the user starts the validation process, first display an **"Invoices from SAP"** section.

For the POC:

- Show a few dummy/sample invoices as if they have been received from SAP.
- Clearly indicate that these invoices are **"Fetched from SAP"**.
- Display basic information such as:
  - Invoice Number
  - Invoice Date
  - Supplier
  - Number of Items
  - Total Quantity
  - Status
- Allow the user to select an invoice.

I will provide actual sample invoices later, so the dummy invoices should be stored/configured in a way that they can easily be replaced with the new invoice data without changing the UI or business logic.

### Important

Do not build an actual SAP integration for this POC.

Create a clean abstraction such as:

`SAP Data Source → Invoice Data`

so that an actual SAP API can be connected later without changing the rest of the application.

---

## Step 2: Manual Invoice Upload

Along with the SAP invoice section, provide another section:

### "Upload Invoice"

Allow the user to upload an invoice from their computer.

Supported formats can include:

- PDF
- JPG/JPEG
- PNG

After uploading the invoice:

1. Process the uploaded document.
2. Extract the invoice information using OCR/document extraction.
3. Display an extraction progress/loading state.
4. Show the extracted information to the user.
5. Allow the user to review the extracted data before proceeding.

The extraction must be based on the **actual uploaded invoice**, not predefined data.

---

## Step 3: Invoice Data Extraction

Extract all relevant information available from the invoice.

For every item/product, try to identify:

- Item Name
- GTIN
- Serial Number
- Batch Number
- Quantity
- SKU/Product Code
- Expiry Date
- Manufacturer
- Product Description
- Any other relevant product information available on the invoice

Also extract invoice-level information such as:

- Invoice Number
- Invoice Date
- Supplier
- Customer
- Total Quantity
- Other relevant metadata

### Data Storage

After extraction, normalize the information and save it into the local database.

Create a structured data model so that invoice data can later be compared against scanned box/item data.

For example:

`Invoice`

→ Invoice Items

→ GTIN  
→ Serial Number  
→ Batch Number  
→ Quantity  
→ Item Name  
→ Expiry Date  
→ Other Metadata

Do not assume that every field will always be present. The extraction logic should gracefully handle missing fields.

---

# Step 4: Proceed to Physical Box/Item Scanning

Once the invoice has been successfully extracted and saved, the user clicks:

**"Continue to Scan"**

Open a dedicated **Scanner / Box Validation** screen.

The experience should feel similar to a modern mobile/payment scanner interface, with:

- Camera/scanner area
- Scanning frame
- Instructions
- Scan status
- Captured item information
- Option to upload an image

### Upload Image Option

Inside the scanner screen, provide:

**"Upload Image"**

This should allow the user to select an image from their computer instead of using the camera.

The UI should feel similar to the experience users are familiar with when a payment application opens a scanner and also provides an option to select an image from the device.

For the desktop POC, the upload option can be the primary method while the scanner interface visually represents the real-world scanning experience.

---

# Step 5: Extract Data from Box/Item Image

When an image is uploaded:

1. Analyze the image using OCR/computer vision.
2. Detect all visible products/items.
3. Extract the available information from each item.

For each detected item, extract as much information as possible:

- Item Name
- GTIN
- Serial Number
- Batch Number
- Quantity
- Expiry Date
- Product Code
- Manufacturer
- Barcode information
- SSCC, if available
- Any other identifiable information

The system should also determine:

### Item Count

Calculate how many units of each item are present in the image.

For example:

| Item | GTIN | Serial/Batch | Detected Quantity |
|---|---|---|---:|
| Product A | 089xxxx | B001 | 5 |
| Product B | 089yyyy | B002 | 3 |

The final detected dataset should be stored separately from the invoice dataset.

---

# Step 6: Intelligent Matching Engine

Once the invoice data and image data are available, automatically start the **Matching & Validation Engine**.

Do not hardcode the result.

The system should compare the two datasets dynamically.

### Matching Criteria

Compare wherever the information is available:

1. Item Name
2. GTIN
3. Serial Number
4. Batch Number
5. Quantity
6. Expiry Date
7. Product Code
8. SSCC
9. Other relevant identifiers

The system should determine the status of each individual field.

For example:

| Validation Criteria | Invoice | Scanned Image | Result |
|---|---|---|---|
| Item Name | Product A | Product A | ✓ Matched |
| GTIN | 089123 | 089123 | ✓ Matched |
| Batch | B001 | B001 | ✓ Matched |
| Quantity | 5 | 5 | ✓ Matched |
| Serial Number | SN001 | SN001 | ✓ Matched |

If something does not match:

| Validation Criteria | Invoice | Scanned Image | Result |
|---|---|---|---|
| Quantity | 5 | 4 | ⚠ Mismatch |

Clearly highlight mismatched fields.

---

# Step 7: Discrepancy Handling

If any mismatch is detected, do not mark the validation as successful.

Create a clear **"Discrepancies Found"** section.

Display:

- Item affected
- Field that failed
- Expected value
- Detected value
- Reason for failure
- Recommended action

Example:

**Quantity Mismatch**

Expected: `5`  
Detected: `4`

**Status: Human Intervention Required**

The system should flag the item for manual review.

Provide an option such as:

**"Review & Resolve"**

The user should be able to review the discrepancy and, where appropriate for the POC, manually resolve/override it with a reason.

All overrides should be recorded in the validation result.

---

# Step 8: Tatmeen Validation

Only after the invoice and physical item/box data successfully pass the required matching rules should the system proceed to Tatmeen validation.

Display:

**"Validate with Tatmeen"**

When clicked, validate each applicable pharma item against the Tatmeen dataset/API.

For the POC, if an actual Tatmeen API is not available, create a **Tatmeen Service Adapter** with realistic mock data.

The application should behave as if it is communicating with Tatmeen.

Do not hardcode the final UI result.

Instead:

`Matched Invoice Data`

→ `Matched Physical Item Data`

→ `Tatmeen Validation`

→ `Final Status`

---

# Step 9: Tatmeen Result

For every pharma item, display the Tatmeen validation result individually.

Possible statuses:

### Reported on Tatmeen

The item exists in Tatmeen and the required information matches.

### Not Reported on Tatmeen

The item could not be found in Tatmeen or the required information does not match.

### Tatmeen Validation Failed

The system could not complete the validation.

### Human Intervention Required

The item has a discrepancy that requires manual review.

For example:

| Item | Invoice Match | Image Match | Tatmeen | Final Status |
|---|---|---|---|---|
| Item 1 | ✓ | ✓ | Reported | ✓ Validated |
| Item 2 | ✓ | ✓ | Not Reported | ⚠ Exception |
| Item 3 | ✓ | ✗ | Not Checked | 🔴 Human Intervention |

---

# Step 10: Non-Pharma Validation

Non-pharma items should not be forced through Tatmeen validation.

For non-pharma items, validate based on the applicable business rules.

For example:

**Quantity Validation**

Invoice Quantity = 10  
Detected Quantity = 10

Result:

**✓ Quantity Matched**

If:

Invoice Quantity = 10  
Detected Quantity = 8

Result:

**⚠ Quantity Mismatch – Human Intervention Required**

---

# Step 11: Final Validation Summary

After all validations are complete, display a final summary.

Include:

### Invoice Summary

- Invoice Number
- Total Items
- Total Quantity

### Physical Scan Summary

- Items Detected
- Total Quantity Detected

### Matching Summary

- Matched Items
- Mismatched Items
- Missing Items
- Extra Items

### Tatmeen Summary

- Reported Items
- Not Reported Items
- Failed Validations

### Final Result

Possible overall statuses:

**✓ Validation Successful**

or

**⚠ Validation Completed with Exceptions**

or

**🔴 Human Intervention Required**

---

# Important Business Logic

The application must NOT simply show:

> "Validation Successful"

because the predefined flow says that the item is valid.

Instead, every result must be generated dynamically from:

**Invoice → Extracted Data → Database**

+

**Box/Image → Extracted Data → Database**

↓

**Matching Algorithm**

↓

**Discrepancy Detection**

↓

**Tatmeen Validation**

↓

**Final Result**

This is the most important change in the POC.

---

# Data Architecture

Keep three separate datasets:

### 1. SAP/Invoice Dataset

Represents the expected shipment information.

### 2. Physical Scan Dataset

Represents what was actually detected from the box/item image.

### 3. Tatmeen Dataset

Represents the product information available/reported in Tatmeen.

The matching engine should compare these datasets rather than using predefined validation outcomes.

---

# POC Implementation Constraint

This is a client demonstration POC, so keep the implementation lightweight.

Do not implement actual:

- SAP integration
- Tatmeen API integration
- External enterprise integrations

Instead:

- Use realistic sample SAP data.
- Use actual invoice upload and extraction.
- Use actual image upload and extraction.
- Use a local lightweight database.
- Use a mock Tatmeen dataset/service.
- Keep the architecture ready for real APIs later.

If an external AI/OCR API is unavailable, the system must gracefully fall back to realistic mock extraction data without breaking the workflow.

---

# Final End-to-End Flow

The final user journey should be:

**Start Validation**

↓

**Select Invoice from SAP OR Upload Invoice**

↓

**Extract Invoice Data**

↓

**Review & Save Invoice Data**

↓

**Continue to Scan**

↓

**Open Scanner**

↓

**Scan Box / Upload Image**

↓

**Extract Item Data**

↓

**Identify Items + Quantities + GTIN + Serial/Batch + SSCC**

↓

**Save Physical Scan Data**

↓

**Run Matching Algorithm**

↓

**Compare Invoice vs Physical Items**

↓

**Display Field-Level Matching Results**

↓

**If Mismatch → Flag for Human Intervention**

↓

**If Valid → Validate with Tatmeen**

↓

**Check Pharma Items Against Tatmeen**

↓

**Validate Non-Pharma Items Using Quantity/Applicable Rules**

↓

**Show Item-Level Results**

↓

**Show Final Validation Summary**

This flow should be implemented consistently across all POC scenarios so that the client can clearly see that the system is performing **actual document/image data extraction, intelligent matching, discrepancy detection, and Tatmeen validation**, rather than displaying predefined validation results.