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



