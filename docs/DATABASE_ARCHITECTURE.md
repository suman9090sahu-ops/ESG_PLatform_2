# MEIL ESG CONTROL TOWER — Database Architecture Specification
## Phase 03: Organization Hierarchy & Data Ownership Scope

---

## 1. Executive Summary

The **MEIL ESG CONTROL TOWER** organizational hierarchy serves as the universal **scope foundation** for the entire platform. Every ESG telemetry record, utility invoice, fuel meter reading, OCR upload, anomaly flag, calculation step, and SEBI BRSR Core indicator resolves directly to this hierarchy.

Rather than independent tables, the architecture implements a normalized four-tiered relational hierarchy:

```text
MEIL ENTERPRISE GROUP (Company)
           │
           └── SUBSIDIARY DIVISION (Subsidiary)
                   │
                   └── INFRASTRUCTURE PROJECT (Project)
                           │
                           └── OPERATIONAL SITE (Site)
```

---

## 2. Conceptual Hierarchy & Entities

```text
+-------------------------------------------------------+
|                       Company                         |
|  - id (BigAutoField, PK)                              |
|  - code (VARCHAR(50), UNIQUE, INDEX)                 |
|  - name (VARCHAR(255), UNIQUE)                        |
|  - legal_name (VARCHAR(255))                          |
|  - country (VARCHAR(100), default='India')            |
|  - registered_address (TEXT)                          |
|  - description (TEXT)                                 |
|  - status (VARCHAR(20), ACTIVE/INACTIVE/CLOSED, INDEX)|
|  - is_active (BOOLEAN, default=True)                  |
|  - created_at, updated_at (TIMESTAMPTZ)               |
+-------------------------------------------------------+
                           │ 1
                           │ has many
                           ▼ N (on_delete=models.PROTECT)
+-------------------------------------------------------+
|                      Subsidiary                       |
|  - id (BigAutoField, PK)                              |
|  - company_id (FK -> Company.id, PROTECT)             |
|  - code (VARCHAR(50), UNIQUE, INDEX)                 |
|  - name (VARCHAR(255))                                |
|  - legal_name (VARCHAR(255))                          |
|  - short_name (VARCHAR(100))                          |
|  - industry (VARCHAR(100))                            |
|  - country (VARCHAR(100), default='India')            |
|  - registered_address (TEXT)                          |
|  - status (VARCHAR(20), ACTIVE/INACTIVE/CLOSED, INDEX)|
|  - is_active (BOOLEAN, default=True)                  |
|  - created_at, updated_at (TIMESTAMPTZ)               |
+-------------------------------------------------------+
                           │ 1
                           │ has many
                           ▼ N (on_delete=models.PROTECT)
+-------------------------------------------------------+
|                        Project                        |
|  - id (BigAutoField, PK)                              |
|  - subsidiary_id (FK -> Subsidiary.id, PROTECT)       |
|  - code (VARCHAR(50), UNIQUE, INDEX)                 |
|  - name (VARCHAR(255))                                |
|  - description (TEXT)                                 |
|  - location (VARCHAR(255))                            |
|  - status (VARCHAR(20), ACTIVE/INACTIVE/CLOSED, INDEX)|
|  - start_date, end_date (DATE, NULL)                  |
|  - is_active (BOOLEAN, default=True)                  |
|  - created_at, updated_at (TIMESTAMPTZ)               |
+-------------------------------------------------------+
                           │ 1
                           │ has many
                           ▼ N (on_delete=models.PROTECT)
+-------------------------------------------------------+
|                         Site                          |
|  - id (BigAutoField, PK)                              |
|  - project_id (FK -> Project.id, PROTECT)             |
|  - code (VARCHAR(50), UNIQUE, INDEX)                 |
|  - name (VARCHAR(255))                                |
|  - facility_type (VARCHAR(100))                       |
|  - location (VARCHAR(255))                            |
|  - latitude, longitude (DECIMAL(9,6), NULL)           |
|  - contact_person (VARCHAR(150))                      |
|  - contact_email (VARCHAR(254))                       |
|  - description (TEXT)                                 |
|  - status (VARCHAR(20), ACTIVE/INACTIVE/CLOSED, INDEX)|
|  - is_active (BOOLEAN, default=True)                  |
|  - created_at, updated_at (TIMESTAMPTZ)               |
+-------------------------------------------------------+
```

---

## 3. Relational Organizational Scope Assignments

Fine-grained authorization links authenticated users to distinct organizational levels through relational models:

```text
User ──┬── CompanyAssignment     ──► Company (Enterprise Group Scope)
       ├── SubsidiaryAssignment  ──► Subsidiary (Division Review Scope)
       ├── ProjectAssignment     ──► Project (Infrastructure Scope)
       └── SiteAssignment        ──► Site (Operational Data Entry Scope)
```

Each assignment table enforces a compound database unique constraint:
- `core_siteassignment`: `UNIQUE(user_id, site_id)`
- `core_subsidiaryassignment`: `UNIQUE(user_id, subsidiary_id)`
- `core_projectassignment`: `UNIQUE(user_id, project_id)`
- `core_companyassignment`: `UNIQUE(user_id, company_id)`

---

## 4. Referential Integrity & Deletion Policy

### Foreign Key Protection Axiom
All downward hierarchical relationships utilize `on_delete=models.PROTECT`.
- A `Company` cannot be deleted while child `Subsidiary` records exist.
- A `Subsidiary` cannot be deleted while child `Project` records exist.
- A `Project` cannot be deleted while child `Site` records exist.
- A `Site` cannot be deleted while child activity, invoice, or evidence records reference it in future phases.

### Safe Deactivation / Archiving Policy
Historical ESG disclosures under SEBI BRSR and GHG Protocol regulations require permanent audit lineage. Hard deletes of organizational entities that have reported telemetry are strictly prohibited.
- When an entity is decommissioned, its lifecycle state is changed to `INACTIVE` or `CLOSED` via `safe_deactivate_entity()`.
- The `is_active` boolean is synchronized to `False`.
- The operation writes an `ORGANIZATION_DEACTIVATED` event to `core_authauditlog`.
- Inactive entities remain queryable for historical reporting periods and assurance audits, but are filtered out of active operational data collection.

---

## 5. Organizational Inheritance Traversal

The ORM models provide explicit property traversals:

```python
# Site level
site.project           # -> Project
site.subsidiary        # -> Subsidiary (site.project.subsidiary)
site.company           # -> Company (site.project.subsidiary.company)

# Project level
project.subsidiary     # -> Subsidiary
project.company        # -> Company (project.subsidiary.company)

# Subsidiary level
subsidiary.company     # -> Company
subsidiary.parent_company # -> Company
```

---

## 6. Database Migrations

1. `core.0001_initial`: Initial User, Role, Company, Subsidiary, Project, Site, Assignments, and AuthAuditLog.
2. `core.0002_company_country_company_legal_name_and_more`:
   - Adds `OrganizationStatus` lifecycle state choices (`ACTIVE`, `INACTIVE`, `CLOSED`) with database indexes.
   - Adds legal names, short names, countries, registered addresses, facility types, GPS coordinates, timelines, and contact attributes.
   - Enriches `AuthAuditLog` with `ORGANIZATION_CREATED`, `ORGANIZATION_UPDATED`, `ORGANIZATION_DEACTIVATED` event types.
3. `core.0003_alter_authauditlog_event_type_reportingperiod`:
   - Adds `ReportingPeriod` model with `CheckConstraint` (`start_date < end_date`), `UniqueConstraint` (`(company, code)`), and composite indexes.
   - Enriches `AuthAuditLog` with `PERIOD_CREATED`, `PERIOD_UPDATED`, `PERIOD_STATUS_CHANGED` event types.

---

## 7. Reporting Periods & Temporal Governance (Phase 04)

Reporting periods define the authoritative temporal boundaries for ESG activities, evidence ingestion, emission calculations, consolidation, and SEBI BRSR reporting.

```text
+-------------------------------------------------------------+
|                      ReportingPeriod                        |
|  - id (BigAutoField, PK)                                    |
|  - company_id (FK -> Company.id, PROTECT)                   |
|  - subsidiary_id (FK -> Subsidiary.id, PROTECT, NULL)       |
|  - code (VARCHAR(50), e.g. FY2025-26)                       |
|  - name (VARCHAR(150), e.g. FY 2025-26 Annual ESG Cycle)   |
|  - fiscal_year (VARCHAR(50), e.g. FY 2025-26)               |
|  - start_date (DATE, inclusive)                             |
|  - end_date (DATE, inclusive)                               |
|  - status (VARCHAR(20), DRAFT/OPEN/CLOSED/LOCKED/FINALIZED) |
|  - description (TEXT)                                       |
|  - created_by (FK -> User.id, SET_NULL)                     |
|  - updated_by (FK -> User.id, SET_NULL)                     |
|  - created_at, updated_at (TIMESTAMPTZ)                     |
+-------------------------------------------------------------+
```

### Constraints & Integrity Rules
- **CheckConstraint**: `check=Q(start_date < end_date)` ensures start date is strictly before end date.
- **UniqueConstraint**: `unique_together = (company, code)` prevents duplicate period codes per company.
- **Overlap Prevention**: Enforced at application and service layer; prevents overlapping date ranges within the same company and subsidiary scope.
- **Controlled Lifecycle**:
  `DRAFT` -> `OPEN` -> `CLOSED` -> `LOCKED` -> `FINALIZED`
  Reopening supported: `CLOSED -> OPEN`, `LOCKED -> CLOSED`.
  `FINALIZED` is an immutable terminal regulatory state.
- **Data Protection**:
  Operational data entry (`allows_data_entry`) is permitted ONLY when `status == OPEN`.

---

## 8. Projects & Operational Sites Foundation (Phase 05)

Phase 05 establishes the operational boundary foundation where future ESG activity entry, evidence attachments, and telemetry measurements occur.

```text
+-------------------------------------------------------+
|                        Project                        |
|  - id (BigAutoField, PK)                              |
|  - subsidiary_id (FK -> Subsidiary.id, PROTECT)       |
|  - code (VARCHAR(50), UNIQUE, INDEX)                 |
|  - name (VARCHAR(255))                                |
|  - description (TEXT)                                 |
|  - location (VARCHAR(255))                            |
|  - status (VARCHAR(20), ACTIVE/INACTIVE/CLOSED, INDEX)|
|  - start_date, end_date (DATE, NULL)                  |
|  - is_active (BOOLEAN, default=True)                  |
|  - created_by (FK -> User.id, SET_NULL, NULL)         |
|  - updated_by (FK -> User.id, SET_NULL, NULL)         |
|  - created_at, updated_at (TIMESTAMPTZ)               |
+-------------------------------------------------------+
                           │ 1
                           │ has many
                           ▼ N (on_delete=models.PROTECT)
+-------------------------------------------------------+
|                         Site                          |
|  - id (BigAutoField, PK)                              |
|  - project_id (FK -> Project.id, PROTECT)             |
|  - code (VARCHAR(50), UNIQUE, INDEX)                 |
|  - name (VARCHAR(255))                                |
|  - facility_type (VARCHAR(100))                       |
|  - location (VARCHAR(255))                            |
|  - latitude, longitude (DECIMAL(9,6), NULL)           |
|  - operational_start_date (DATE, NULL)                |
|  - operational_end_date (DATE, NULL)                  |
|  - contact_person (VARCHAR(150))                      |
|  - contact_email (VARCHAR(254))                       |
|  - description (TEXT)                                 |
|  - status (VARCHAR(20), ACTIVE/INACTIVE/CLOSED, INDEX)|
|  - is_active (BOOLEAN, default=True)                  |
|  - created_by (FK -> User.id, SET_NULL, NULL)         |
|  - updated_by (FK -> User.id, SET_NULL, NULL)         |
|  - created_at, updated_at (TIMESTAMPTZ)               |
+-------------------------------------------------------+
```

### Constraints & Integrity Rules (Phase 05)
- **CheckConstraint (`check_project_start_before_end`)**: `check=Q(start_date__isnull=True) | Q(end_date__isnull=True) | Q(start_date__lte=F('end_date'))` ensures Project start date does not exceed end date.
- **CheckConstraint (`check_site_start_before_end`)**: `check=Q(operational_start_date__isnull=True) | Q(operational_end_date__isnull=True) | Q(operational_start_date__lte=F('operational_end_date'))` ensures Site operational start date does not exceed end date.
- **Composite Indexes**:
  - Project: `Index(fields=['subsidiary', 'status'])`, `Index(fields=['code'])`
  - Site: `Index(fields=['project', 'status'])`, `Index(fields=['code'])`
- **Audit Lineage**:
  - `AuthAuditLog.EventType.PROJECT_CREATED`, `PROJECT_UPDATED`, `PROJECT_DEACTIVATED`
  - `AuthAuditLog.EventType.SITE_CREATED`, `SITE_UPDATED`, `SITE_DEACTIVATED`
- **Migration**:
  - `apps/core/migrations/0004_project_created_by_project_updated_by_and_more.py`

---

## 9. ESG Data Entry & Activity Telemetry (Phase 08)

Phase 08 establishes the operational measurement layer linking Operational Sites, Reporting Cycles, and Activity Master reference definitions to actual physical ESG consumption records.

```text
+-------------------------------------------------------------------------------------------------+
|                                         ActivityRecord                                          |
|  - id (BigAutoField, PK)                                                                        |
|  - site_id (FK -> Site.id, PROTECT, INDEX)                                                      |
|  - reporting_period_id (FK -> ReportingPeriod.id, PROTECT, INDEX)                                |
|  - activity_id (FK -> ActivityMaster.id, PROTECT, INDEX)                                        |
|  - measurement_date (DATE, INDEX)                                                               |
|  - quantity (DECIMAL(18, 4), CHECK: quantity >= 0)                                             |
|  - unit_id (FK -> UnitOfMeasure.id, PROTECT)                                                    |
|  - notes (TEXT, BLANK)                                                                          |
|  - evidence_reference (VARCHAR(255), BLANK)                                                     |
|  - status (VARCHAR(20), DRAFT/READY/SUBMITTED/VERIFIED/APPROVED/REJECTED, INDEX)                |
|  - created_by (FK -> User.id, SET_NULL, NULL)                                                   |
|  - updated_by (FK -> User.id, SET_NULL, NULL)                                                   |
|  - created_at, updated_at (TIMESTAMPTZ)                                                         |
+-------------------------------------------------------------------------------------------------+
```

### Constraints & Integrity Rules (Phase 08)
- **CheckConstraint (`check_activity_record_quantity_non_negative`)**: `check=Q(quantity__gte=0)` prevents negative consumption quantities at the database engine level.
- **Model Validation (`clean`)**:
  - Validates that the selected `unit` is permissible for the assigned `activity` (`unit == activity.base_unit` or `unit in activity.allowed_units`).
  - Validates that `measurement_date` falls strictly within the `reporting_period` start and end date boundaries.
  - Validates that `activity.status == MasterStatus.ACTIVE` (cannot record against inactive or archived activities).
  - Validates organizational boundary alignment (Site's parent company must match the Reporting Period's governing company).
- **Composite Indexes**:
  - `idx_rec_site_period`: `['site', 'reporting_period']` — optimizes scoped dashboard queries and period aggregations.
  - `idx_rec_act_date`: `['activity', 'measurement_date']` — accelerates chronological emissions calculations and trend charting.
  - `idx_rec_status`: `['status']` — optimizes workflow triage and review queues.
  - `idx_rec_created`: `['-created_at']` — accelerates ledger pagination and recent activity feeds.
- **Workflow State Machine (`RecordStatus`)**:
  - `DRAFT`: Editable and deletable by assigned Site Manager.
  - `READY`: Marked ready for subsidiary submission review; editable by Site Manager.
  - `SUBMITTED`: Forwarded for Subsidiary Manager verification; locked from Site Manager modification.
  - `VERIFIED`: Formally verified by Subsidiary Manager; immutable.
  - `APPROVED`: Included in enterprise calculation and BRSR consolidation; immutable.
  - `REJECTED`: Flagged during review with feedback; re-editable by Site Manager.
- **Audit Lineage**:
  - `AuthAuditLog.EventType.ACTIVITY_RECORD_CREATED`
  - `AuthAuditLog.EventType.ACTIVITY_RECORD_UPDATED`
  - `AuthAuditLog.EventType.ACTIVITY_RECORD_DELETED`
- **Migration**:
  - `apps/core/migrations/0006_alter_authauditlog_event_type_activityrecord.py`

---

## 10. Evidence Management & Audit Traceability (Phase 09)

Phase 09 establishes the auditable supporting document layer linking physical invoices, utility bills, meter readings, manifests, and lab reports directly to specific ESG `ActivityRecord` entries.

```text
+-------------------------------------------------------------------------------------------------+
|                                             Evidence                                            |
|  - id (BigAutoField, PK)                                                                        |
|  - activity_record_id (FK -> ActivityRecord.id, PROTECT, INDEX, related_name="evidence_files")    |
|  - file (FileField -> upload_to=evidence_file_upload_path)                                       |
|  - evidence_type (VARCHAR(30), INVOICE/UTILITY_BILL/METER_READING/FUEL_CHALLAN/..., INDEX)      |
|  - original_filename (VARCHAR(255))                                                             |
|  - file_type (VARCHAR(100), MIME content type)                                                  |
|  - file_size (POSITIVE BIGINT, CHECK: file_size > 0)                                            |
|  - file_hash (VARCHAR(64), SHA-256 cryptographic checksum, INDEX)                               |
|  - description (TEXT, BLANK)                                                                    |
|  - status (VARCHAR(20), ACTIVE/RETIRED, DEFAULT: ACTIVE, INDEX)                                 |
|  - retirement_reason (TEXT, BLANK)                                                              |
|  - retired_at (TIMESTAMPTZ, NULL)                                                               |
|  - retired_by (FK -> User.id, SET_NULL, NULL, related_name="retired_evidence_set")              |
|  - ocr_metadata (JSONField, DEFAULT: dict, BLANK)                                               |
|  - validation_metadata (JSONField, DEFAULT: dict, BLANK)                                        |
|  - uploaded_by (FK -> User.id, SET_NULL, NULL, related_name="uploaded_evidence_set")            |
|  - created_at, updated_at (TIMESTAMPTZ)                                                         |
+-------------------------------------------------------------------------------------------------+
```

### Constraints & Integrity Rules (Phase 09)
- **CheckConstraint (`check_evidence_file_size_positive`)**: `check=Q(file_size__gt=0)` guarantees no 0-byte or negative-size file entries are recorded in the database.
- **FK Deletion Safety (`on_delete=models.PROTECT`)**: Prevents accidental deletion of parent `ActivityRecord` while supporting audit evidence is attached.
- **Cryptographic Fingerprint (`file_hash`)**: 64-character SHA-256 hash computed on upload stream ensures end-to-end tamper-evident audit traceability.
- **Safe Storage Partitioning (`evidence_file_upload_path`)**: Files are stored at `evidence/<site_code>/<period_code>/rec_<record_id>/<uuid12>_<safe_filename>` preventing path traversal and name collisions.
- **Magic Bytes Validation**: Enforces MIME verification via magic byte inspection for PDF (`%PDF-`), JPEG (`\xff\xd8\xff`), PNG (`\x89PNG`), and ZIP/OOXML (`PK\x03\x04`). Rejects executable extensions (`.exe`, `.sh`, `.bat`, `.py`, `.js`, `.bin`, `.msi`).
- **Composite & Filter Indexes**:
  - `idx_ev_rec_status`: `['activity_record', 'status']` — optimizes fetching active supporting evidence for an activity record.
  - `idx_ev_type`: `['evidence_type']` — accelerates taxonomy queries across the evidence repository.
  - `idx_ev_created`: `['-created_at']` — powers chronological repository views and pagination.
  - `idx_ev_hash`: `['file_hash']` — enables audit deduplication and cryptographic verification lookups.
- **Lifecycle & Retirement**:
  - `ACTIVE`: Current audit-supporting document.
  - `RETIRED`: Soft-retired with mandatory reason, timestamp, and actor; preserved immutably for historical audits. Hard deletion is restricted to DRAFT records by record owner or operator.
- **Audit Lineage**:
  - `AuthAuditLog.EventType.EVIDENCE_UPLOADED`
  - `AuthAuditLog.EventType.EVIDENCE_DOWNLOADED`
  - `AuthAuditLog.EventType.EVIDENCE_RETIRED`
  - `AuthAuditLog.EventType.EVIDENCE_DELETED`
- **Migration**:
  - `apps/core/migrations/0007_alter_authauditlog_event_type_evidence.py`

---

## 11. ESG Validation Engine & Data Quality Ledger (Phase 10)

Phase 10 establishes the deterministic validation engine evaluating ESG activity records and supporting evidence across Layers 1–7 (Structural, Scope, Period, Activity, Evidence, Consistency, Workflow Readiness) prior to downstream review, anomaly analysis, and BRSR calculation.

```text
+----------------------------------------------------------------------------------------------------+
|                                           ValidationRule                                           |
|  - id (BigAutoField, PK)                                                                           |
|  - code (VARCHAR(64), UNIQUE, INDEX)                                                               |
|  - name (VARCHAR(255))                                                                             |
|  - description (TEXT)                                                                              |
|  - category (VARCHAR(32), STRUCTURAL/SCOPE/PERIOD/ACTIVITY/EVIDENCE/CONSISTENCY/WORKFLOW, INDEX)   |
|  - severity (VARCHAR(16), ERROR/WARNING/INFO, DEFAULT: ERROR, INDEX)                               |
|  - is_active (BOOLEAN, DEFAULT: True, INDEX)                                                       |
|  - is_blocking (BOOLEAN, DEFAULT: True)                                                            |
|  - applicable_activity (FK -> ActivityMaster.id, NULL, ON_DELETE: SET_NULL)                        |
|  - rule_parameters (JSONField, DEFAULT: dict, BLANK)                                               |
|  - version (POSITIVE INT, DEFAULT: 1)                                                              |
|  - effective_from (DATE, DEFAULT: current_date)                                                    |
|  - created_at, updated_at (TIMESTAMPTZ)                                                            |
+----------------------------------------------------------------------------------------------------+
                                      ▲ 1
                                      │ evaluates
                                      ▼ N
+----------------------------------------------------------------------------------------------------+
|                                           ValidationResult                                         |
|  - id (BigAutoField, PK)                                                                           |
|  - validation_run_id (FK -> ValidationRun.id, CASCADE, INDEX, related_name="results")              |
|  - activity_record_id (FK -> ActivityRecord.id, CASCADE, INDEX, related_name="validation_results")  |
|  - rule_id (FK -> ValidationRule.id, PROTECT, INDEX, related_name="results")                       |
|  - severity (VARCHAR(16), ERROR/WARNING/INFO, INDEX)                                               |
|  - is_blocking (BOOLEAN, DEFAULT: True)                                                            |
|  - field_name (VARCHAR(64), BLANK, INDEX)                                                          |
|  - message (TEXT)                                                                                  |
|  - context_data (JSONField, DEFAULT: dict, BLANK)                                                  |
|  - created_at (TIMESTAMPTZ)                                                                        |
+----------------------------------------------------------------------------------------------------+
                                      ▲ N
                                      │ belongs to
                                      │ 1
+----------------------------------------------------------------------------------------------------+
|                                            ValidationRun                                           |
|  - id (BigAutoField, PK)                                                                           |
|  - activity_record_id (FK -> ActivityRecord.id, CASCADE, INDEX, related_name="validation_runs")     |
|  - run_number (POSITIVE INT)                                                                       |
|  - status (VARCHAR(20), UNVALIDATED/VALID/WARNING/INVALID, INDEX)                                  |
|  - total_rules_evaluated (POSITIVE INT, DEFAULT: 0)                                                |
|  - error_count (POSITIVE INT, DEFAULT: 0)                                                          |
|  - warning_count (POSITIVE INT, DEFAULT: 0)                                                        |
|  - info_count (POSITIVE INT, DEFAULT: 0)                                                           |
|  - summary_message (TEXT, BLANK)                                                                   |
|  - executed_by (FK -> User.id, SET_NULL, NULL, related_name="validation_runs_executed")             |
|  - executed_at (TIMESTAMPTZ)                                                                        |
|  - execution_duration_ms (POSITIVE INT, DEFAULT: 0)                                                |
|  - rule_version_snapshot (JSONField, DEFAULT: dict, BLANK)                                         |
|  - created_at (TIMESTAMPTZ)                                                                        |
+----------------------------------------------------------------------------------------------------+
```

### Constraints, Integrity Rules & Field Additions (Phase 10)
- **`ActivityRecord.validation_status`**: Added `VARCHAR(20)` with choices `UNVALIDATED`, `VALID`, `WARNING`, `INVALID` (Default: `UNVALIDATED`), indexed via `idx_rec_val_status`.
- **`ActivityRecord.last_validated_at`**: Nullable `DateTimeField` capturing the timestamp of the latest validation run.
- **UniqueConstraint (`unique_record_run_number`)**: `UniqueConstraint(fields=['activity_record', 'run_number'])` guarantees strictly monotonic, collision-free run numbering per record.
- **FK Deletion Safety (`on_delete=models.PROTECT`)**: Prevents deleting historical `ValidationRule` definitions that have associated results in the audit ledger.
- **Composite Indexes**:
  - `idx_vrun_rec_status`: `['activity_record', 'status']` — accelerates latest-run lookups and workflow readiness gates.
  - `idx_vrun_rec_num`: `['activity_record', '-run_number']` — powers chronological run history display.
  - `idx_vres_run_sev`: `['validation_run', 'severity']` — accelerates filtering blocking errors vs non-blocking warnings per run.
  - `idx_vres_rec_rule`: `['activity_record', 'rule']` — enables cross-run rule failure telemetry.
  - `idx_vrule_active_cat`: `['is_active', 'category']` — optimizes in-memory rule engine compilation.
- **Audit Lineage**:
  - `AuthAuditLog.EventType.VALIDATION_EXECUTED`
  - `AuthAuditLog.EventType.VALIDATION_RULE_CREATED`
  - `AuthAuditLog.EventType.VALIDATION_RULE_UPDATED`
- **Migration**:
  - `apps/core/migrations/0008_validationresult_validationrule_validationrun_and_more.py`

---

## 11. Phase 11 — OCR Document Intelligence & Entity Extraction Schema

### Architectural Principle
OCR output is strictly treated as **UNVERIFIED DOCUMENT INTEL**. It never silently mutates or replaces authoritative operational telemetry (`ActivityRecord.quantity`, `unit`, etc.). An immutable multi-run model (`OCRRun`) preserves historical extraction runs and audit lineage.

### Entity Relationship Diagram
```text
+----------------------------------------------------------------------------------------------------+
|                                               Evidence                                             |
|  - id (BigAutoField, PK)                                                                           |
|  - activity_record_id (FK -> ActivityRecord.id, CASCADE, INDEX)                                   |
|  - file (FileField)                                                                                |
|  - sha256_hash (CharField(64))                                                                    |
|  - evidence_type (CharField(32))                                                                   |
|  - ...                                                                                             |
+----------------------------------------------------------------------------------------------------+
                                      ▲ 1
                                      │ has runs
                                      ▼ N
+----------------------------------------------------------------------------------------------------+
|                                                OCRRun                                              |
|  - id (BigAutoField, PK)                                                                           |
|  - evidence_id (FK -> Evidence.id, CASCADE, INDEX, related_name="ocr_runs")                         |
|  - run_number (POSITIVE INT)                                                                       |
|  - status (VARCHAR(20), PENDING/PROCESSING/COMPLETED/FAILED/CANCELLED, INDEX)                      |
|  - engine (VARCHAR(64), default="pypdf-text-extractor")                                            |
|  - engine_version (VARCHAR(32), blank)                                                             |
|  - language (VARCHAR(16), default="eng")                                                           |
|  - page_count (POSITIVE INT, default=0)                                                            |
|  - extracted_text (TEXT, blank)                                                                    |
|  - confidence (FLOAT, NULL)                                                                        |
|  - page_data (JSONField, default=list, blank)                                                      |
|  - execution_duration_ms (POSITIVE INT, default=0)                                                |
|  - is_latest (BOOLEAN, default=True, INDEX)                                                        |
|  - error_message (TEXT, blank)                                                                     |
|  - initiated_by (FK -> User.id, SET_NULL, NULL, related_name="ocr_runs_initiated")                  |
|  - started_at, completed_at, created_at, updated_at (TIMESTAMPTZ)                                   |
+----------------------------------------------------------------------------------------------------+
                                      ▲ 1
                                      │ extracts
                                      ▼ N
+----------------------------------------------------------------------------------------------------+
|                                               OCRField                                             |
|  - id (BigAutoField, PK)                                                                           |
|  - ocr_run_id (FK -> OCRRun.id, CASCADE, INDEX, related_name="fields")                              |
|  - field_name (VARCHAR(64), INDEX)                                                                 |
|  - raw_value (TEXT)                                                                                |
|  - normalized_value (VARCHAR(255), blank, INDEX)                                                   |
|  - unit (VARCHAR(32), blank)                                                                       |
|  - confidence (FLOAT, NULL)                                                                        |
|  - page_number (POSITIVE INT, default=1)                                                           |
|  - bounding_box (JSONField, default=dict, blank)                                                   |
|  - extraction_method (VARCHAR(32), REGEX_RULE / HEURISTIC / LLM / MANUAL)                          |
|  - created_at (TIMESTAMPTZ)                                                                        |
+----------------------------------------------------------------------------------------------------+
```

### Constraints, Integrity Rules & Field Additions (Phase 11)
- **Multi-Run Monotonicity (`unique_evidence_run_number`)**: `UniqueConstraint(fields=['evidence', 'run_number'])` enforces collision-free run sequences per evidence document.
- **Latest Run Pointer (`is_latest`)**: Denormalized boolean flag indexed via composite `idx_ocr_run_ev_latest` (`['evidence', 'is_latest']`) for O(1) retrieval of current OCR intel.
- **Composite Indexes**:
  - `idx_ocr_run_ev_status`: `['evidence', 'status']` — quick lookup of active/failed runs.
  - `idx_ocr_run_ev_num`: `['evidence', '-run_number']` — chronological order for run history.
  - `idx_ocr_field_run_name`: `['ocr_run', 'field_name']` — entity field lookups.
  - `idx_ocr_field_name_val`: `['field_name', 'normalized_value']` — search across extracted entities.
- **Audit Lineage**:
  - `AuthAuditLog.EventType.OCR_REQUESTED`
  - `AuthAuditLog.EventType.OCR_STARTED`
  - `AuthAuditLog.EventType.OCR_COMPLETED`
  - `AuthAuditLog.EventType.OCR_FAILED`
  - `AuthAuditLog.EventType.OCR_RETRIED`
- **Migration**:
  - `apps/core/migrations/0009_alter_authauditlog_event_type_ocrrun_ocrfield_and_more.py`
