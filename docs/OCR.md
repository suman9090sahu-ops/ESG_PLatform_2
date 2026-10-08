# MEIL ESG CONTROL TOWER — Phase 11 OCR Engine & Document Intelligence

## 1. Executive Summary

Phase 11 introduces the **OCR and Document-Data Extraction Foundation** to the MEIL ESG Control Tower Django monolith. The system processes uploaded ESG evidence files (such as utility electricity invoices, fuel consumption receipts, and weighbridge slips) and extracts structured intelligence and raw text for automated telemetry comparison and audit scrutiny.

---

## 2. Core Domain Principle: Unverified Document Intelligence

```text
Original Evidence Document (PDF / Images)
                ↓
    OCR Processing Engine
                ↓
      Raw Extracted Text
                ↓
   Structured Extracted Fields (Invoice #, Date, Quantity, Unit, Amount)
                ↓
  Operational Telemetry Comparison (MATCH / MISMATCH)
                ↓
  Human & Compliance Workflow Review (Phase 12+)
                ↓
    Authoritative Verified ESG Data
```

### Critical Rules
1. **Never Auto-Overwrite Operational Telemetry**: OCR output is strictly **UNVERIFIED DOCUMENT INTEL**. It never silently alters or mutates authoritative `ActivityRecord` telemetry (`quantity`, `unit`, `measurement_date`, `status`).
2. **Deterministic Comparison**: Differences between document data and telemetry are flagged as telemetry signals (`MATCH` / `MISMATCH`), providing objective evidence for validation and review without modifying data.
3. **Preservation of Document Immutability**: The original evidence file and its SHA-256 cryptographic checksum are never altered or replaced by OCR operations.

---

## 3. Supported Document Types & Processing Paths

| Document Format | Extension | Primary Engine | Processing Strategy |
| :--- | :--- | :--- | :--- |
| **PDF (Digital / Text)** | `.pdf` | `PyPDFTextProvider` (`pypdf`) | Native stream text extraction, page-aware text chunking. |
| **PDF (Scanned)** | `.pdf` | `TesseractOCRProvider` (`pytesseract`) | Optical character recognition per page (requires Tesseract binary). |
| **Image (PNG / JPEG)** | `.png`, `.jpg`, `.jpeg` | `TesseractOCRProvider` (`pytesseract` + `Pillow`) | Image OCR preprocessing & optical recognition. |
| **Other Formats** | `.xlsx`, `.docx`, `.csv` | N/A | Deferred to future tabular parsers. Cleanly rejected with `UnsupportedDocumentTypeError`. |

---

## 4. OCR Provider Abstraction

The processing layer uses a clean decoupled provider abstraction (`apps/core/ocr_services.py`):

```text
                  BaseOCRProvider
                         ▲
         ┌───────────────┼───────────────┐
         │                               │
 PyPDFTextProvider             TesseractOCRProvider          MockOCRProvider
  (Native PDF streams)         (System OCR engine)         (Unit tests & mock runs)
```

- **`OCR_DEFAULT_PROVIDER`**: Configured via Django settings (`"pypdf"`, `"tesseract"`, or `"mock"`).
- **Graceful Failure Handling**: If system OCR binaries (e.g. `tesseract.exe`) are missing, the system reports `OCREngineUnavailableError` and records status `FAILED` in the database, with a clear user error message. It **never** fakes OCR results.

---

## 5. Multi-Run Versioning & Immutability

OCR output can change when documents are rescanned, engines upgraded, or parameters adjusted. To maintain audit compliance, the platform preserves historical OCR runs:

```text
Evidence Document #7
   ├── Run #1 (FAILED: Corrupted stream) ── [Archived]
   ├── Run #2 (COMPLETED: pypdf, 95% confidence) ── [Archived]
   └── Run #3 (COMPLETED: pytesseract, 98% confidence) ── [Latest Active]
```

- **`OCRRun`**:
  - `run_number`: Sequentially incremented integer per Evidence document (`1, 2, 3...`).
  - `is_latest`: Boolean flag indexed for O(1) retrieval of current intel.
  - `UniqueConstraint(fields=['evidence', 'run_number'])`: Enforces monotonic uniqueness.
  - `page_data`: JSON array capturing page-by-page text extracts.
- **`OCRField`**:
  - Structured fields extracted per run (`field_name`, `raw_value`, `normalized_value`, `unit`, `confidence`, `page_number`).
  - Distinguishes raw document text (e.g., `"1,250.00 kWh"`) from normalized values (`"1250.00"`).

---

## 6. Structured Field Extraction & Normalization

The service layer extracts domain-specific entities using robust regex heuristics and normalizers:

| Entity Field | Regex Matching Patterns | Normalization Output |
| :--- | :--- | :--- |
| `invoice_number` | `Invoice\s*(?:No|Number|#)?[:\s-]*([A-Z0-9\-\/]{4,30})` | Uppercase trimmed string |
| `quantity` | `(?:Units|Quantity|Consumed|Qty)[:\s-]*([0-9,]+(?:\.[0-9]+)?)` | Float string (commas stripped) |
| `unit` | `(?:kWh|Units|Litres|Liters|L|MT|Tonnes|kg)` | Standardized unit code |
| `billing_date` | `(?:Invoice\s*Date|Bill\s*Date)[:\s-]*([0-9]{4}-[0-9]{2}-[0-9]{2})` | ISO date (`YYYY-MM-DD`) |
| `billing_period` | `(?:Billing\s*Period|Bill\s*Month)[:\s-]*([A-Za-z0-9\s,\-]+)` | Clean trimmed string |
| `total_amount` | `(?:Total\s*Amount|Grand\s*Total|Net\s*Amount)[:\s-]*(?:INR|Rs\.?|USD)?\s*([0-9,]+(?:\.[0-9]+)?)` | Decimal amount string |
| `vendor` | `(?:Supplier|Vendor|Billed\s*By)[:\s-]*([A-Za-z0-9\s,\.\-&]{3,80})` | Clean vendor name |
| `meter_number` | `(?:Meter\s*No|Consumer\s*No)[:\s-]*([A-Za-z0-9\-\/]{4,30})` | Meter/Consumer identifier |

---

## 7. Operational Telemetry Comparison Engine

`compare_ocr_with_activity_record(ocr_run, record)` evaluates the extracted entities against the parent `ActivityRecord`:

1. **Quantity Comparison**: Evaluates absolute delta and percentage delta. Match if delta percentage < 0.5%.
2. **Unit of Measure Comparison**: Case-insensitive comparison against `record.unit.code` and `record.unit.name`.
3. **Date Comparison**: Compares ISO date strings between document invoice date and telemetry `measurement_date`.
4. **Reference Comparison**: Compares invoice number against `record.reference_number` or notes.
5. **Overall Status**: Returns `MATCH` (all detected items match), `MISMATCH` (at least one detected item diverges), or `NO_DATA` (no comparable entities extracted).

---

## 8. Role-Based Access Control (RBAC) & Anti-IDOR

| Role | View OCR Intel & Runs | Execute OCR Run | Reprocess / Retry Run |
| :--- | :--- | :--- | :--- |
| `SITE_MANAGER` | Scoped to assigned sites | Permitted for assigned sites | Permitted for assigned sites |
| `SUBSIDIARY_MANAGER` | Scoped to child division sites | Permitted for child division sites | Permitted for child division sites |
| `MEIL_OPERATOR` | Enterprise-wide | Permitted enterprise-wide | Permitted enterprise-wide |
| `ESG_MANAGER` | Enterprise-wide | Permitted enterprise-wide | Permitted enterprise-wide |
| `AUDITOR` | Enterprise-wide (Read-Only) | **403 Forbidden** | **403 Forbidden** |

---

## 9. API & HTTP Routes

| Method | URL Route | Handler View | Access Control |
| :--- | :--- | :--- | :--- |
| `POST` | `/evidence/<id>/ocr/process/` | `ocr_process_view` | Scoped managers / operators. Dual AJAX JSON and HTTP redirect support. |
| `GET` | `/evidence/<id>/ocr/status/` | `ocr_status_api_view` | Scoped users. Returns run telemetry status JSON. |
| `GET` | `/evidence/<id>/ocr/runs/<run_id>/` | `ocr_run_detail_view` | Scoped users & Auditors. Dedicated Run Audit Ledger. |
| `POST` | `/evidence/<id>/ocr/runs/<run_id>/retry/` | `ocr_run_retry_view` | Scoped managers / operators. Increments run number. |

---

## 10. Audit Lineage & Security Logging

Every OCR lifecycle transition writes to `AuthAuditLog`:
- `OCR_REQUESTED`: Triggered by user request.
- `OCR_STARTED`: Processing begun with engine specs.
- `OCR_COMPLETED`: Successfully extracted text and entities.
- `OCR_FAILED`: Execution error captured with sanitized user-facing message.
- `OCR_RETRIED`: Reprocess action dispatched.

---

## 11. Verification & Test Coverage

- **Automated Unit & Integration Tests**: 24 tests in `tests/test_phase11_ocr_engine.py` (100% PASS).
- **Full Monolithic Regression Suite**: 299 tests across Phases 01–11 passed with 0 failures and 0 errors (`manage.py test`).
- **Live HTTP Workflow Suite**: 10-step end-to-end verification via `tests/verify_phase11_live.py` (100% PASS).
