# MEIL ESG CONTROL TOWER — Organizational Governance & Data Ownership Workflow
## Phase 03: Organization Hierarchy Integration

---

## 1. Operating Governance Model

The **MEIL ESG CONTROL TOWER** operates across four tiers of governance:

```text
+-----------------------------------------------------------------------------------------+
| LEVEL 1: MEIL ENTERPRISE GROUP                                                          |
| Roles: MEIL_OPERATOR, ESG_MANAGER, AUDITOR                                              |
| Responsibilities: Enterprise GHG consolidation, BRSR Core disclosures, assurance audit  |
+-----------------------------------------------------------------------------------------+
                                           │
                                           ▼
+-----------------------------------------------------------------------------------------+
| LEVEL 2: SUBSIDIARY DIVISION (e.g. MEIL Hydro, MEIL Solar)                             |
| Roles: SUBSIDIARY_MANAGER                                                               |
| Responsibilities: Division review desk, validation anomaly triage, escalation governance|
+-----------------------------------------------------------------------------------------+
                                           │
                                           ▼
+-----------------------------------------------------------------------------------------+
| LEVEL 3: INFRASTRUCTURE PROJECT (e.g. Polavaram Irrigation, Kurnool Solar Park)         |
| Roles: Project Engineers, Operations Team                                               |
| Responsibilities: Project asset tracking, boundary management, milestone compliance     |
+-----------------------------------------------------------------------------------------+
                                           │
                                           ▼
+-----------------------------------------------------------------------------------------+
| LEVEL 4: OPERATIONAL SITE (e.g. Dam Headworks, Array 1 Inverter Station)                |
| Roles: SITE_MANAGER                                                                     |
| Responsibilities: Raw fuel/power telemetry, utility invoice uploads, OCR verification  |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Upward Data Flow & Review Lineage

```text
[SITE MANAGER] ──► Submits raw activity entry + evidence doc
                          │
                          ▼
               [AUTOMATED VALIDATION] ──► Sanity check & anomaly flags
                          │
                          ▼
            [SUBSIDIARY MANAGER REVIEW] ──► Verify division accuracy or request revision
                          │
                          ▼
              [ESG MANAGER CONSOLIDATION] ──► Enterprise Scope 1, 2, 3 carbon accounting
                          │
                          ▼
              [INDEPENDENT ASSURANCE] ──► AUDITOR traces formula lineage to raw site evidence
```

---

## 3. Server-Side Scoping Boundaries

| Persona | Permitted Organizational Scope | Organization Management Authority |
| :--- | :--- | :--- |
| **`SITE_MANAGER`** | Explicitly assigned sites only | Strictly denied organization CRUD or hierarchy overview. Can only view assigned site profile. |
| **`SUBSIDIARY_MANAGER`** | Assigned subsidiary divisions, child projects, and child sites | Can view assigned division tree. Can create/edit projects and sites **only** within assigned subsidiary. Denied access to other divisions. |
| **`ESG_MANAGER`** | Universal Enterprise Read Scope | Read-only access to complete organizational hierarchy. Structural modifications restricted to MEIL_OPERATOR. |
| **`AUDITOR`** | Universal Enterprise Assurance Scope | Strictly **read-only**. Blocked from create, edit, or deactivation operations across all organizational entities. |
| **`MEIL_OPERATOR`** | Full Enterprise Operational Scope | Full CRUD authority across Companies, Subsidiaries, Projects, and Operational Sites. |

---

## 4. Phase 09 Supporting Evidence Lifecycle Workflow

```text
[SITE MANAGER]
      │
      ├─► [Selects/Creates ActivityRecord]
      │         │
      │         ▼
      ├─► [Uploads Supporting Evidence File (PDF/JPEG/PNG/XLSX/DOCX/CSV)]
      │         │
      │         ▼
      ├─► [File Validation: Magic Bytes Check + SHA-256 Checksum + Safe Storage Path]
      │         │
      │         ▼
      ├─► [Evidence Status: ACTIVE (Linked to ActivityRecord via FK with PROTECT)]
      │         │
      │         ▼
      ├─► [Activity Status Progression: DRAFT ➔ READY ➔ SUBMITTED]
      │
      └─► [Correction / Retirement Path: If invoice was superseded, soft-retires with reason;
           SHA-256 hash & original file permanently preserved for audit compliance]
```

---

## 5. Phase 10 ESG Validation Engine Quality Gate Workflow

```text
[SITE MANAGER DATA ENTRY]
          │
          ▼
    Activity Record (Draft)
          │
          ├──────────────┐
          ▼              ▼
   Attached Evidence   Activity Master Rules
          │              │
          └──────┬───────┘
                 │
                 ▼
     [ESG VALIDATION ENGINE]
     Layer 1: Structural (Presence, types, positive quantity, valid units)
     Layer 2: Scope (Site active, user assigned, project/company hierarchy)
     Layer 3: Period (Open status, measurement date inside reporting dates)
     Layer 4: Activity (Compatible unit taxonomy, measurement date flag)
     Layer 5: Evidence (Mandatory evidence attached, active status)
     Layer 6: Consistency & Deterministic Duplicates (Same site/date/activity)
     Layer 7: Workflow Readiness (Blocking errors check)
                 │
                 ▼
       Validation Run & Findings Created (Immutable)
                 │
       ┌─────────┴─────────┐
       ▼                   ▼
 [ERRORS DETECTED]   [NO BLOCKING ERRORS]
   Status: INVALID     Status: VALID or WARNING
   Auto-demotes to     Eligible for Submission
   DRAFT if READY      (Phase 11 OCR / Phase 12 Review)
       │
       ▼
  Site Manager
  Corrects Data / Evidence
       │
       ▼
  Re-Validate (New Run Created, History Preserved)
```

---

## 6. Phase 12 Formal Submission Lifecycle Workflow

```text
[SITE MANAGER]
      │
      ├─► [Pre-Submission Validation: Must be VALID or WARNING (Zero Blocking Errors)]
      ├─► [Evidence Check: Active evidence attached if required by ActivityMaster]
      ├─► [Reporting Period Check: Period must be OPEN and allows data modification]
      │
      ▼
[SUBMIT ACTION (POST /data-entry/<id>/submit/)]
      │
      ├─► Creates Submission #1 (status: SUBMITTED, is_current: True)
      ├─► Captures immutable snapshot_data (quantity, unit, dates, evidence hashes)
      ├─► Locks ActivityRecord (status: SUBMITTED; telemetry editing locked)
      ├─► Emits AuthAuditLog (SUBMISSION_CREATED)
      │
      ▼
[WITHDRAW ACTION (POST /data-entry/<id>/withdraw/)] (Conditional)
      │
      ├─► Site Manager may withdraw submission ONLY while still in SUBMITTED state (before review begins)
      ├─► Marks Submission status -> WITHDRAWN (is_current: False)
      ├─► Returns ActivityRecord -> READY for editing
      └─► Terminal states (VERIFIED, APPROVED, CANCELLED) cannot be withdrawn
```

---

## 7. Phase 13 Subsidiary Manager First-Line Review Workflow

```text
[SUBSIDIARY MANAGER INBOX (/subsidiary-manager/inbox/)]
      │
      ├─► Scoped strictly to assigned subsidiary division, child projects, and sites
      ├─► Filter by Reporting Period, Activity Category, Status, Site
      │
      ▼
[REVIEW WORKSPACE (/subsidiary-manager/submissions/<id>/review/)]
      │
      ├─► Inspects: Operational Telemetry + Attached Evidence + OCR Results + Validation Run Findings
      ├─► Anti-Self-Review Guard: Submitter CANNOT review their own submission
      ├─► Auditor Guard: Read-only assurance (403 on state mutation)
      │
      ▼
[DECISION ACTIONS (POST ONLY with CSRF Protection)]
      │
      ├──► [VERIFY] ──► Sets Submission & Record -> VERIFIED. Immutable sign-off review record created.
      │
      ├──► [REQUEST CORRECTION] ──► Transitions Submission -> CORRECTION_REQUESTED, Record -> REJECTED.
      │                             Mandates structured reason, required correction, affected area.
      │                             Creates authoritative CorrectionRequest & baseline ActivityRevision #1.
      │
      ├──► [EXPLAIN] ──► Sets Submission -> EXPLAINED. Records operating explanation without altering telemetry.
      │
      └──► [ESCALATE] ──► Sets Submission -> ESCALATED. Routes governance ambiguity to ESG_MANAGER.
```

---

## 8. Phase 14 Controlled Correction, Explanation & Resubmission Lifecycle

The core architecture guarantees: **A correction never silently overwrites history. Every iteration creates an immutable revision ledger, preserves original data, and mandates revalidation before re-entering the review queue.**

```text
                     SUBSIDIARY MANAGER
                              │
                    [REQUEST CORRECTION]
                    - Reason (Mandatory text)
                    - Required Changes
                    - Affected Area (Data / Evidence / Both)
                              │
                              ▼
                   [CorrectionRequest: OPEN]
                   [ActivityRevision #1 (Baseline Snapshot Saved)]
                   [Submission #1: CORRECTION_REQUESTED]
                   [ActivityRecord: REJECTED]
                              │
                              ▼
                        SITE MANAGER
                              │
                    [CORRECTION INBOX (/corrections/)]
                    - Surfaces in Site Manager Dashboard pending alerts
                    - Displays reason, requested by, timestamp, affected scope
                              │
                              ▼
                    [CORRECTION WORKSPACE (/corrections/<id>/)]
                    - Reviews original submission & reviewer instructions
                    - Starts correction (Status: OPEN ➔ IN_PROGRESS)
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
           [EDIT TELEMETRY]      [MANAGE EVIDENCE]
           - Permitted fields:    - Add required documents
             quantity, unit,      - Supersede wrong bills
             date, notes          - OCR re-runs preserved
                    │                   │
                    └─────────┬─────────┘
                              │
                              ▼
                 [MANDATORY REVALIDATION RUN]
                 (Phase 10 Validation Engine re-evaluated)
                              │
                 ┌────────────┴────────────┐
                 ▼                         ▼
          [BLOCKING ERRORS]          [VALID / WARNING]
          - Status: IN_PROGRESS      - Status: READY_FOR_RESUBMISSION
          - Resubmit STRICTLY BLOCKED - Resubmission enabled
                              │
                              ▼
                   [EXECUTE RESUBMISSION]
                   (POST /corrections/<id>/resubmit/)
                              │
                              ├─► Atomically row-locks Record, Correction, and Submission #1
                              ├─► Validates reporting period is OPEN & allows modification
                              ├─► Re-verifies zero blocking validation errors & required evidence
                              ├─► Computes field-by-field JSON deltas vs original submission
                              ├─► Creates ActivityRevision #2 (records changed_fields, actor, timestamp)
                              ├─► Creates Submission #2 (parent_submission ➔ Submission #1, submission_number=2)
                              ├─► Marks Submission #1 is_current=False; Submission #2 is_current=True
                              ├─► Resolves CorrectionRequest (status ➔ RESOLVED, resubmission ➔ Submission #2)
                              ├─► Updates ActivityRecord status ➔ SUBMITTED
                              ├─► Emits AuthAuditLog (CORRECTION_RESOLVED, RESUBMISSION_CREATED)
                              │
                              ▼
                     SUBSIDIARY MANAGER
                              │
                    [RE-REVIEW WORKSPACE]
                    - Inspects Comparative Delta Ledger (Original vs Corrected Telemetry)
                    - Inspects Chronological Submission & Review Timeline
                    - Completes second review: VERIFY (Submission #2 & Record ➔ VERIFIED)
```

---

## 7. Phase 15: ESG Anomaly Detection & Operational Patterns Engine

```text
                    ACTIVITY RECORD
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
          VALIDATION                ANOMALY
   "Is data structurally     "Is data unusual or suspicious
      & logically valid?"       vs expected patterns?"
              │                         │
              │                  Deterministic Anomaly Rules:
              │                  1. Historical Spike (>100%)
              │                  2. Historical Drop (>50%)
              │                  3. Period-over-Period Variance (>50%)
              │                  4. Duplicate Operational Activity
              │                  5. Threshold Range Breach
              │                  6. Operational Intensity Anomaly
              │                         │
              │                         ▼
              │                  ANOMALY RECORD
              │                  - Observed vs Baseline Telemetry
              │                  - Variance % & Deviation
              │                  - Explainable Finding Justification
              │                  - Risk Severity (INFO, LOW, MEDIUM, HIGH, CRITICAL)
              │                  - Status (OPEN, ACKNOWLEDGED, EXPLAINED, RESOLVED, DISMISSED)
              │                         │
              └────────────┬────────────┘
                           ▼
                      SUBMISSION
                           │
                           ▼
                 SUBSIDIARY REVIEW
                           │
        ┌──────────────────┴──────────────────┐
        ▼                                     ▼
ANOMALY GOVERNANCE                     CORRECTION WORKFLOW
- Acknowledge Anomaly                  - Request Correction (Phase 14)
- Record Operational Explanation       - Site Manager Revises Data
- Resolve / Dismiss Findings           - Revalidate & Resubmit
- Preserves Historical Lineage         - Auto-resolve Anomaly on Normalization
```

### Core Architecture Invariants:
1. **Anomaly != Invalid:** An anomalous record is a review signal, never an automatic rejection. Valid data with extreme operational spikes remains valid until reviewers decide.
2. **Rolling Historical Baselines:** Computed strictly across comparable approved records (same site, same activity, same unit dimension). Incomplete or insufficient historical data (< 2 records) reports "Baseline unavailable" rather than fabricating numbers.
3. **Deterministic & Explainable:** Zero black-box ML or unexplainable heuristics; every anomaly result provides exact observed value, baseline value, delta, variance percentage, and readable reason.
4. **Controlled Review Lifecycle:** OPEN -> ACKNOWLEDGED -> EXPLAINED / RESOLVED / DISMISSED. Strict server-side RBAC protects all state transitions.
5. **Phase 14 Correction Integration:** Resubmissions automatically trigger anomaly re-evaluation, auto-resolving normalized telemetry while preserving historical audit trails.

