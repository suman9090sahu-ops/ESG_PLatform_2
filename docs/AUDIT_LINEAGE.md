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

---

## 2. Phase 12 Formal Submission & Snapshot Lineage

When a Site Manager formally submits an `ActivityRecord`, the platform captures an authoritative point-in-time state:

```text
[ActivityRecord #X] (status: READY)
          │
          ▼
   [submit_activity_record]
          │
          ├─► [Submission #1 Created]
          │     - submission_number: 1
          │     - status: SUBMITTED
          │     - is_current: True
          │     - submitted_by: sm_user
          │     - submitted_at: ISO-8601 timestamp
          │     - snapshot_data: {
          │         "record_id": X,
          │         "quantity": "5000.0000",
          │         "unit_code": "KL",
          │         "measurement_date": "2026-10-01",
          │         "evidence_files": [{"id": 1, "sha256": "...", "filename": "..."}]
          │       }
          │
          ├─► [ActivityRecord status: SUBMITTED] (Telemetry editing locked)
          │
          └─► [AuthAuditLog: SUBMISSION_CREATED]
```

---

## 3. Phase 13 Subsidiary Review Decisions Lineage

Subsidiary Manager review decisions generate immutable `SubmissionReview` audit records:

```text
[Submission #1] (status: SUBMITTED)
          │
          ▼
   [Review Actions]
          ├──► VERIFY ──────────► [SubmissionReview: VERIFY] ➔ Submission & Record: VERIFIED
          ├──► EXPLAIN ─────────► [SubmissionReview: EXPLAIN] ➔ Submission: EXPLAINED (operating context recorded)
          ├──► ESCALATE ────────► [SubmissionReview: ESCALATE] ➔ Submission: ESCALATED (routed to ESG_MANAGER)
          └──► REQUEST_CORRECTION ➔ [SubmissionReview: REQUEST_CORRECTION]
                                    - Reason: structured text
                                    - Required Changes: structured text
                                    - Affected Area: ACTIVITY_DATA / EVIDENCE / BOTH / OTHER
                                    - Submission: CORRECTION_REQUESTED, Record: REJECTED
```

---

## 4. Phase 14 Correction, Revision Ledger & Resubmission Iteration Lineage

Phase 14 strictly enforces that **no correction overwrites historical records**. Instead, it generates a cryptographically traceable revision chain:

```text
[Submission #1: CORRECTION_REQUESTED]
          │
          ├─► [CorrectionRequest Created] (status: OPEN)
          │     - requester: sub_mgr
          │     - reason: "Tax invoice indicates 5,250 kL rather than 5,000 kL"
          │     - affected_area: ACTIVITY_DATA
          │
          ├─► [ActivityRevision #1 Preserved] (Baseline Snapshot)
          │     - revision_number: 1
          │     - quantity: 5000.0000 kL
          │     - reason: "INITIAL_BASELINE_SNAPSHOT"
          │     - is_baseline: True
          │
          ▼
   [Site Manager Corrections]
          ├─► Status: OPEN ➔ IN_PROGRESS
          ├─► Operational Data Updated (quantity: 5250.0000 kL)
          ├─► Site Manager Explanatory Notes Attached
          ├─► Mandatory Phase 10 Validation Re-evaluated (Run #2: VALID)
          └─► Status: READY_FOR_RESUBMISSION
          │
          ▼
   [Authoritative Resubmission Execution]
          ├─► Field-by-field JSON deltas computed:
          │     changed_fields: {
          │       "quantity": {"old": "5000.0000", "new": "5250.0000", "delta": "+250.000000"}
          │     }
          ├─► [ActivityRevision #2 Created] (author: sm_user, changed_fields: recorded)
          ├─► [Submission #2 Created]
          │     - submission_number: 2
          │     - parent_submission: Submission #1 (unbroken FK chain)
          │     - is_resubmission: True
          │     - is_current: True (Submission #1 is_current: False)
          ├─► [CorrectionRequest Resolved]
          │     - status: RESOLVED
          │     - resolved_by: sm_user
          │     - resubmission: Submission #2
          └─► [ActivityRecord status: SUBMITTED]
          │
          ▼
[Subsidiary Manager Re-Review]
          ├─► Inspects Comparative Delta Ledger (Original: 5,000 kL vs Corrected: 5,250 kL, Delta: +250 kL)
          ├─► Inspects Chronological Submission & Review Timeline
          └─► VERIFY Decision ➔ Submission #2: VERIFIED, Record: VERIFIED

===================================================================================
                   COMPLETE RECONSTRUCTION CHAIN (AUDIT-READY)
===================================================================================
Submission #1 (5,000 kL) ──► Review #1 (Correction Requested)
       │
       ▼
ActivityRevision #1 (Baseline) ──► ActivityRevision #2 (Delta: +250 kL)
       │
       ▼
Submission #2 (5,250 kL, Parent: #1) ──► Review #2 (VERIFIED) ──► ESG Reporting
===================================================================================
```

---

## 5. Authoritative AuthAuditLog Event Types

The platform records strict security and governance events in `AuthAuditLog`:

| Event Type | Trigger | Key Logged Attributes |
| :--- | :--- | :--- |
| `SUBMISSION_CREATED` | Site Manager submits record | Submission ID, Record ID, Site, Period, Snapshot Hash |
| `SUBMISSION_WITHDRAWN` | Site Manager recalls submission | Submission ID, Record ID, Reason |
| `SUBMISSION_VERIFIED` | Subsidiary Manager verifies submission | Submission ID, Review ID, Reviewer, Site |
| `SUBMISSION_CORRECTION_REQUESTED` | Subsidiary Manager requests correction | Submission ID, Reason, Affected Area |
| `SUBMISSION_EXPLAINED` | Subsidiary Manager attaches explanation | Submission ID, Explanation notes |
| `SUBMISSION_ESCALATED` | Subsidiary Manager escalates to ESG Manager | Submission ID, Target Role |
| `CORRECTION_STARTED` | Site Manager opens/initiates correction | CorrectionRequest ID, Record ID |
| `CORRECTION_UPDATED` | Site Manager updates telemetry/evidence | CorrectionRequest ID, New Quantity, Validation Status |
| `CORRECTION_RESOLVED` | Correction resolved upon resubmission | CorrectionRequest ID, Resolving user, Submission #2 |
| `RESUBMISSION_CREATED` | New versioned submission created | Submission #2, Parent Submission #1, Revision #2 |
| `ANOMALY_DETECTED` | Anomaly engine flags unusual pattern | AnomalyRecord ID, Rule Code, Severity, Observed, Baseline, Delta |
| `ANOMALY_ACKNOWLEDGED` | Reviewer formally notes open anomaly | AnomalyRecord ID, User, Notes |
| `ANOMALY_EXPLAINED` | Reviewer records operational justification | AnomalyRecord ID, Operational Context Explanation |
| `ANOMALY_DISMISSED` | Reviewer formally dismisses false positive | AnomalyRecord ID, Justification Reason |
| `ANOMALY_RESOLVED` | Reviewer marks resolved post-correction | AnomalyRecord ID, Resolution Notes, Related Submission/Revision |
| `ANOMALY_RULE_CREATED` | New deterministic anomaly rule authored | Rule Code, Category, Threshold, Author |
| `ANOMALY_RULE_UPDATED` | Anomaly rule threshold/state modified | Rule Code, New Version, New Threshold, Modifier |
| `ANOMALY_DETECTION_RUN` | Batch anomaly evaluation executed | Run ID, Scope, Evaluated Count, Flagged Count, Duration |
| `SUPPLIER_CREATED` | Vendor/supplier registered | Supplier ID, Code, Legal Name, Company, User |
| `SUPPLIER_UPDATED` | Vendor details or ESG notes modified | Supplier ID, Code, Updated fields, User |
| `SUPPLIER_ARCHIVED` | Vendor soft-archived | Supplier ID, Code, User |
| `PROCUREMENT_CREATED` | Commercial purchase order/record logged | Procurement ID, Number, Supplier, Site, Period, Total Amount, Currency |
| `PROCUREMENT_UPDATED` | Procurement details or line items modified | Procurement ID, Number, Updated fields, User |
| `PROCUREMENT_DELETED` | Draft procurement record deleted | Procurement ID, Number, User |
| `PROCUREMENT_SUBMITTED` | Procurement formally submitted for review | Procurement ID, Number, Submitted by, Lock state |
| `PROCUREMENT_VERIFIED` | Subsidiary manager verifies procurement | Procurement ID, Number, Reviewer, Site |
| `PROCUREMENT_CORRECTION_REQUESTED` | Reviewer requests correction | Procurement ID, Number, Reason, Notes |
| `PROCUREMENT_RESUBMITTED` | Remediated procurement resubmitted | Procurement ID, Number, Resubmitted by |
| `PROCUREMENT_REJECTED` | Procurement rejected by manager | Procurement ID, Number, Reject reason |
| `PROCUREMENT_CANCELLED` | Procurement cancelled | Procurement ID, Number, Cancel reason |
| `PROCUREMENT_VALIDATED` | Deterministic procurement validation run | Procurement ID, Status, Errors, Warnings |
| `PROCUREMENT_ANOMALY_DETECTED` | Procurement anomaly flagged | Procurement ID, Anomaly Code, Variance, Details |

---

## 6. Phase 15 Operational Anomaly Detection & Review Decisions Lineage

Phase 15 integrates deterministic anomaly evaluation as an explainable risk indicator alongside formal validation and review workflows:

```text
[ActivityRecord #X] (Telemetry: 12,000 Litres)
          │
          ├─► [Validation Engine (Phase 10)] ──► Status: VALID
          │
          ▼
   [Anomaly Detection Engine (Phase 15)]
   (Triggered during Submission, Resubmission, or Batch Sweep)
          │
          ├─► Identifies Rule: DIESEL_SPIKE (Threshold: +100%)
          ├─► Historical Baseline Computed: 5,000 Litres (Rolling 12-month average)
          ├─► Observed Variance: +7,000 Litres (+140.0%)
          │
          ▼
   [AnomalyRecord Created / Updated Idempotently]
   - record: ActivityRecord #X
   - rule: DIESEL_SPIKE (v1)
   - severity: HIGH
   - status: OPEN
   - observed_value: 12000.0000
   - baseline_value: 5000.0000
   - deviation_percentage: +140.00%
   - explanation_text: "Observed quantity (12,000.0000 L) exceeds historical baseline (5,000.0000 L) by +140.0% (threshold: 100.0%)."
   - AuthAuditLog: ANOMALY_DETECTED
          │
          ▼
[Subsidiary Manager Review Workspace]
(Reviewer investigates operational justification without modifying raw telemetry)
          │
          ├──► ACKNOWLEDGE ────► Status: ACKNOWLEDGED ➔ AuthAuditLog: ANOMALY_ACKNOWLEDGED
          ├──► EXPLAIN ────────► Status: EXPLAINED (e.g., "Emergency generator ran during grid failure") ➔ AuthAuditLog: ANOMALY_EXPLAINED
          ├──► DISMISS ────────► Status: DISMISSED (e.g., "Planned plant shutdown baseline shift") ➔ AuthAuditLog: ANOMALY_DISMISSED
          └──► REQUEST CORRECTION (Phase 14)
                     │
                     ▼
             [Correction Request Flow]
             - ActivityRecord quantity corrected: 5,200 Litres
             - ActivityRevision #2 captured with delta
             - Resubmission #2 executed
                     │
                     ▼
             [Automated Anomaly Re-evaluation]
             - Anomaly Engine re-runs against updated quantity (5,200 L)
             - New variance: +4.0% (below +100% threshold)
             - Historical AnomalyRecord preserved in RESOLVED status with pointer to Resubmission
             - AuthAuditLog: ANOMALY_RESOLVED

===================================================================================
                  FULL COMPLIANCE & GOVERNANCE LINEAGE
===================================================================================
Evidence (SHA-256) ➔ ActivityRecord ➔ Validation ➔ Anomaly Detection ➔
Submission ➔ Subsidiary Review ➔ Revision/Resubmission ➔ Anomaly Resolution ➔ Scope 1/2/3 Calculation
===================================================================================
```

---

## 7. Phase 16 — Supplier & Procurement Traceability Lineage

Phase 16 establishes the complete commercial audit trail connecting suppliers, invoices, and purchase records to ESG evidence and future Scope 3 accounting:

```text
===================================================================================
                  SUPPLIER & PROCUREMENT AUDIT TRACEABILITY
===================================================================================

[SUPPLIER MASTER]
- Supplier Code: VEND-001 (Unique, Stable ID)
- Tax / GST ID: 29AABCU9603R1ZM
- ESG Profile: ISO 14001, ESG Declaration
- Status: ACTIVE (Archival preserves historical purchases)
        │
        ▼
[PROCUREMENT RECORD]
- Reference: MEIL-PROC-202610-A1B2
- Supplier: UltraTech Cement Ltd (VEND-001)
- Invoice #: INV-2026-8819 | PO #: PO-HYDRO-4401
- Purchase Date: 2026-10-01 (Within Reporting Period FY2026-27-Q3)
- Site: Polavaram Headworks (SITE-POL-101)
- Currency: INR | Total Amount: ₹500,000.00
        │
        ├─► [PROCUREMENT LINE ITEMS]
        │     - Item 1: Ordinary Portland Cement (OPC 53)
        │     - Quantity: 100.0000 Tonnes @ ₹5,000.00/T = ₹500,000.00
        │     - Scope 3 Category: CAT_01 (Purchased Goods and Services)
        │     - Future Link: ActivityMaster (Cement Consumption)
        │
        ├─► [SUPPORTING EVIDENCE]
        │     - File: evidence/SITE-POL-101/FY2026-27-Q3/proc_1/invoice.pdf
        │     - SHA-256: 4a2b9... (Tamper-evident checksum)
        │
        ├─► [OCR EXTRACTION & COMPARISON]
        │     - Extracted Invoice #: INV-2026-8819 [MATCH]
        │     - Extracted Amount: 500,000.00 [MATCH]
        │     - Extracted Date: 2026-10-01 [MATCH]
        │     - Extracted Vendor: UltraTech Cement [MATCH]
        │     - Non-destructive: Stored commercial records never silently overwritten
        │
        ├─► [VALIDATION & ANOMALY EVALUATION]
        │     - Validation: VALID (Supplier active, period open, evidence attached)
        │     - Anomaly Detection: Clean (No duplicate invoice, price within tolerance)
        │
        ▼
[WORKFLOW LIFECYCLE & AUDIT EVENTS]
- SUBMISSION: Site Manager submits (AuthAuditLog: PROCUREMENT_SUBMITTED)
- REVIEW: Subsidiary Manager verifies (AuthAuditLog: PROCUREMENT_VERIFIED)
- (Or CORRECTION REQUESTED ➔ REMEDIATED ➔ RESUBMITTED ➔ VERIFIED)
- PREPARED FOR: Scope 3 GHG Category 1 calculation & SEBI BRSR Principle 6
===================================================================================
```


