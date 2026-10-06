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

Attributes captured include user reference, attempted username, event type, client IP address (`HTTP_X_FORWARDED_FOR` aware), user-agent string, resource URI, failure details, and indexed UTC timestamp.
