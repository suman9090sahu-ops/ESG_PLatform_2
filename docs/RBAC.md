# MEIL ESG CONTROL TOWER — Role-Based Access Control (RBAC) Architecture
## Phase 02: Authentication & Authorization Specification

---

## 1. Executive Overview

The **MEIL ESG CONTROL TOWER** operates as a unified enterprise governance and SEBI BRSR compliance platform. Roles function as an **authorization and context layer** operating on a common underlying domain model, rather than segregated Django applications.

Authentication is powered by a single custom Django identity model (`core.User`), while authorization combines coarse-grained functional roles with fine-grained **object-level organizational assignments**.

---

## 2. Authorization Hierarchy

```text
Authenticated User
       ↓
  Role(s)
       ↓
Organization Scope Assignment
  (Company / Subsidiary / Project / Site)
       ↓
Allowed Domain Object
```

### Critical Security Axiom
A functional role alone **never** implies blanket object access:
- `SITE_MANAGER` does **not** grant access to all operational sites. Access is granted **only** to sites explicitly assigned via `SiteAssignment`.
- `SUBSIDIARY_MANAGER` does **not** grant access to all corporate subsidiaries. Access is restricted to assigned subsidiaries and their child projects/sites via `SubsidiaryAssignment`.
- Direct URL requests containing client-provided IDs (e.g. `site_id`, `subsidiary_id`) are validated on the server. Tampering with IDs triggers an immediate `403 Forbidden` response and records a security audit log event.

---

## 3. Personas & Role Semantics

| Role Code | Role Name | Scope & Authority | Primary Responsibilities |
| :--- | :--- | :--- | :--- |
| **`SITE_MANAGER`** | Site Manager | Assigned Operational Sites | Operational ESG telemetry, fuel/electricity reading entries, evidence uploads, OCR digitization verification, anomaly corrections, batch submissions. Cannot access unassigned sites or modify corporate factors. |
| **`SUBSIDIARY_MANAGER`** | Subsidiary Manager | Assigned Subsidiary Divisions | Review desk for facility submissions across division projects/sites, anomaly triage, evidence validation, verification, and escalation. Cannot view unrelated subsidiaries. |
| **`ESG_MANAGER`** | Corporate ESG Manager | Corporate Enterprise Scope | GHG Scope 1, 2, 3 consolidation, emission factor library administration, unit conversion methodologies, exception governance, and SEBI BRSR Core disclosures finalization. |
| **`AUDITOR`** | ESG Assurance Auditor | Enterprise Scope (Read-Only) | Independent assurance inspection, raw evidence traceability, OCR validation audits, formula computation lineage, approval workflow histories. Strictly **read-only**; data mutations are blocked server-side. |
| **`MEIL_OPERATOR`** | MEIL Operations Lead | Enterprise Operational Hub | Operational command, telemetry streaming pipeline monitoring, sync queue diagnostics, and security audit log review. Distinct from Django `is_superuser`. |

---

## 4. Organizational Assignment Model

To support fine-grained object-level authorization without storing unstructured JSON, relational assignment models link users to explicit organizational tiers:

```text
MEIL Enterprise Group (Company)
      │
      ├── CompanyAssignment [User ↔ Company]
      │
      └── Subsidiary Companies (Subsidiary)
              │
              ├── SubsidiaryAssignment [User ↔ Subsidiary]
              │
              └── Infrastructure Projects (Project)
                      │
                      ├── ProjectAssignment [User ↔ Project]
                      │
                      └── Operational Sites (Site)
                              │
                              └── SiteAssignment [User ↔ Site]
```

### Foreign Key Protection Policy
All organizational hierarchy foreign keys employ `on_delete=models.PROTECT` to prevent accidental cascading deletion of compliance-governed infrastructure assets.

---

## 5. Organizational Scope Service & Object Authorization (`apps/core/scope_services.py`)

The authorization and queryset-scoping engine lives in `apps/core/scope_services.py` and is re-exported via `apps/core/auth_services.py`:

```python
# Object-level access verification
user_can_access_company(user, company)
user_can_access_subsidiary(user, subsidiary)
user_can_access_project(user, project)
user_can_access_site(user, site)

# Scoped querysets
get_accessible_companies(user)
get_accessible_subsidiaries(user)
get_accessible_projects(user)
get_accessible_sites(user)

# Organization mutation & hierarchy governance policies
user_can_manage_hierarchy(user)                # MEIL_OPERATOR & Superuser
user_can_manage_subsidiary(user, subsidiary)   # MEIL_OPERATOR & Superuser
user_can_manage_project(user, project, sub)    # MEIL_OPERATOR or SUBSIDIARY_MANAGER in scope
user_can_manage_site(user, site, project)      # MEIL_OPERATOR or SUBSIDIARY_MANAGER in scope

# Safe archiving policy (no cascade hard-delete)
safe_deactivate_entity(entity, user=request.user, request=request)
```

---

## 6. Insecure Direct Object Reference (IDOR) Protection

All object inspection and mutation views validate ownership server-side before resolving objects:

```python
# Example: Scoped Project Detail
@login_required
def project_detail_view(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if not user_can_access_project(request.user, project):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Project:{project.id}",
            details="IDOR violation attempt.",
            success=False,
        )
        raise PermissionDenied(f"Access Denied: Unassigned project '{project.code}'.")
    ...
```

Direct URL manipulation (e.g. changing `subsidiary_id=2` when assigned only to `subsidiary_id=1`) immediately halts execution with `403 Forbidden` and logs a security telemetry event.

---

## 7. Audit-Ready Security & Organization Logging (`AuthAuditLog`)

Every security-sensitive event is logged to the `core_authauditlog` table for regulatory traceability:
- `LOGIN_SUCCESS`, `LOGIN_FAILURE`, `LOGOUT`
- `PASSWORD_CHANGE`, `PASSWORD_RESET_REQUEST`, `PASSWORD_RESET_SUCCESS`
- `ACCOUNT_DISABLED`, `ROLE_CHANGED`, `ASSIGNMENT_CHANGED`
- `UNAUTHORIZED_ACCESS_ATTEMPT` (IDOR / cross-role / cross-subsidiary tampering)
- `ORGANIZATION_CREATED` (Company, Division, Project, or Site added)
- `ORGANIZATION_UPDATED` (Entity metadata or boundaries edited)
- `ORGANIZATION_DEACTIVATED` (Entity safely archived and marked inactive)
- `PERIOD_CREATED` (Reporting period cycle configured)
- `PERIOD_UPDATED` (Reporting period parameters modified)
- `PERIOD_STATUS_CHANGED` (Reporting period lifecycle transitioned)

Attributes captured include user reference, attempted username, event type, client IP address (`HTTP_X_FORWARDED_FOR` aware), user-agent string, resource URI, failure details, and indexed UTC timestamp.

---

## 8. Reporting Period Governance & Lifecycle RBAC (Phase 04)

Reporting period management enforces clear role-based separation:

| Role | Period Visibility | Creation & Metadata Edit | Lifecycle Status Transitions | Operational Data Entry |
| :--- | :--- | :--- | :--- | :--- |
| `MEIL_OPERATOR` | Enterprise-wide | Permitted across all companies | Full authority (`DRAFT`, `OPEN`, `CLOSED`, `LOCKED`, `FINALIZED`) | Permitted when OPEN |
| `ESG_MANAGER` | Enterprise / Governed scope | Permitted for assigned companies | Full authority for assigned companies | Permitted when OPEN |
| `SUBSIDIARY_MANAGER` | Assigned divisions + Enterprise periods | Prohibited (403) | Prohibited (403) | Permitted when OPEN |
| `SITE_MANAGER` | Assigned site's division + Enterprise periods | Prohibited (403) | Prohibited (403) | Permitted when OPEN |
| `AUDITOR` | Governed scope (Read-Only) | Strictly Prohibited (403) | Strictly Prohibited (403) | Strictly Prohibited (Read-only) |

### Temporal Data Protection Guards
- Operational ESG data entry (`can_user_enter_data`) and modifications (`can_user_modify_data`) are allowed ONLY when the period status is `OPEN`.
- Periods in `CLOSED`, `LOCKED`, or `FINALIZED` prohibit operational data creation and modification.
- Historical locked and finalized periods prohibit metadata edits, protecting regulatory audit lineage.

---

## 9. Projects & Operational Sites Operational Boundary RBAC (Phase 05)

The Project and Operational Site operational foundation enforces strict access partitioning:

| Role | Project Visibility | Site Visibility | Project/Site Creation & Mutation | Deactivation / Archival |
| :--- | :--- | :--- | :--- | :--- |
| `MEIL_OPERATOR` | Platform-wide (all projects) | Platform-wide (all sites) | Permitted across all subsidiaries & projects | Permitted (Safe Deactivation Policy) |
| `SUBSIDIARY_MANAGER` | Projects within assigned subsidiaries | Sites under projects in assigned subsidiaries | Permitted within assigned subsidiaries only | Permitted within assigned scope |
| `SITE_MANAGER` | Parent projects of assigned sites | Assigned operational sites only (`My Assigned Sites`) | Prohibited (403 Forbidden) | Prohibited (403 Forbidden) |
| `ESG_MANAGER` | Platform-wide (all projects) | Platform-wide (all sites) | Prohibited (403 Forbidden) | Prohibited (403 Forbidden) |
| `AUDITOR` | Governed scope (Read-Only) | Governed scope (Read-Only) | Strictly Prohibited (403 Forbidden) | Strictly Prohibited (403 Forbidden) |

### Key Isolation Mechanisms
1. **Site Manager Containment**:
   - `get_accessible_sites(user)` filters strictly by active `SiteAssignment` records.
   - `get_accessible_projects(user)` resolves only the parent projects of assigned sites.
   - Any access attempt to unassigned sites or unrelated projects raises `PermissionDenied` (`403 Forbidden`) and logs `UNAUTHORIZED_ACCESS_ATTEMPT`.
2. **Auditor Read-Only Enforcement**:
   - `user_can_manage_project(user)` and `user_can_manage_site(user)` return `False` for Auditors.
   - GET/POST on `/projects/create/`, `/projects/<id>/edit/`, `/sites/create/`, `/sites/<id>/edit/`, or deactivation endpoints yields `403 Forbidden`.
3. **Safe Deactivation Over Hard Deletion**:
   - Entities marked `INACTIVE` (`is_active=False`) to preserve historical ESG references and audit lineage.
   - Destructive hard deletion is prevented via `on_delete=models.PROTECT`.

---

## 10. Activity Master & Categorization RBAC (Phase 06)

The ESG Activity Master module defines the centralized catalog of BRSR and ESG activities, categorizations, and emission factors:

| Role | Activity Catalog Read | Category & Activity Create/Edit | Activity Deactivation | Custom Unit Management |
| :--- | :--- | :--- | :--- | :--- |
| `MEIL_OPERATOR` | Platform-wide | Permitted (Global) | Permitted (Safe Deactivation) | Permitted |
| `ESG_MANAGER` | Platform-wide | Permitted (Global) | Permitted (Safe Deactivation) | Permitted |
| `SUBSIDIARY_MANAGER` | Read-only | Prohibited (403 Forbidden) | Prohibited (403 Forbidden) | Prohibited (403 Forbidden) |
| `SITE_MANAGER` | Read-only (Catalog reference) | Prohibited (403 Forbidden) | Prohibited (403 Forbidden) | Prohibited (403 Forbidden) |
| `AUDITOR` | Read-only (Audit review) | Prohibited (403 Forbidden) | Prohibited (403 Forbidden) | Prohibited (403 Forbidden) |

### Key Governance Principles:
1. **Centralized Standards Control**: Only `MEIL_OPERATOR` and `ESG_MANAGER` may create or alter activity categories, standardized unit systems, or calculation methodology attributes.
2. **Immutable Historic Auditability**: Activities referenced in reporting periods are protected against hard deletion (`on_delete=models.PROTECT`).
3. **Safe Invalidation**: Deactivation (`is_active=False`) retains historical reporting integrity while preventing new data entries.

---

## 11. Site Manager Operational Dashboard Scoping & Governance (Phase 07)

The Site Manager Dashboard (`/site-manager/dashboard/` and canonical alias `/dashboard/site-manager/`) provides a role-scoped operational view strictly constrained to authorized entities:

| Role | Dashboard Access | Site Scope | Project Metrics Scope | Audit Trail Visibility |
| :--- | :--- | :--- | :--- | :--- |
| `SITE_MANAGER` | **Authorized (200 OK)** | Strictly assigned sites via `SiteAssignment` | Parent projects of assigned sites (distinct count) | User's own auth and authorized site activities only |
| `MEIL_OPERATOR` | **Authorized (200 OK)** | Supervisory access across all active sites | All active projects | Global system activity |
| `SUBSIDIARY_MANAGER` | **Forbidden (403)** | N/A (Directs to Subsidiary Dashboard) | N/A | N/A |
| `ESG_MANAGER` | **Forbidden (403)** | N/A (Directs to ESG Control Tower Dashboard) | N/A | N/A |
| `AUDITOR` | **Forbidden (403)** | N/A (Directs to Audit Review Workspace) | N/A | N/A |

### Anti-IDOR & Information Leakage Defenses
1. **Zero Client Parameter Trust**: Dashboard context computation (`get_site_manager_dashboard_context(user)`) ignores URL query parameters (such as `?site_id=...` or `?project_id=...`). Access boundaries are derived exclusively from the authenticated session user.
2. **Multi-Project Duplicate Prevention**: Projects are aggregated with `.distinct()` over authorized sites, preventing artificial inflation of project counts when multiple sites belong to the same project.
3. **Audit Trail Data Leakage Prevention**: When unauthorized access attempts occur (e.g. attempting to tamper with another site's ID in other views), the dashboard audit trail filters out foreign site identifiers to prevent resource code leakage.
4. **Zero Metric Fabrication**: All dashboard cards, tables, and readiness indicators reflect verified database queries; future workflows (Phases 08–12) display honest readiness hooks with 0 pending items rather than placeholder or random data.

---

## 12. ESG Data Entry & Activity Telemetry RBAC (Phase 08)

The ESG Data Entry module (`/data-entry/...`) enforces zero-trust, object-level authorization across the entire measurement entry lifecycle:

| Role | Ledger View (`/data-entry/`) | Create Record (`/data-entry/create/`) | Edit Record (`/data-entry/<id>/edit/`) | Delete Draft (`/data-entry/<id>/delete/`) | Detail View (`/data-entry/<id>/`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `SITE_MANAGER` | Scoped to assigned sites only | Permitted for assigned sites in OPEN periods | Permitted in DRAFT, READY, REJECTED states | Permitted in DRAFT state only | Scoped to assigned sites |
| `SUBSIDIARY_MANAGER` | Scoped to child division sites | Prohibited (403 Forbidden) | Prohibited (403 Forbidden) | Prohibited (403 Forbidden) | Scoped to child division sites |
| `MEIL_OPERATOR` | Universal enterprise scope | Permitted across enterprise sites | Permitted in editable states | Permitted for DRAFT records | Universal enterprise scope |
| `ESG_MANAGER` | Universal enterprise scope | Permitted across enterprise sites | Permitted in editable states | Permitted for DRAFT records | Universal enterprise scope |
| `AUDITOR` | Universal enterprise scope (Read-Only) | Prohibited (403 Forbidden) | Prohibited (403 Forbidden) | Prohibited (403 Forbidden) | Universal enterprise scope (Read-Only) |

### Anti-IDOR & Lifecycle Protection Rules:
1. **Query Boundary Enforcement**: `get_accessible_activity_records(user)` filters down to authorized sites before any database access occurs. Unauthorized record queries evaluate to empty or trigger `PermissionDenied`.
2. **Form Foreign Key Scoping**: Choice dropdowns for `site`, `reporting_period`, and `unit` are dynamically filtered at the form query boundary to prevent ID tampering in POST payloads.
3. **Period Lifecycle Lock**: Activity data creation or editing is strictly prohibited against `CLOSED`, `LOCKED`, or `FINALIZED` reporting cycles.
4. **Workflow Protection**: Once an Activity Record transitions to `SUBMITTED`, `VERIFIED`, or `APPROVED`, it is locked against modification by Site Managers to preserve compliance and audit integrity.

---

## 13. Evidence Management & Supporting Document RBAC (Phase 09)

The Evidence Management module (`/evidence/...` and `/data-entry/<id>/evidence/...`) implements strict object-level authorization and tamper-proof audit controls:

| Role | Repository View (`/evidence/`) | Upload Evidence (`/data-entry/<id>/evidence/upload/`) | Detail View (`/evidence/<id>/`) | Download / Preview (`.../download/`, `.../preview/`) | Retire Document (`/evidence/<id>/retire/`) | Delete Document (`.../delete/`) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `SITE_MANAGER` | Scoped to assigned sites only | Permitted for assigned sites (in DRAFT, READY, REJECTED records) | Scoped to assigned sites | Permitted for assigned sites (Audit logged) | Permitted with required justification reason | Permitted for DRAFT records only |
| `SUBSIDIARY_MANAGER` | Scoped to child division sites | Prohibited (403 Forbidden) | Scoped to child division sites | Permitted for child division sites | Prohibited (Review role only) | Prohibited (403 Forbidden) |
| `MEIL_OPERATOR` | Universal enterprise scope | Permitted across all enterprise records | Universal enterprise scope | Permitted across all records (Audit logged) | Permitted with justification | Permitted for DRAFT records |
| `ESG_MANAGER` | Universal enterprise scope | Permitted across all enterprise records | Universal enterprise scope | Permitted across all records (Audit logged) | Permitted with justification | Permitted for DRAFT records |
| `AUDITOR` | Universal enterprise scope (Read-Only) | Prohibited (403 Forbidden) | Universal enterprise scope (Read-Only) | Permitted across all records (Audit logged) | Prohibited (403 Forbidden) | Prohibited (403 Forbidden) |

### Anti-IDOR, Storage & Integrity Controls:
1. **Server-Side Authorization (`user_can_access_evidence`)**: Direct object access through URL parameters (`/evidence/<id>/`, `/evidence/<id>/download/`, `/evidence/<id>/preview/`) executes object-level permission verification before any file metadata or binary payload is transmitted.
2. **Upload Ownership Verification (`user_can_upload_evidence`)**: Attempting to post evidence to `/data-entry/<id>/evidence/upload/` verifies that the current user has site-level authorization for the parent `ActivityRecord` and that the reporting period is open and record is in an editable workflow state.
3. **Download Logging (`AuthAuditLog.EventType.EVIDENCE_DOWNLOADED`)**: Every successful file download logs the requesting user, client IP, resource ID, and file size to the immutable security audit log.
4. **Historical Preservation & Safe Retirement**: Once an activity record progresses beyond `DRAFT`, evidence files cannot be hard-deleted. They may only be transitioned to `RETIRED` state with a mandatory justification explanation, recording the retiring user and timestamp while preserving the original file and SHA-256 hash.
5. **Magic Byte Content Verification**: Rejects spoofed MIME types and disguised executables by verifying actual binary magic bytes (`%PDF-`, `\x89PNG`, `\xff\xd8\xff`, `PK\x03\x04`).

---

## 14. ESG Validation Engine & Rule Governance RBAC (Phase 10)

The ESG Validation Engine (`/data-entry/<id>/validate/`, `/validation/runs/<id>/`, `/validation/rules/...`) enforces clear boundaries between operational execution, audit review, and central rule governance:

| Role | Execute Validation on Record | Batch Validate Records | View Validation Run Audit | View Rules Catalog (`/validation/rules/`) | Create / Edit Rules | Toggle Rule Active Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `SITE_MANAGER` | Permitted for assigned sites only | Permitted for assigned sites only | Scoped to assigned sites only | **Prohibited (403 Forbidden)** | **Prohibited (403 Forbidden)** | **Prohibited (403 Forbidden)** |
| `SUBSIDIARY_MANAGER` | Scoped to child division sites | Scoped to child division sites | Scoped to child division sites | **Prohibited (403 Forbidden)** | **Prohibited (403 Forbidden)** | **Prohibited (403 Forbidden)** |
| `MEIL_OPERATOR` | Universal enterprise scope | Universal enterprise scope | Universal enterprise scope | Permitted (Full visibility) | Permitted (Full governance) | Permitted |
| `ESG_MANAGER` | Universal enterprise scope | Universal enterprise scope | Universal enterprise scope | Permitted (Full visibility) | Permitted (Full governance) | Permitted |
| `AUDITOR` | **Prohibited (403 Forbidden)** | **Prohibited (403 Forbidden)** | Universal enterprise scope (Read-Only) | Permitted (Read-Only review) | **Prohibited (403 Forbidden)** | **Prohibited (403 Forbidden)** |

### Key Isolation & Governance Mechanisms:
1. **Server-Side Record Validation Authorization (`user_can_validate_record`)**:
   - Site Managers can only trigger validation runs on `ActivityRecord` instances associated with their explicitly assigned operational sites.
   - Access attempts to unassigned records or foreign companies are blocked with `Http404` or `PermissionDenied` (Anti-IDOR).
   - Inactive or suspended user accounts are strictly blocked.
2. **Centralized Rule Governance Protection (`user_can_manage_validation_rules` / `user_can_view_validation_rules`)**:
   - Operational users (`SITE_MANAGER`, `SUBSIDIARY_MANAGER`) are prevented from viewing or modifying validation rule configurations (`403 Forbidden`), preventing unauthorized loosening of compliance standards.
   - Only `ESG_MANAGER` and `MEIL_OPERATOR` can create, edit, or toggle rules.
   - `AUDITOR` has strict read-only access to `/validation/rules/` and `/validation/rules/<id>/` for audit verification; mutation POSTs (such as `/toggle/`) are rejected with `403 Forbidden`.
3. **Immutable Run Ledger & Demotion Safety**:
   - Every execution creates a new, immutable `ValidationRun` record; historical runs are never overwritten or deleted.
   - If a record currently in `READY` status fails validation with blocking errors, the engine automatically demotes it to `DRAFT`, preventing premature submission.
4. **Audit Trail Logging**:
   - Validation executions log `VALIDATION_EXECUTED` with record ID, run number, composite status, and error count.
   - Rule changes log `VALIDATION_RULE_CREATED` and `VALIDATION_RULE_UPDATED` capturing actor, rule code, and parameter diffs.

---

## 15. OCR Document Intelligence & Entity Extraction RBAC (Phase 11)

The OCR Engine module (`/evidence/<id>/ocr/...`) enforces strict authorization boundaries between operational document processing, enterprise oversight, and independent auditor inspection:

| Role | View OCR Findings (`/evidence/<id>/`) | Trigger OCR Run (`.../ocr/process/`) | Re-run / Retry OCR (`.../ocr/runs/<run_id>/retry/`) | View OCR Run Ledger (`.../ocr/runs/<run_id>/`) | Status Telemetry API (`.../ocr/status/`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `SITE_MANAGER` | Scoped to assigned sites | Permitted for assigned sites | Permitted for assigned sites | Scoped to assigned sites | Scoped to assigned sites |
| `SUBSIDIARY_MANAGER` | Scoped to child division sites | Permitted for child division sites | Permitted for child division sites | Scoped to child division sites | Scoped to child division sites |
| `MEIL_OPERATOR` | Universal enterprise scope | Permitted across all enterprise records | Permitted across all enterprise records | Universal enterprise scope | Universal enterprise scope |
| `ESG_MANAGER` | Universal enterprise scope | Permitted across all enterprise records | Permitted across all enterprise records | Universal enterprise scope | Universal enterprise scope |
| `AUDITOR` | Universal enterprise scope (Read-Only) | **Prohibited (403 Forbidden)** | **Prohibited (403 Forbidden)** | Universal enterprise scope (Read-Only) | Universal enterprise scope (Read-Only) |

### Anti-IDOR, Governance & Non-Destructive Principles:
1. **Server-Side Authorization (`user_can_view_ocr` / `user_can_process_ocr`)**:
   - `SITE_MANAGER` can only view or trigger OCR against Evidence documents attached to `ActivityRecord` instances for their assigned sites.
   - Any attempt to access or process evidence belonging to an unassigned site or foreign company is blocked with `Http404` or `PermissionDenied` (Anti-IDOR).
   - Inactive or suspended user accounts are strictly blocked.
2. **Auditor Read-Only Isolation**:
   - The `AUDITOR` role has full inspection privileges over extracted text, structured entities, telemetry comparison indicators, and historical run ledgers.
   - However, any mutation or processing POST (`/evidence/<id>/ocr/process/` or `/ocr/runs/<run_id>/retry/`) is blocked with `403 Forbidden`.
3. **Non-Destructive Domain Principle**:
   - OCR output is strictly **UNVERIFIED DOCUMENT INTEL**.
   - OCR results NEVER silently overwrite or mutate authoritative `ActivityRecord` quantities, dates, units, or status.
   - The original uploaded evidence file and its SHA-256 hash remain completely immutable.
4. **Historical Preservative Multi-Run Lifecycle**:
   - Reprocessing an evidence document creates a new `OCRRun` record with an incremented `run_number` (`run_number=2, 3, ...`), maintaining the previous runs intact for audit review.
5. **Security Audit Logging**:
   - Every OCR execution records `OCR_REQUESTED`, `OCR_STARTED`, `OCR_COMPLETED`, or `OCR_FAILED` in the immutable `AuthAuditLog`.

---

## 16. Supplier & Procurement Management RBAC (Phase 16)

The Supplier and Procurement Management module (`/procurement/...` and `/suppliers/...`) enforces multi-tier scoping across vendor catalogs and commercial purchasing transactions:

| Role | Supplier Directory (`/suppliers/`) | Create / Edit Supplier | Soft-Archive Supplier | Procurement Ledger (`/procurement/`) | Create Procurement | Submit Procurement | Review / Verify Procurement | Request Correction |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `SITE_MANAGER` | View Active Directory | **Prohibited (403)** | **Prohibited (403)** | Scoped to Assigned Sites | Permitted for assigned sites | Permitted | **Prohibited (403)** | Remediation workspace |
| `SUBSIDIARY_MANAGER` | View Directory | **Prohibited (403)** | **Prohibited (403)** | Scoped to Division Sites | **Prohibited (403)** | **Prohibited (403)** | Permitted in scope | Permitted |
| `MEIL_OPERATOR` | Universal Enterprise Scope | Full CRUD | Permitted | Universal Enterprise Scope | Permitted | Permitted | Permitted | Permitted |
| `ESG_MANAGER` | Universal Enterprise Scope | Full CRUD | Permitted | Universal Enterprise Scope | Permitted | Permitted | Permitted | Permitted |
| `AUDITOR` | Universal Scope (Read-Only) | **Prohibited (403)** | **Prohibited (403)** | Universal Scope (Read-Only) | **Prohibited (403)** | **Prohibited (403)** | **Prohibited (403)** | **Prohibited (403)** |

### Server-Side Guards & Anti-IDOR Protections:
1. **Queryset Scoping (`get_accessible_suppliers`, `get_accessible_procurements`)**:
   - Site Managers can view only procurement records belonging to their explicitly assigned operational sites.
   - Subsidiary Managers can view procurement records belonging to projects and sites under their assigned subsidiaries.
   - ESG Managers, MEIL Operators, and Auditors view all enterprise records within active company assignments.
2. **Object Authorization (`user_can_access_procurement`, `user_can_modify_procurement`)**:
   - Attempts to access, edit, delete, or submit procurement records from unassigned sites or other companies raise `PermissionDenied` (`403 Forbidden`) and log `UNAUTHORIZED_ACCESS_ATTEMPT`.
3. **Workflow Segregation**:
   - Site Managers cannot verify their own procurements (`user_can_review_procurement` returns `False`).
   - Subsidiary Managers cannot create raw procurement records, ensuring separation of duties between purchasing entry and compliance approval.
4. **Historical Preservation & Safe Deletion**:
   - Only `DRAFT` procurement records can be hard-deleted.
   - Once submitted or verified, records are locked (`is_locked=True`) and mutations require the formal correction and resubmission workflow.
   - Suppliers cannot be hard-deleted if referenced by historical procurement records; soft-archiving (`archive()`) changes status to `ARCHIVED` while keeping historical linkages intact.

---

## 17. Transport & Logistics Management RBAC (Phase 17)

The Transport & Logistics module (`/transport/...`, `/carriers/...`, `/vehicles/...`) enforces strict organizational boundaries, fleet ownership differentiation, and governance separation of duties:

| Role | Carrier Directory (`/carriers/`) | Register / Edit Carrier | Vehicle Catalog (`/vehicles/`) | Register Vehicle | Transport Ledger (`/transport/`) | Create Transport | Submit Transport | Review / Verify | Request Correction |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `SITE_MANAGER` | View Directory | **Prohibited (403)** | Scoped to Company | Permitted (Site fleet) | Scoped to Assigned Sites | Permitted for assigned sites | Permitted | **Prohibited (403)** | Remediation workspace |
| `SUBSIDIARY_MANAGER` | Scoped to Company | Permitted in scope | Scoped to Company | Permitted in scope | Scoped to Division Sites | **Prohibited (403)** | **Prohibited (403)** | Permitted in scope | Permitted |
| `MEIL_OPERATOR` | Universal Scope | Full CRUD | Universal Scope | Full CRUD | Universal Enterprise Scope | Permitted | Permitted | Permitted | Permitted |
| `ESG_MANAGER` | Universal Scope | Full CRUD | Universal Scope | Full CRUD | Universal Enterprise Scope | Permitted | Permitted | Permitted | Permitted |
| `AUDITOR` | Universal (Read-Only) | **Prohibited (403)** | Universal (Read-Only) | **Prohibited (403)** | Universal Scope (Read-Only) | **Prohibited (403)** | **Prohibited (403)** | **Prohibited (403)** | **Prohibited (403)** |

### Server-Side Guards & Anti-IDOR Protections:
1. **Queryset Scoping (`get_accessible_transports`, `get_accessible_carriers`, `get_accessible_vehicles`)**:
   - Site Managers can query only transport movements bound to their explicitly assigned operational sites.
   - Subsidiary Managers query transport records belonging to operational sites and infrastructure projects within their authorized corporate subsidiary boundary.
   - ESG Managers, MEIL Operators, and Auditors maintain universal enterprise visibility.
2. **Object Authorization (`user_can_access_transport`, `user_can_modify_transport`, `user_can_review_transport`)**:
   - Attempting to inspect, modify, submit, or review transport records outside the user's jurisdictional scope raises `PermissionDenied` (`403 Forbidden`) or `Http404` and dispatches `AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT`.
3. **Separation of Duties**:
   - Site Managers are strictly prohibited from evaluating or verifying their own transport movements (`user_can_review_transport` evaluates to `False`).
   - Subsidiary Managers conduct independent governance reviews but cannot create raw physical transport movements, ensuring clean separation of data entry and verification.
4. **Historical Preservation & Safe Deletion**:
   - Only `DRAFT` movement records can be hard-deleted by their creator, MEIL Operator, or Superuser.
   - Once submitted or verified, records are immutably locked (`is_locked=True`).
   - Carriers and Vehicles referenced by historical transport movements cannot be hard-deleted; soft-archival (`archive()`) preserves all relational foreign keys for longitudinal audit and future Scope 1 / Scope 3 accounting.



