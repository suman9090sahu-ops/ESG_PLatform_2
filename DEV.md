# MEIL ESG CONTROL TOWER — Development Tracking

## Current Phase
**PHASE 07 — SITE MANAGER DASHBOARD**

**Status:** IMPLEMENTED & VERIFIED  
**Phase 07 Completion:** 100%  
**Total Project Completion:** 88%

---

## 1. Phase 04 Implementation Summary

Engineered the authoritative temporal governance foundation for the MEIL ESG Control Tower as part of the integrated Django monolith. Reporting periods establish the immutable regulatory boundaries for operational telemetry data entry, utility invoices, evidence OCR verification, Scope 1/2/3 GHG calculations, consolidation, and SEBI BRSR reporting.

### Key Architectural Deliverables
1. **Reporting Period Domain Model (`ReportingPeriod`):**
   - Fields: `company` (PROTECT FK), `subsidiary` (optional PROTECT FK), `code` (e.g. `FY2025-26`), `name`, `fiscal_year`, `start_date`, `end_date`, `status`, `description`, `created_by`, `updated_by`, timestamps.
   - Database `CheckConstraint` (`start_date < end_date`) ensuring strict date ordering.
   - Database `UniqueConstraint` on `(company, code)` enforcing unique cycle identifiers per enterprise company while preserving multi-tenant isolation.
   - Composite database indexes on `(company, status)` and `(start_date, end_date)`.
   - Application-level overlap prevention in `clean()` prohibiting conflicting date windows for the same organizational scope.
2. **Controlled Lifecycle State Machine (`PeriodStatus`):**
   - Strict state progression: `DRAFT` &rarr; `OPEN` &rarr; `CLOSED` &rarr; `LOCKED` &rarr; `FINALIZED`.
   - Explicit authorized reopening (`CLOSED -> OPEN`) and unlocking (`LOCKED -> CLOSED`).
   - `FINALIZED` is enforced as an immutable terminal regulatory state.
3. **Temporal Scoping & Governance Services (`apps/core/period_services.py`):**
   - Queryset scoping: `get_accessible_reporting_periods(user)` resolving access based on user role and assigned organization scope.
   - Current period resolver: `get_current_reporting_period(company, subsidiary, as_of_date)`.
   - Server-side object authorization: `user_can_access_reporting_period`, `user_can_manage_reporting_period`, `user_can_manage_period_lifecycle`.
   - Operational data guards: `can_user_enter_data`, `can_user_modify_data` permitting data mutations ONLY when the period status is `OPEN`.
4. **Audit-Ready Regulatory Lineage (`AuthAuditLog`):**
   - Extended with `PERIOD_CREATED`, `PERIOD_UPDATED`, and `PERIOD_STATUS_CHANGED`.
   - Transition events capture old state, new state, user actor, timestamp, and optional governance rationale.
5. **Insecure Direct Object Reference (IDOR) Protection:**
   - Tampered period IDs (`/reporting-periods/<id>/`, `/reporting-periods/<id>/edit/`, `/reporting-periods/<id>/status/`) trigger immediate `403 Forbidden` responses.
   - Tampering attempts record `UNAUTHORIZED_ACCESS_ATTEMPT` audit events.
6. **Reporting Period Management UI & Bootstrap Design:**
   - `/reporting-periods/`: List view with 6 KPI cards (Total, Open, Draft, Closed, Locked, Finalized), filters by status/company, search, and responsive table.
   - `/reporting-periods/<id>/`: Detail view featuring temporal boundary specifications, lifecycle progress indicator, authorized transition form, downstream integration hooks, and recent security audit events.
   - `/reporting-periods/create/`: Scoped creation form with server-side validation.
   - `/reporting-periods/<id>/edit/`: Scoped edit form with lock protection for historical records.
   - `/reporting-periods/<id>/status/`: POST-only transition handler with CSRF and permission enforcement.
7. **Dynamic Sidebar Navigation:**
   - Context-injected "Reporting Periods" navigation item across `MEIL_OPERATOR`, `ESG_MANAGER`, `AUDITOR`, `SUBSIDIARY_MANAGER`, and `SITE_MANAGER` menus.
8. **Automated Seeding Integration (`seed_rbac_data`):**
   - Seeds standard reporting periods: `FY2024-25` (LOCKED), `FY2025-26` (OPEN), `FY2026-27` (DRAFT).

---

## 2. Validation & System Checks

### `python manage.py check`
```text
System check identified no issues (0 silenced).
Result: PASS
```

### `python manage.py makemigrations --check`
```text
No changes detected
Result: PASS
```

### `python manage.py test`
```text
Creating test database for alias 'default'...
...........................................................................................................................
----------------------------------------------------------------------
Ran 127 tests in 121.386s

OK
Destroying test database for alias 'default'...
Found 127 test(s).
System check identified no issues (0 silenced).
Result: PASS
```

### Live E2E HTTP Verification (`tests/test_live_e2e.py`)
```text
[1] Health Check: Status 200 (Expected 200)
[2] Login meil_operator: Status 200 (Expected 200)
[3] /organization/ Overview: Status 200 (Expected 200)
[4] /organization/companies/: Status 200 (Expected 200)
[5] /organization/companies/1/: Status 200 (Expected 200)
[6] /organization/subsidiaries/: Status 200 (Expected 200)
[7] /organization/subsidiaries/1/: Status 200 (Expected 200)
[8] /organization/projects/: Status 200 (Expected 200)
[9] /organization/projects/1/: Status 200 (Expected 200)
[10] /organization/sites/: Status 200 (Expected 200)
[11] /organization/sites/1/: Status 200 (Expected 200)
[12] Login subsidiary_manager: Status 200 (Expected 200)
[13] subsidiary_manager accesses Hydro Division (/organization/subsidiaries/1/): Status 200 (Expected 200)
[14] IDOR attempt: subsidiary_manager accesses unassigned Solar Division (/organization/subsidiaries/2/): Status 403 (Expected 403)
[15] Login site_manager: Status 200 (Expected 200)
[16] site_manager attempts /organization/ overview: Status 403 (Expected 403)
[17] site_manager accesses assigned Site 1 (/organization/sites/1/): Status 200 (Expected 200)
[18] IDOR attempt: site_manager tampers URL to unassigned Site 2 (/organization/sites/2/): Status 403 (Expected 403)
[19] /reporting-periods/ List: Status 200 (Expected 200)
[20] /reporting-periods/2/ Detail (FY2025-26): Status 200 (Expected 200)
[21] /reporting-periods/create/ GET: Status 200 (Expected 200)
[22] Login esg_manager: Status 200 (Expected 200)
[23] esg_manager accesses /reporting-periods/: Status 200 (Expected 200)
[24] esg_manager accesses /reporting-periods/create/: Status 200 (Expected 200)
[25] Login auditor: Status 200 (Expected 200)
[26] auditor accesses /reporting-periods/: Status 200 (Expected 200)
[27] auditor accesses /reporting-periods/2/ Detail: Status 200 (Expected 200)
[28] auditor attempts /reporting-periods/create/ -> Status 403 (Expected 403)
[29] auditor attempts /reporting-periods/2/edit/ -> Status 403 (Expected 403)
[30] site_manager accesses /reporting-periods/: Status 200 (Expected 200)
[31] site_manager attempts /reporting-periods/create/ -> Status 403 (Expected 403)
[32] site_manager attempts /reporting-periods/2/edit/ -> Status 403 (Expected 403)

ALL 32 LIVE E2E HTTP VERIFICATIONS PASSED SUCCESSFULLY!
```

### Test Suite Breakdown
- **Phase 04 Reporting Period Suite (`tests/test_reporting_periods.py`):** 16 tests (Model instantiation, date range validation, CheckConstraint, UniqueConstraint, overlap validation, multi-tenant isolation, scoping across 5 personas, IDOR defense, lifecycle transitions, reopening/unlocking, data guards, locked/finalized immutability).
- **Phase 03 Organization Hierarchy Suite (`tests/test_organization.py`):** 15 tests.
- **Authentication Suite (`tests/test_auth.py`):** 10 tests.
- **RBAC Suite (`tests/test_rbac.py`):** 12 tests.
- **Object Access & IDOR Suite (`tests/test_object_access.py`):** 10 tests.
- **Phase 01 UI Foundation Baseline (`tests/test_phase01_foundation.py`):** 64 tests.
- **Total Tests:** 127 | **Passed:** 127 | **Failed:** 0 | **Errors:** 0

---

## 3. Database Changes
- `apps/core/migrations/0003_alter_authauditlog_event_type_reportingperiod.py`:
  - `ReportingPeriod`: Added domain model with `CheckConstraint` (`start_date < end_date`), `UniqueConstraint` on `(company, code)`, and composite indexes.
  - `AuthAuditLog`: Added event types `PERIOD_CREATED`, `PERIOD_UPDATED`, `PERIOD_STATUS_CHANGED`.

---

## 4. Documentation Updated
- `docs/DATABASE_ARCHITECTURE.md`: Added Section 7 detailing ReportingPeriod schema, constraints, and lifecycle state machine.
- `docs/RBAC.md`: Added Section 8 detailing Reporting Period RBAC matrix, temporal data protection guards, and event types.
- `docs/ROUTE_MAP.md`: Registered `/reporting-periods/...` routes and updated architectural tree.
- `DEV.md`: Phase 04 completion report and test telemetry.

---

---

# Phase 05 — Projects & Operational Sites

**Status:** IMPLEMENTED & VERIFIED  
**Date:** October 7, 2026  
**Sign-off:** Antigravity Agentic Pair Programmer

---

## 1. Overview & Architecture

Phase 05 establishes the operational **Project → Site** boundary foundation required for downstream ESG activity collection (Phase 06/07/08).
Rather than creating duplicate models or disjoint architectures, Phase 05 reuses and enhances the normalized 4-tier organizational hierarchy established in Phase 03:
```text
MEIL ENTERPRISE GROUP (Company)
           │
           └── SUBSIDIARY DIVISION (Subsidiary)
                   │
                   └── INFRASTRUCTURE PROJECT (Project)
                           │
                           └── OPERATIONAL SITE (Site)
```
Projects and Sites are persistent spatial/operational entities that span multiple financial reporting periods. Temporal integration with Phase 04 Reporting Periods is established dynamically through company and subsidiary ownership scopes without artificially creating yearly copies of sites or projects.

---

## 2. Key Deliverables & Enhancements

1. **Model Enhancements (`apps/core/models.py`)**:
   - `Project`: Added audit fields `created_by`, `updated_by` (`ForeignKey(User, SET_NULL, null=True, blank=True)`), model `clean()` date validation (`start_date <= end_date`), database `CheckConstraint` (`check_project_start_before_end`), and composite indexes on `(subsidiary, status)` and `code`.
   - `Site`: Added `operational_start_date`, `operational_end_date`, audit fields `created_by`, `updated_by` (`ForeignKey(User, SET_NULL, null=True, blank=True)`), model `clean()` date validation (`operational_start_date <= operational_end_date`), database `CheckConstraint` (`check_site_start_before_end`), and composite indexes on `(project, status)` and `code`.
   - `AuthAuditLog`: Extended `EventType` with `PROJECT_CREATED`, `PROJECT_UPDATED`, `PROJECT_DEACTIVATED`, `SITE_CREATED`, `SITE_UPDATED`, `SITE_DEACTIVATED`.

2. **Database Migration (`apps/core/migrations/0004_...`)**:
   - Clean migration generated and applied cleanly. Zero pending migrations.

3. **Forms (`apps/core/org_forms.py`)**:
   - `ProjectForm`: Date validation ensuring `start_date <= end_date`.
   - `SiteForm`: Operational timeline inputs (`operational_start_date`, `operational_end_date`) with date validation.

4. **Scoping & Authorization Services (`apps/core/scope_services.py`)**:
   - `get_accessible_projects(user)` & `get_accessible_sites(user)`: Strict object-level scoping. Confines `SITE_MANAGER` exclusively to assigned sites and their parent projects. Confines `SUBSIDIARY_MANAGER` to assigned divisions.
   - `user_can_manage_project(user)` & `user_can_manage_site(user)`: Enforces `AUDITOR` as strictly read-only (`False`), preventing mutations.
   - `safe_deactivate_entity`: Implements safe deactivation policy (`status=INACTIVE`, `is_active=False`) preventing hard-delete data loss of historical ESG records, logging granular audit events.

5. **Views & Query Optimization (`apps/core/org_views.py`)**:
   - N+1 Prevention: `project_list_view` uses `.annotate(annotated_sites_count=Count("sites", filter=Q(sites__status=OrganizationStatus.ACTIVE)))` to render active site counts efficiently.
   - Phase 04 Temporal Integration: `project_detail_view` and `site_detail_view` query and display applicable reporting cycles based on company/subsidiary scope.
   - Transparent Assignment Inspection: `site_detail_view` displays assigned Site Managers card via `site.assigned_users.all().select_related("user")`.

6. **Routing (`apps/core/urls.py`)**:
   - Direct routes registered: `/projects/`, `/projects/create/`, `/projects/<id>/`, `/projects/<id>/edit/`, `/projects/<id>/deactivate/`, `/sites/`, `/sites/create/`, `/sites/<id>/`, `/sites/<id>/edit/`, `/sites/<id>/deactivate/`.
   - Full backward compatibility maintained for existing `/organization/...` routes.

7. **Bootstrap 5 UI Templates (`templates/organization/`)**:
   - `project_list.html`: Uses `annotated_sites_count`, responsive search/filters, status badges.
   - `project_detail.html`: Shows parent subsidiary, timeline, child sites list, and applicable reporting periods table.
   - `site_list.html`: Shows parent project, status badges, location summary, action buttons.
   - `site_detail.html`: Full breadcrumb lineage, operational dates, "Assigned Site Managers" governance card, and applicable reporting periods table.
   - `site_form.html`: Updated with operational timeline date controls.

---

## 3. Test Suite & Verification Results

- **Django System Check:** `System check identified no issues (0 silenced).`
- **Migration Check:** `makemigrations --check` reports `No changes detected in apps 'core'`.
- **Full Automated Test Suite (`manage.py test`):**
  - **149 tests** across all apps and modules: **149 Passed, 0 Failed, 0 Errors** (Ran in 167.772s, OK).
  - Phase 05 Dedicated Suite (`tests/test_phase05_projects_sites.py`): 22/22 passed.
  - Organization & Hierarchy Suite (`tests/test_organization.py`): 22/22 passed.
  - RBAC Suite (`tests/test_rbac.py`): 12/12 passed.
  - Reporting Periods Suite (`tests/test_reporting_periods.py`): 22/22 passed.
  - Auth, Audit & Models Suites: 71/71 passed.
- **Live E2E HTTP Verification (`tests/test_live_e2e.py`):**
  - **47 live HTTP tests** executed against live server (`http://127.0.0.1:8000`):
    - Direct `/projects/` and `/sites/` routes: 200 OK.
    - Site Manager assigned project/site access: 200 OK.
    - Site Manager IDOR URL tampering to unassigned project/site: 403 Forbidden verified.
    - Auditor read-only inspection (200 OK) vs mutation attempts (403 Forbidden verified).

---

# Phase 06 — Activity Master & ESG Catalog Foundation

**Status:** IMPLEMENTED & VERIFIED  
**Date:** October 7, 2026  
**Sign-off:** Antigravity Agentic Pair Programmer

---

## 1. Overview & Architecture

Phase 06 establishes the centralized master data catalog for ESG activities, standard emission scopes, reporting frequencies, and physical units of measure across the MEIL Enterprise:
```text
ESG Master Data Catalog
├── Activity Categories (Energy, Water, Waste, Travel, Logistics, etc.)
├── Units of Measure (kWh, Liters, MT, km, kg, etc.)
└── Activity Masters (Central definition, default factor, scope classification, frequency)
```

## 2. Key Deliverables & Enhancements

1. **Master Domain Models (`apps/core/models.py`)**:
   - `ActivityCategory`: Code, name, description, display order, `is_active`, `created_by`, `updated_by`.
   - `UnitOfMeasure`: Code, name, symbol, dimension, conversion factor, `is_active`.
   - `ActivityMaster`: Category (FK PROTECT), base unit (FK PROTECT), allowed units (M2M), scope (Scope 1, Scope 2, Scope 3, Water, Waste, Social, Governance), frequency, default emission factor, `status` (DRAFT, ACTIVE, INACTIVE), `is_active`.
   - `AuthAuditLog`: Added events `CATEGORY_CREATED`, `CATEGORY_UPDATED`, `ACTIVITY_CREATED`, `ACTIVITY_UPDATED`, `ACTIVITY_STATUS_CHANGED`.

2. **Master Data Services (`apps/core/activity_services.py`)**:
   - Queryset scoping: `get_accessible_activity_categories`, `get_accessible_activity_masters`, `get_accessible_units`.
   - Authorization rules: `user_can_manage_activity_master` (Restricted to `MEIL_OPERATOR` and `ESG_MANAGER`).
   - Safe deactivation: `safe_deactivate_activity_master` (prevents historic data corruption).

3. **Views, Forms & URLs (`apps/core/activity_views.py`, `activity_forms.py`, `urls.py`)**:
   - Full CRUD views under `/activity-master/` with role guards and CSRF protection.
   - Comprehensive UI templates in `templates/activity_master/`.

4. **Testing & Telemetry (`tests/test_phase06_activity_master.py`)**:
   - **26 tests passed (0 failures, 0 errors)** covering models, RBAC matrix, IDOR protection, and safe deactivation.

---

# Phase 07 — Site Manager Dashboard

**Status:** IMPLEMENTED & VERIFIED  
**Date:** October 7, 2026  
**Sign-off:** Antigravity Agentic Pair Programmer

---

## 1. Overview & Architecture

Phase 07 implements the dedicated operational workspace for the `SITE_MANAGER` (and supervising `MEIL_OPERATOR`). The dashboard provides a high-fidelity, secure, site-scoped overview of authorized operational sites and ESG readiness status for the active reporting period.

```text
Logged-in Site Manager
        ↓
Server-Side Authorization (SiteAssignment)
        ↓
Authorized Operational Sites
        ↓
Parent Infrastructure Projects (Distinct)
        ↓
Current Reporting Period (Phase 04 OPEN Period)
        ↓
Aggregated Operational Telemetry & Readiness (Zero Fabrication)
```

## 2. Key Architectural Deliverables

1. **Dashboard Data Aggregation Service Layer (`apps/core/dashboard_services.py`)**:
   - `get_site_manager_dashboard_context(user, as_of_date=None)`:
     - Derives authorized sites using `get_accessible_sites(user)` with query optimization via `select_related("project", "project__subsidiary", "project__subsidiary__company", "created_by", "updated_by")`.
     - Distinct project counting (`parent_projects.count()`) to prevent duplicate project inflation when multiple sites share a project.
     - Dynamic reporting period resolution using Phase 04 `get_current_reporting_period()` or latest `OPEN` cycle.
     - Real activity master catalog counts (`active_catalog_count`).
     - Real workflow metrics (0 drafts, 0 submissions, 0 corrections, 0 validation issues, 0 pending evidence) reflecting actual database state without fabrication.
     - Scoped audit trail (`AuthAuditLog`): Displays recent operational events while filtering out foreign site resource identifiers to prevent cross-tenant information leakage.
     - Telemetry & sync status: Real-time readiness indicators and connectivity state.

2. **Server-Side Security & Anti-IDOR Protections (`apps/core/auth_views.py`)**:
   - Route `@role_required(Role.Code.SITE_MANAGER, Role.Code.MEIL_OPERATOR)` guarding `/site-manager/dashboard/`.
   - Canonical alias `/dashboard/site-manager/` with permanent redirect.
   - Zero Trust on client URL parameters: Tampered query parameters like `?site_id=2` or `?project_id=999` are completely ignored; data is derived strictly from `request.user`.
   - Access attempts by unauthorized roles (`SUBSIDIARY_MANAGER`, `ESG_MANAGER`, `AUDITOR`) yield `403 Forbidden`.

3. **Bootstrap 5 Responsive Operational Workspace (`templates/dashboards/site_manager.html`)**:
   - Page Header: Title, role badge, operational period badge, current date, and quick action refresh.
   - 5 KPI Cards: Assigned Sites, Active Projects, Current Period, Activity Catalog, Pending Actions.
   - Authorized Operational Sites Table: Site code, name, parent project, subsidiary, operational dates, status badge, and action buttons (`Inspect Site`, `View Project`, `Activity Catalog`, disabled `Data Entry [Phase 08]`).
   - ESG Workflow Status & Readiness Card: Progress bars and readiness indicators for upcoming Phase 08–12 modules.
   - Pending Actions Empty State: "You're All Caught Up" state when no actionable tasks are pending.
   - Recent Operational Activity: Scoped audit log table with timestamps, actions, and actors.
   - Operations Side Panel: Site Manager Profile, Temporal Boundary Card, Telemetry & Sync Readiness, and Quick Links.
   - Complete Empty States: Handles no assigned sites, no open reporting period, no pending actions, and empty audit logs.

4. **Integration with Existing Routes & Navigation**:
   - Updated `apps/core/urls.py` registering `/site-manager/dashboard/` and `/dashboard/site-manager/`.
   - Updated `templates/dashboards/site_detail.html` with breadcrumbs and direct link back to Site Manager Dashboard.
   - Documented in `docs/ROUTE_MAP.md` and `docs/RBAC.md`.

---

## 3. Verification & Test Telemetry

### Django System Check
```text
System check identified no issues (0 silenced).
Result: PASS
```

### Migration Check (`makemigrations --check`)
```text
No changes detected
Result: PASS (0 schema migrations needed)
```

### Phase 07 Automated Test Suite (`tests/test_phase07_site_manager_dashboard.py`)
```text
Ran 23 tests in 19.559s
OK
Result: 23 Passed, 0 Failed, 0 Errors
```
**Test Coverage Matrix:**
- `Authentication & Login Redirect`: Anonymous users redirected to `/auth/login/` (Status 302).
- `RBAC Role Enforcement`: Site Manager (200), MEIL Operator (200), Subsidiary Manager (403), ESG Manager (403), Auditor (403).
- `Site Scoping & Isolation`: Site Manager strictly sees assigned Site 1; unassigned Site 2 is excluded from context and HTML.
- `Multi-Site & Multi-Project Aggregation`: 3 assigned sites across 2 projects correctly yields count of 3 sites and 2 distinct projects without duplication.
- `Zero Client Trust / Anti-IDOR`: Query parameter `?site_id=2` completely ignored.
- `Reporting Period Resolution`: Correctly identifies current `OPEN` period (`FY2025-26`).
- `Empty States`: Verified "No sites assigned", "No active reporting period", and "No pending actions".
- `Audit Lineage & Anti-Leakage`: Tampered access attempts to foreign sites excluded from Site Manager's audit feed.
- `Query Efficiency`: Single constant batch queries (`select_related`) with no N+1 query growth.

### Full Monolith Regression Suite (`manage.py test`)
```text
Ran 198 tests in 250.709s
OK (Found 198 tests, 0 failures, 0 errors)
Result: 100% PASS
```

### Live E2E Browser & HTTP Verification (`tests/test_live_e2e.py` & `tests/verify_site_manager_dashboard_live.py`)
```text
[PASS] Session authentication & redirection to /site-manager/dashboard/
[PASS] 27 verified DOM elements rendered cleanly
[PASS] IDOR defense: Tampered site URL /site-manager/sites/2/ returns 403 Forbidden
[PASS] IDOR defense: Query param ?site_id=2 ignored
[PASS] Cross-role defense: Subsidiary Manager, ESG Manager, Auditor blocked with 403 Forbidden
[PASS] Supervisor access: MEIL Operator permitted access (200 OK)
ALL 71 LIVE E2E HTTP VERIFICATIONS PASSED SUCCESSFULLY!
```

---

## 4. Next Recommended Phase
**PHASE 08 — ESG DATA ENTRY & ACTIVITY TELEMETRY**
- Operational data entry forms scoped to authorized site, active reporting period, and approved activity masters.
- Numeric consumption inputs, physical unit validation (`validate_activity_unit`), and operational calculation hooks.
- Draft vs. Submitted lifecycle states (`ESGDataRecord`).
- Integration with Site Manager Dashboard pending actions counter.



