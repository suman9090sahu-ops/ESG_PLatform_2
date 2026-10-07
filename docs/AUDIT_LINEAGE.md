# ESG DATA AUDIT & EVIDENCE LINEAGE ARCHITECTURE

The MEIL ESG Control Tower establishes end-to-end, tamper-evident audit lineage connecting high-level BRSR disclosures down to raw operational physical evidence.

```text
===================================================================================
                         MEIL ESG DATA LINEAGE CHAIN
===================================================================================

[1] PHYSICAL SOURCE DOCUMENT
    (e.g., IOCL Tax Invoice #IOCL-2025-0914, Electricity Utility Bill #BESCOM-883)
                                 │
                                 ▼
[2] SECURE EVIDENCE ATTACHMENT (Phase 09)
    - File: evidence/SITE-POL-101/FY25-26-Q1/rec_7/a1b2c3d4e5f6_iocl_invoice.pdf
    - SHA-256 Checksum: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
    - Taxonomy: INVOICE / UTILITY_BILL / METER_READING / FUEL_CHALLAN / ...
    - Audit Status: ACTIVE / RETIRED (with cryptographic hash preservation)
                                 │
                                 ▼
[3] OPERATIONAL ACTIVITY RECORD (Phase 08)
    - ID: #7
    - Operational Site: Polavaram Dam Headworks Site (SITE-POL-101)
    - Activity Definition: High-Speed Diesel (HSD) Stationary Combustion
    - Telemetry: 450.5000 Litres on 2025-06-15
    - Workflow State: DRAFT ➔ READY ➔ SUBMITTED ➔ VERIFIED ➔ APPROVED
                                 │
                                 ▼
[4] AUTOMATED OCR EXTRACTION & VALIDATION (Phases 10 & 11)
    - Extracted Invoice Quantity: 450.50 L
    - Invoice Date: 2025-06-15
    - Tolerance Matching & Business Rule Validations
                                 │
                                 ▼
[5] EMISSION CALCULATIONS & METHODOLOGY (Phase 12)
    - Activity × Emission Factor = Calculated GHG Emissions (Scope 1 / Scope 2 / Scope 3)
    - 450.50 L × 2.68 kg CO2e/L = 1,207.34 kg CO2e (1.207 tCO2e)
                                 │
                                 ▼
[6] ENTERPRISE CONSOLIDATION & BRSR DISCLOSURE (Phases 13 & 14)
    - SEBI BRSR Principle 6: Essential Indicator 1 (Total Energy & Scope 1 Emissions)
                                 │
                                 ▼
[7] "TRACE THIS NUMBER" AUDIT RECONSTRUCTION
    - Auditor selects BRSR Metric ➔ Identifies Contributing Calculations ➔
      Pins Contributory Activity Records ➔ Downloads Cryptographically Verified Original Evidence
===================================================================================
```

---

## 1. Traceability Invariants

1. **One-Way Operational Immutability**:
   Once an `ActivityRecord` is promoted to `SUBMITTED`, `VERIFIED`, or `APPROVED`, both the record and its attached `Evidence` are locked against destructive modifications.
2. **Cryptographic Checksums**:
   Every evidence file computes a SHA-256 checksum during upload streaming. Any downstream modification of the physical file or storage corruption can be immediately detected.
3. **Audit Trail Logging**:
   Every lifecycle transition, upload, binary download, and retirement is permanently logged into `AuthAuditLog` with actor user ID, role, client IP address, and resource URI.
4. **Non-Destructive Retirement**:
   Erroneous or superseded documents are transitioned to `RETIRED` with an audit justification rather than being silently purged, maintaining full traceability for statutory and regulatory audits.
